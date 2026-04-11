/**
 * Prompt 构建模块（v2）
 * 注入真题分析、录取分数线、时间维度策略
 */
import { DiagnosisResult } from "./diagnosis";
import { KnowledgeBase } from "./knowledge-base";
import yaml from "js-yaml";

// 模块ID到知识库key的映射
const MODULE_TO_KB_KEY: Record<string, string> = {
  numbersAndExpressions: "numbers-and-expressions",
  equationsAndInequalities: "equations-and-inequalities",
  functions: "functions",
  triangles: "triangles",
  circles: "circles",
  statisticsAndProbability: "statistics-and-probability",
  geometryComprehensive: "geometry-comprehensive",
};

const MODULE_TO_LP_KEY: Record<string, string> = {
  numbersAndExpressions: "numbers-and-expressions",
  equationsAndInequalities: "equations-and-inequalities",
  functions: "functions",
  triangles: "triangles",
  circles: "quadrilaterals-and-circles",
  statisticsAndProbability: "statistics-and-probability",
  geometryComprehensive: "geometry-comprehensive",
};

// 判断时间阶段
function getTimePhase(weeksUntilExam: number): "long_term" | "mid_term" | "sprint" {
  if (weeksUntilExam > 24) return "long_term";
  if (weeksUntilExam > 12) return "mid_term";
  return "sprint";
}

function getTimePhaseName(phase: string): string {
  switch (phase) {
    case "long_term": return "长线期（距中考6个月以上）";
    case "mid_term": return "强化期（距中考3-6个月）";
    case "sprint": return "冲刺期（距中考3个月内）";
    default: return phase;
  }
}

// 找到目标学校对应的 tier
function findTargetTier(kb: KnowledgeBase, targetScore: number): any {
  const mapping = kb.admission.mathTargetMapping;
  if (!mapping?.targets) return null;
  // 从高到低找第一个 math_score 范围匹配的 tier
  for (const tier of mapping.targets) {
    const mathScore = tier.math_score;
    if (typeof mathScore === "string" && mathScore.includes("+")) {
      const min = parseInt(mathScore);
      if (targetScore >= min) return tier;
    } else if (typeof mathScore === "string" && mathScore.includes("-")) {
      const [min, max] = mathScore.split("-").map(Number);
      if (targetScore >= min && targetScore <= max) return tier;
    }
  }
  // 返回最低层
  return mapping.targets[mapping.targets.length - 1];
}

// 找匹配的提分策略
function findScoreGapStrategy(kb: KnowledgeBase, currentMath: number, targetMath: number): any {
  const mapping = kb.admission.mathTargetMapping;
  if (!mapping?.priority_by_score_gap) return null;
  for (const strat of mapping.priority_by_score_gap) {
    const [lo, hi] = strat.current_math.split("-").map(Number);
    if (currentMath >= lo && currentMath <= hi) return strat;
  }
  return null;
}

// 从模拟题库中找出匹配该模块+水平段的题目
function findMockQuestionsForModule(kb: KnowledgeBase, moduleId: string, level: string): any[] {
  const results: any[] = [];
  for (const exam of kb.mockExams) {
    const source = `${exam.year || ""}${exam.district || ""}${exam.exam_type || ""}`;
    for (const q of exam.questions || []) {
      if (q.module !== moduleId) continue;
      if (!q.recommended_for?.includes(level)) continue;
      results.push({ ...q, source });
    }
  }
  // 每个模块最多推荐 5 道，按难度从易到难
  const diffOrder: Record<string, number> = { "基础": 0, "中档": 1, "较难": 2, "压轴": 3 };
  results.sort((a, b) => (diffOrder[a.difficulty] ?? 1) - (diffOrder[b.difficulty] ?? 1));
  return results.slice(0, 5);
}

export function buildPrompt(
  diagnosis: DiagnosisResult,
  kb: KnowledgeBase,
  district: string,
  targetSchool?: string
): { system: string; user: string } {
  const timePhase = getTimePhase(diagnosis.weeksUntilExam);

  // 筛选需要提升的模块
  const modulesToImprove = diagnosis.modules
    .filter((m) => m.level !== "L3")
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 5);

  // 组装每个模块的知识库片段（含真题锚点和时间策略）
  const moduleContexts = modulesToImprove.map((m) => {
    const kbKey = MODULE_TO_KB_KEY[m.id];
    const lpKey = MODULE_TO_LP_KEY[m.id];
    const diag = kb.diagnostics[kbKey];
    const lp = kb.learningPaths[lpKey];

    // 诊断标准中的level描述
    let levelDesc = "";
    if (diag?.levels) {
      const lvl = diag.levels.find((l: any) => l.id === m.level);
      if (lvl) {
        levelDesc = `当前水平描述：${lvl.description}\n典型表现：${(lvl.signals || []).slice(0, 3).join("；")}`;
      }
    }

    // 真题锚点
    let benchmarkStr = "";
    if (diag?.exam_benchmarks?.[m.level]) {
      const bench = diag.exam_benchmarks[m.level];
      if (bench.must_solve) {
        benchmarkStr = `\n真题锚点（做对这些题=确认${m.level}水平）：\n` +
          bench.must_solve.slice(0, 3).map((t: any) =>
            `  - ${t.year}年第${t.qid}题：${t.topic}（${t.score || ""}分）`
          ).join("\n");
      }
    }

    // 升级路径
    const upgradeKey = `${m.level}_to_${m.targetLevel}`;
    let pathData = lp?.[upgradeKey];
    if (!pathData && lpKey === "quadrilaterals-and-circles") {
      pathData = lp?.[`circles_${upgradeKey}`] || lp?.[upgradeKey];
    }

    // 时间维度策略
    let timeStrategyStr = "";
    if (lp?.time_strategies?.[timePhase]) {
      const ts = lp.time_strategies[timePhase];
      const levelKey = m.level === "L0" ? "L0" : m.level === "L1" ? "L1" : "L2";
      const advice = ts.by_level?.[levelKey];
      if (advice) {
        timeStrategyStr = `\n当前时间阶段建议（${getTimePhaseName(timePhase)}）：\n${advice}`;
      }
    }

    // 限制路径数据大小
    let pathStr = "";
    if (pathData) {
      const pathDump = yaml.dump({
        target: pathData.target,
        estimated_hours: pathData.estimated_hours,
        steps: pathData.steps?.map((s: any) => ({
          order: s.order,
          topic: s.topic,
          goal: s.goal,
          estimated_hours: s.estimated_hours,
        })),
      }, { lineWidth: 200 });
      pathStr = `\n学习路径：\n${pathDump}`;
    }

    // 易错点
    let mistakesStr = "";
    const cmKey = MODULE_TO_KB_KEY[m.id];
    const cmData = kb.commonMistakes[cmKey];
    if (cmData?.by_level?.[m.level]) {
      const levelMistakes = cmData.by_level[m.level];
      const focusIds: string[] = levelMistakes.focus || [];
      const relevantMistakes = (cmData.mistakes || [])
        .filter((mk: any) => focusIds.includes(mk.id))
        .slice(0, 3);
      if (relevantMistakes.length > 0) {
        mistakesStr = `\n⚠️ 该水平段易错点（${levelMistakes.message}）：\n` +
          relevantMistakes.map((mk: any) =>
            `  - ${mk.name}（丢${mk.typical_score_loss}分）：${mk.description.split("\n")[0]}` +
            (mk.fix_method ? `\n    纠正方法：${mk.fix_method.split("\n")[0]}` : "")
          ).join("\n");
      }
    }

    // 模拟题推荐
    let mockStr = "";
    const mockQuestions = findMockQuestionsForModule(kb, m.id, m.level);
    if (mockQuestions.length > 0) {
      mockStr = `\n📝 推荐模拟题练习：\n` +
        mockQuestions.map((q: any) =>
          `  - ${q.source} 第${q.id}题（${q.type}，${q.score}分，${q.difficulty}）：${(q.question || "").split("\n")[0].slice(0, 60)}`
        ).join("\n");
    }

    return `
### ${m.name}（当前 ${m.level} - ${m.levelName}，目标 ${m.targetLevel}，优先级 #${m.priority}）
预计提分：${m.potentialGain}分
${levelDesc}${benchmarkStr}${pathStr}${timeStrategyStr}${mistakesStr}${mockStr}
`;
  }).join("\n");

  // 区域信息
  const districtMap: Record<string, string> = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng", "朝阳": "chaoyang",
  };
  const dKey = districtMap[district.replace("区", "")] || "haidian";
  const districtInfo = kb.districts[dKey];

  // 时间分配
  const timeAllocStr = diagnosis.timeAllocation
    .filter((t) => t.percentage > 0)
    .map((t) => `${t.moduleName}：${t.percentage}%（每周${t.hoursPerWeek}小时）`)
    .join("\n");

  // 真题分析摘要
  const examSummary = kb.examAnalysis.summary;
  let scoreSources = "";
  if (examSummary?.score_sources) {
    // 根据目标分数选择匹配的分数段策略
    const target = diagnosis.targetScore;
    let matchedLevel = "60分（及格）";
    if (target >= 95) matchedLevel = "95+分（拔尖）";
    else if (target >= 90) matchedLevel = "90分（优秀）";
    else if (target >= 80) matchedLevel = "80分（良好）";
    const sourceData = examSummary.score_sources[matchedLevel];
    if (sourceData) {
      scoreSources = `\n目标${matchedLevel}的得分策略：\n${yaml.dump(sourceData, { lineWidth: 200 })}`;
    }
  }

  // 目标学校→数学目标分映射
  let targetTierStr = "";
  const tier = findTargetTier(kb, diagnosis.targetScore);
  if (tier) {
    targetTierStr = `\n目标层级：${tier.tier}（${tier.description}）\n考试策略：${tier.exam_strategy}`;
    if (tier.time_advice) {
      targetTierStr += `\n时间分配建议：${tier.time_advice}`;
    }
  }

  // 提分策略
  let scoreGapStr = "";
  const gapStrategy = findScoreGapStrategy(kb, diagnosis.totalScore, diagnosis.targetScore);
  if (gapStrategy) {
    scoreGapStr = `\n提分策略（从${gapStrategy.current_math}分到${gapStrategy.target_math}分）：\n` +
      gapStrategy.priority_modules.map((p: any) => `  - ${p.module}：${p.action}，预期${p.gain}`).join("\n") +
      `\n总预期提分：${gapStrategy.total_potential}\n${gapStrategy.note || ""}`;
  }

  // 录取分数线参考
  let admissionStr = "";
  const admDistrict = kb.admission.districts[dKey];
  if (admDistrict && targetSchool) {
    const school = admDistrict.schools?.find((s: any) =>
      s.name.includes(targetSchool) || targetSchool.includes(s.name.replace(/北京市|中学|学校/g, ""))
    );
    if (school) {
      admissionStr = `\n目标学校录取参考：${school.name}\n${yaml.dump(school.scores, { lineWidth: 200 })}`;
    }
  }

  // 教辅推荐矩阵
  let resourceStr = "";
  const recMatrix = kb.resources.workbooks?.recommendation_matrix;
  if (recMatrix) {
    // 根据学生整体水平选匹配的推荐
    const levelKey = diagnosis.estimatedTotalLevel === "L0" ? "L0_student"
      : diagnosis.estimatedTotalLevel === "L1" ? "L1_student"
      : diagnosis.estimatedTotalLevel === "L2" ? "L2_student"
      : "L3_student";
    const rec = recMatrix[levelKey];
    if (rec) {
      resourceStr = `\n教辅推荐（${levelKey.replace("_", " ")}）：\n` +
        `  主力教辅：${rec.primary}\n` +
        `  辅助教辅：${rec.secondary}\n` +
        (rec.optional ? `  可选：${rec.optional}\n` : "") +
        (rec.avoid ? `  ⚠️ 不推荐：${rec.avoid}\n` : "") +
        (rec.note ? `  备注：${rec.note}\n` : "");
    }
  }

  // 真题命题趋势
  let trendsStr = "";
  if (examSummary?.trends) {
    trendsStr = `\n命题趋势：实际情境题${examSummary.trends.real_world_context}；函数每年占${examSummary.trends.function_emphasis}；${examSummary.trends.textbook_origin}`;
  }

  // 模拟题统计
  const mockExamCount = kb.mockExams.length;
  const mockQuestionCount = kb.mockExams.reduce((sum, e) => sum + (e.questions?.length || 0), 0);

  const system = `你是一位经验丰富的北京中考数学辅导专家。你拥有完整的北京中考真题数据库（2021-2025年共140道题的逐题分析）、朝阳/海淀/西城/东城四区高中的录取分数线，以及${mockExamCount}套各区一模试卷（共${mockQuestionCount}道题，含完整题目、答案和解析）。

你的任务是根据学生的诊断数据、真题分析和知识库中的学习路径，生成一份针对性极强的学习规划。

核心要求：
1. 语气亲切但专业，像经验丰富的班主任
2. 所有建议必须具体——引用真实的题号（如"2025年第22题一次函数"），推荐具体的教材章节和教辅页码
3. 根据距中考的时间阶段（${getTimePhaseName(timePhase)}）调整策略的激进程度
4. 明确告诉学生哪些题必须拿分、哪些题可以放弃——基于真题数据而非泛泛而谈
5. 过关标准可量化（"连续做对5年真题Q17"而非"掌握即可"）
6. 用分数说话（"函数从L0提到L1，Q22能做对就是5分到手"）
7. 该生在${district}，注意区的特点
8. 输出用 Markdown 格式，结构清晰
9. **周计划是整份报告的核心价值**——学生拿到报告后应该能直接照着第1周的计划开始学习，不需要再做任何翻译和转化。第1周的每一天都要写清楚"几点到几点做什么、用什么材料、做到什么标准算完成"`;

  const user = `## 学生基本情况

- 所在区：${district}
- 数学成绩：${diagnosis.totalScore}/100（${diagnosis.estimatedTotalLevel}）
- 每周可用学习时间：${diagnosis.totalWeeklyHours}小时
- 距中考：${diagnosis.weeksUntilExam}周（当前处于**${getTimePhaseName(timePhase)}**）
- 目标分数：${diagnosis.targetScore}分${targetSchool ? `\n- 目标学校：${targetSchool}` : ""}
${targetTierStr}

## 各模块诊断结果

${diagnosis.modules.map((m) => `| ${m.name} | ${m.level}(${m.levelName}) | 预估${m.currentEstimatedScore}分 | 可提${m.potentialGain}分 | 优先级#${m.priority} |`).join("\n")}
${scoreGapStr}

## 真题得分策略
${scoreSources}

## 建议的时间分配

${timeAllocStr}

## 各模块详细数据（含真题锚点和时间策略）

${moduleContexts}

## 教辅资源推荐
${resourceStr}

## 真题命题趋势
${trendsStr}
${admissionStr}

---

请基于以上数据，为这位同学生成一份学习规划报告，分为两大部分：

---

## 第一部分：整体规划（全局视角）

1. **一句话诊断**：当前水平、与目标的差距、核心策略方向。

2. **各模块诊断表**（表格，每模块一行：模块名 | 当前水平 | 关键问题 | 必拿分题号 | 过关标准）

3. **总体路线图**（按月/阶段划分，距中考共${diagnosis.weeksUntilExam}周）：
   用表格或时间线展示，每个阶段包含：
   - 阶段名称和时间范围（如"第1-3周：基础修补期"）
   - 本阶段重点攻克的模块
   - 阶段目标（用分数或过关标准衡量，如"函数从L1→L2，Q22做对"）
   - 主要使用的学习材料
   最后1-2周标注为"考前冲刺"：全真模拟 + 错题回顾 + 心态调整。
   路线图要简洁，每个阶段3-5行即可，让学生一眼看到全貌。

4. **逐周概览**（每周1-2行，表格形式）：
   | 周次 | 重点模块 | 核心任务 | 过关检测 |
   让学生快速查阅任意一周的重点。

5. **考场策略**（简要，5行以内）+ **提醒**（3条以内）

---

## 第二部分：本周详细计划（执行视角）

这是学生拿到报告后**立刻照着做**的部分，要求精确到每天：

- 每天标注时间段（如19:00-19:45）和学习模块
- 具体任务：教材哪一节（如"人教版八下§19.1 p.45-52"）、教辅哪几题（如"五三A版 p.78 第5-15题"）、模拟题哪道（如"2025西城一模第22题，限时15分钟"）
- 每天结尾标注 ✅ 完成标准（如"12题对10题以上"）
- 周五安排限时检测（从模拟题中选题组卷，标明时间和目标分）
- 周末安排错题回顾 + 过关检测（用真题验证本周成果）
- 每天交叉安排不同模块（防疲劳、防遗忘）
- 优先级高的模块安排更多时间

---

篇幅控制：第一部分占30%（给全局感），第二部分占70%（给执行力）。`;

  return { system, user };
}
