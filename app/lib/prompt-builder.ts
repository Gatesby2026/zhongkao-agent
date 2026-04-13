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

  // ============ 以下为新增注入：把已加载未使用的知识库数据接入 ============

  // 1. 考试政策与关键日期
  let policyStr = "";
  if (kb.policy) {
    const p = kb.policy;
    const examDates = p.exam_dates;
    policyStr = `\n## 考试政策与关键日期\n` +
      `- 中考总分：${p.total_score}分，数学${p.exam_subjects?.find((s: any) => s.subject === "数学")?.score || 100}分/120分钟闭卷\n` +
      (examDates ? `- 统考日期：${examDates.written_exam || "2026-06-24~25"}\n` : "") +
      (p.changes_from_2025 ? `- 2026改革要点：${(p.changes_from_2025 || []).slice(0, 3).map((c: any) => c.change || c).join("；")}\n` : "") +
      (p.admission?.stages ? `- 录取批次：${p.admission.stages.map((s: any) => s.name || s).join(" → ")}\n` : "");
  }

  // 2. 区域特色
  let districtFeatureStr = "";
  if (districtInfo) {
    const chars = districtInfo.characteristics;
    const mathF = districtInfo.math_features;
    districtFeatureStr = `\n## ${district}特色\n` +
      (districtInfo.textbook ? `- 教材版本：${districtInfo.textbook}\n` : "") +
      (chars?.exam_difficulty ? `- 考试难度：${chars.exam_difficulty}\n` : "") +
      (mathF?.mock_difficulty ? `- 模考难度：${mathF.mock_difficulty}\n` : "") +
      (mathF?.style ? `- 命题风格：${mathF.style}\n` : "") +
      (mathF?.notes ? `- 备考提示：${mathF.notes}\n` : "");
  }

  // 3. 考纲权重与提分优先级（weight-analysis）
  let weightStr = "";
  const wa = kb.weightAnalysis;
  if (wa?.score_improvement_priority) {
    weightStr = `\n## 提分ROI优先级排序（基于考纲权重分析）\n` +
      wa.score_improvement_priority.map((p: any) =>
        `${p.rank}. ${p.area}（潜力${p.potential}，投入${p.effort}）：${p.reason}`
      ).join("\n");
  }

  // 4. 题型分布与目标分数对应题号（question-types）
  let questionTypeStr = "";
  const qt = kb.questionTypes;
  if (qt?.score_targets) {
    questionTypeStr = `\n## 各目标分数对应的必拿题号\n`;
    for (const [target, data] of Object.entries(qt.score_targets) as any) {
      if (data?.must_solve) {
        questionTypeStr += `- ${target}：必拿 ${data.must_solve.join("、")}`;
        if (data.try_solve) questionTypeStr += `，争取 ${data.try_solve.join("、")}`;
        questionTypeStr += "\n";
      }
    }
  }
  if (qt?.difficulty_ratio) {
    questionTypeStr += `难度比例：基础${qt.difficulty_ratio.basic || "50%"}、中档${qt.difficulty_ratio.medium || "35%"}、压轴${qt.difficulty_ratio.hard || "15%"}\n`;
  }

  // 5. 教材章节索引（textbooks）— 让 LLM 精准引用教材
  let textbookStr = "";
  const tb = kb.resources.textbooks;
  if (tb) {
    // 根据区确定教材版本
    const districtCn = district.replace("区", "");
    const useRenjiao = ["海淀", "西城", "东城", "朝阳", "丰台"].includes(districtCn);
    const version = useRenjiao ? "人教版" : "北京版";
    const versionData = tb[version === "人教版" ? "人教版" : "北京版"];
    if (versionData?.volumes) {
      textbookStr = `\n## 教材章节索引（${version}，该生适用）\n`;
      for (const vol of versionData.volumes) {
        const keyChapters = (vol.key_chapters || [])
          .filter((c: any) => c.relevance === "极高" || c.relevance === "高")
          .map((c: any) => `${c.chapter}→${c.maps_to_module}(${c.relevance})`);
        if (keyChapters.length > 0) {
          textbookStr += `- ${vol.volume}：${keyChapters.join("、")}\n`;
        }
      }
    }
  }

  // 6. 真题/模拟卷使用策略（exam-papers）— 根据时间阶段给出用卷建议
  let examPaperStrategyStr = "";
  const ep = kb.resources.examPapers;
  if (ep?.overall_strategy) {
    // 根据当前时间阶段匹配策略
    const phaseMap: Record<string, string> = {
      "long_term": "phase_1_基础期",
      "mid_term": "phase_2_一模前",
      "sprint": "phase_3_一模后",
    };
    const currentPhaseKey = phaseMap[timePhase];
    const phaseData = ep.overall_strategy[currentPhaseKey] || ep.overall_strategy["phase_4_考前冲刺"];
    if (phaseData) {
      examPaperStrategyStr = `\n## 当前阶段的做卷策略\n` +
        `阶段：${phaseData.name || currentPhaseKey}（${phaseData.time || ""}）\n` +
        `策略：${phaseData.strategy || phaseData.focus || ""}\n`;
      if (phaseData.frequency) examPaperStrategyStr += `频率：${phaseData.frequency}\n`;
      if (phaseData.key_rule) examPaperStrategyStr += `关键原则：${phaseData.key_rule}\n`;
    }
  }
  // 用卷水平建议
  if (ep?.beijing_zhongkao?.usage_guide) {
    const levelGuide = ep.beijing_zhongkao.usage_guide[diagnosis.estimatedTotalLevel];
    if (levelGuide) {
      examPaperStrategyStr += `真题使用建议（${diagnosis.estimatedTotalLevel}水平）：${levelGuide}\n`;
    }
  }

  // 7. 在线平台推荐
  let platformStr = "";
  const op = kb.resources.onlinePlatforms;
  if (op?.free_platforms) {
    const topPlatforms = (op.free_platforms || [])
      .filter((p: any) => p.recommend_level === "A")
      .map((p: any) => `${p.name}(${p.key_features?.[0] || p.type})`);
    if (topPlatforms.length > 0) {
      platformStr = `\n推荐在线资源：${topPlatforms.join("、")}`;
    }
  }

  // 模拟题统计
  const mockExamCount = kb.mockExams.length;
  const mockQuestionCount = kb.mockExams.reduce((sum, e) => sum + (e.questions?.length || 0), 0);

  const system = `你是一位经验丰富的北京中考数学辅导专家。你拥有完整的北京中考真题数据库（2021-2025年共140道题的逐题分析）、15个区的高中录取分数线，以及${mockExamCount}套各区模考试卷（共${mockQuestionCount}道题，含完整题目、答案和解析），以及完整的人教版/北京版教材章节索引。

你的任务是根据学生的诊断数据、真题分析和知识库中的学习路径，生成一份针对性极强的学习规划。

核心要求：
1. 语气亲切但专业，像经验丰富的班主任
2. 所有建议必须具体——引用真实的题号（如"2025年第22题一次函数"），推荐具体的教材章节和教辅页码（下方有完整的教材章节索引，请据此引用）
3. 根据距中考的时间阶段（${getTimePhaseName(timePhase)}）调整策略的激进程度
4. 明确告诉学生哪些题必须拿分、哪些题可以放弃——基于下方的「各目标分数对应必拿题号」数据
5. 过关标准可量化（"连续做对5年真题Q17"而非"掌握即可"）
6. 用分数说话（"函数从L0提到L1，Q22能做对就是5分到手"）
7. 该生在${district}，注意下方给出的区域特色和模考风格
8. 输出用 Markdown 格式，结构清晰
9. **周计划是整份报告的核心价值**——学生拿到报告后应该能直接照着第1周的计划开始学习，不需要再做任何翻译和转化。第1周的每一天都要写清楚"几点到几点做什么、用什么材料、做到什么标准算完成"
10. 做卷安排要参考下方的「当前阶段做卷策略」，不同时间阶段用卷方式不同`;

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
${policyStr}
${districtFeatureStr}
${weightStr}
${questionTypeStr}
${textbookStr}
${examPaperStrategyStr}
${platformStr}

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

// ============================================================
// 场景2：全科总分规划模式（510分制）
// ============================================================

export interface MultiSubjectInput {
  district: string;
  daysUntilExam: number;
  availableHoursPerDay: number;
  targetTotalScore?: number;  // 目标总分（满分510）
  targetSchool?: string;
  scores: {
    chinese: number;    // /100
    math: number;       // /100
    english: number;    // /100
    physics: number;    // /80
    politics: number;   // /80
    pe: number;         // /50
  };
}

interface SubjectAnalysis {
  name: string;
  key: string;
  fullScore: number;
  current: number;
  gap: number;
  gapRatio: number;
  roi: number;         // 提分性价比
  suggestedHoursPercent: number;
}

const SUBJECT_FULL_SCORES: Record<string, number> = {
  chinese: 100, math: 100, english: 100, physics: 80, politics: 80, pe: 50,
};
const SUBJECT_NAMES: Record<string, string> = {
  chinese: "语文", math: "数学", english: "英语", physics: "物理", politics: "道德与法治", pe: "体育",
};
// 各科提分难度系数（越低越容易提分）
const SUBJECT_DIFFICULTY: Record<string, number> = {
  math: 0.6, english: 0.7, physics: 0.7, politics: 0.65, chinese: 1.0, pe: 0.8,
};

function analyzeSubjects(scores: MultiSubjectInput["scores"]): SubjectAnalysis[] {
  const subjects: SubjectAnalysis[] = [];
  let totalROI = 0;

  for (const [key, current] of Object.entries(scores)) {
    const fullScore = SUBJECT_FULL_SCORES[key];
    const gap = fullScore - current;
    const gapRatio = gap / fullScore;
    // ROI = 提分空间 × (1 - 难度系数)，空间越大、难度越低的科目ROI越高
    const roi = gap * (1 - SUBJECT_DIFFICULTY[key] * 0.5);
    totalROI += roi;
    subjects.push({
      name: SUBJECT_NAMES[key],
      key,
      fullScore,
      current,
      gap,
      gapRatio,
      roi,
      suggestedHoursPercent: 0,
    });
  }

  // 按ROI分配时间（体育单独占10%）
  const peSubject = subjects.find(s => s.key === "pe")!;
  const culturalSubjects = subjects.filter(s => s.key !== "pe");
  const culturalTotalROI = culturalSubjects.reduce((sum, s) => sum + s.roi, 0);

  peSubject.suggestedHoursPercent = 10;
  for (const s of culturalSubjects) {
    s.suggestedHoursPercent = Math.round((s.roi / culturalTotalROI) * 90);
  }
  // 修正误差
  const sum = subjects.reduce((s, x) => s + x.suggestedHoursPercent, 0);
  if (sum !== 100) {
    const maxS = culturalSubjects.sort((a, b) => b.roi - a.roi)[0];
    maxS.suggestedHoursPercent += 100 - sum;
  }

  return subjects.sort((a, b) => b.roi - a.roi);
}

function buildSubjectKBContext(
  kb: KnowledgeBase,
  subjectKey: string,
  current: number,
  fullScore: number
): string {
  if (subjectKey === "math") {
    // 数学已经有深度数据，只给摘要
    const wa = kb.weightAnalysis;
    let str = "**数学**（知识库深度：★★★★★，含完整诊断/路径/易错点/试卷库）\n";
    if (wa?.score_improvement_priority) {
      str += "提分优先级：" + wa.score_improvement_priority.slice(0, 3)
        .map((p: any) => `${p.area}(潜力${p.potential})`)
        .join(" → ") + "\n";
    }
    return str;
  }

  if (subjectKey === "pe") {
    const pe = kb.subjects.pe;
    let str = "**体育**（50分 = 过程性10分 + 现场40分）\n";
    if (pe.examSpec) {
      const spec = pe.examSpec;
      if (spec.on_site_exam?.events) {
        str += "现场考试项目：" + spec.on_site_exam.events
          .map((e: any) => `${e.name}(${e.score}分)`)
          .join("、") + "\n";
      }
    }
    if (pe.scoringStandards) {
      str += "评分标准数据已加载，可精确到性别/项目/成绩段\n";
    }
    if (pe.trainingPlans) {
      str += "训练方案数据已加载，可生成专项训练计划\n";
    }
    return str;
  }

  // 语文/英语/物理/道法
  const subjectMap: Record<string, keyof KnowledgeBase["subjects"]> = {
    chinese: "chinese", english: "english", physics: "physics", politics: "politics",
  };
  const data = kb.subjects[subjectMap[subjectKey] as "chinese" | "english" | "physics" | "politics"];
  if (!data) return "";

  const name = SUBJECT_NAMES[subjectKey];
  let str = `**${name}**\n`;

  // 考试规格摘要
  if (data.examSpec) {
    const spec = data.examSpec;
    const bi = spec.basic_info;
    if (bi) {
      str += `满分${bi.full_score}分，${bi.duration_min}分钟，${bi.exam_type}`;
      if (bi.composition) {
        str += "（" + bi.composition.map((c: any) => `${c.part}${c.score}分`).join("+") + "）";
      }
      str += "\n";
    }
  }

  // 权重分析 —— 提分优先级
  if (data.weightAnalysis?.score_improvement_priority) {
    const priorities = data.weightAnalysis.score_improvement_priority.slice(0, 5);
    str += "提分优先级：\n";
    for (const p of priorities) {
      str += `  ${p.rank}. ${p.area}（潜力${p.potential}，投入${p.effort}）：${p.reason}\n`;
    }
  }

  // 得分策略 —— 根据当前分数匹配
  if (data.weightAnalysis?.score_sources || data.examSpec?.score_targets) {
    const sources = data.weightAnalysis?.score_sources || {};
    const ratio = current / fullScore;
    let matchedKey = "";
    if (ratio < 0.6) matchedKey = Object.keys(sources)[0] || "";
    else if (ratio < 0.8) matchedKey = Object.keys(sources)[1] || "";
    else if (ratio < 0.9) matchedKey = Object.keys(sources)[2] || "";
    else matchedKey = Object.keys(sources)[3] || "";
    if (matchedKey && sources[matchedKey]) {
      str += `当前分数段得分策略（${matchedKey}）：\n`;
      const sd = sources[matchedKey];
      if (sd.guaranteed_questions) {
        for (const q of sd.guaranteed_questions) {
          str += `  - ${q}\n`;
        }
      }
    }
  }

  // 考试分析 —— 命题趋势
  if (data.examAnalysis?.summary?.trends) {
    const trends = data.examAnalysis.summary.trends;
    if (typeof trends === "object" && !Array.isArray(trends)) {
      const entries = Object.entries(trends).slice(0, 3);
      str += "命题趋势：" + entries.map(([k, v]) => `${k}=${typeof v === 'string' ? v.slice(0, 40) : v}`).join("；") + "\n";
    } else if (typeof trends === "string") {
      str += "命题趋势：" + trends.slice(0, 100) + "\n";
    }
  }

  // 题型结构概览
  if (data.questionTypes?.yearly_comparison) {
    const latest = data.questionTypes.yearly_comparison[data.questionTypes.yearly_comparison.length - 1];
    if (latest) {
      str += `最新题型结构（${latest.year}年）：${latest.written_structure || latest.notable_changes || ""}\n`;
    }
  }

  return str;
}

export function buildMultiSubjectPrompt(
  input: MultiSubjectInput,
  kb: KnowledgeBase
): { system: string; user: string } {
  const weeksUntilExam = Math.ceil(input.daysUntilExam / 7);
  const timePhase = getTimePhase(weeksUntilExam);
  const totalCurrent = Object.values(input.scores).reduce((s, v) => s + v, 0);
  const targetTotal = input.targetTotalScore || Math.min(totalCurrent + 50, 510);
  const totalWeeklyHours = input.availableHoursPerDay * 7;

  // 分析各科
  const subjects = analyzeSubjects(input.scores);

  // 各科知识库上下文
  const subjectContexts = subjects.map(s =>
    buildSubjectKBContext(kb, s.key, s.current, s.fullScore)
  ).join("\n---\n");

  // 时间分配表
  const timeTable = subjects.map(s =>
    `| ${s.name} | ${s.current}/${s.fullScore} | ${s.gap}分 | ${s.suggestedHoursPercent}%（${Math.round(totalWeeklyHours * s.suggestedHoursPercent / 100 * 10) / 10}h/周）|`
  ).join("\n");

  // 录取信息
  const districtMap: Record<string, string> = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng", "朝阳": "chaoyang",
  };
  const dKey = districtMap[input.district.replace("区", "")] || "haidian";
  let admissionStr = "";
  const admDistrict = kb.admission.districts[dKey];
  if (admDistrict && input.targetSchool) {
    const school = admDistrict.schools?.find((s: any) =>
      s.name.includes(input.targetSchool!) || input.targetSchool!.includes(s.name.replace(/北京市|中学|学校/g, ""))
    );
    if (school) {
      admissionStr = `\n## 目标学校录取参考\n${school.name}\n${yaml.dump(school.scores, { lineWidth: 200 })}`;
    }
  }

  // 政策信息
  let policyStr = "";
  if (kb.policy) {
    const p = kb.policy;
    policyStr = `\n## 2026年北京中考政策\n` +
      `- 总分：${p.total_score}分（语数英各100 + 物理道法各80 + 体育50）\n` +
      `- 考试日期：${p.exam_dates?.written_exam || "2026年6月24-25日"}\n` +
      (p.changes_from_2025 ? `- 改革要点：${(p.changes_from_2025 || []).slice(0, 3).map((c: any) => c.change || c).join("；")}\n` : "");
  }

  // 区域特色
  const districtInfo = kb.districts[dKey];
  let districtStr = "";
  if (districtInfo) {
    districtStr = `\n## ${input.district}特色\n` +
      (districtInfo.textbook ? `- 教材版本：${districtInfo.textbook}\n` : "") +
      (districtInfo.characteristics?.exam_difficulty ? `- 考试难度：${districtInfo.characteristics.exam_difficulty}\n` : "");
  }

  const system = `你是一位经验丰富的北京中考学习规划专家，精通全部6个计分科目（语文100+数学100+英语100+物理80+道德与法治80+体育50=510分）。

你拥有完整的北京中考知识库：
- 6科考试大纲、题型分析、权重分析
- 2021-2025年五年真题逐年分析和跨年汇总
- 数学科目有完整的诊断/学习路径/易错点/试卷库（最深度的科目）
- 4区录取分数线数据
- 体育评分标准和训练方案

核心要求：
1. 语气亲切但专业，像经验丰富的班主任
2. **全科统筹**——不是6科分别给建议，而是站在510分总分的高度做全局最优分配
3. 根据各科的"提分性价比"排序，把时间优先投入ROI最高的科目
4. 数学科目可以引用具体题号和真题锚点（你有最完整的数据）
5. 其他科目基于考纲权重和提分优先级给出方向性建议
6. 体育需要考虑训练周期——不能考前突击，需要提前安排
7. 当前处于${getTimePhaseName(timePhase)}，策略要匹配时间紧迫程度
8. 明确指出哪些科目该"主攻"、哪些"保稳"、哪些"放养"
9. 输出用 Markdown 格式，结构清晰`;

  const user = `## 学生基本情况

- 所在区：${input.district}
- 当前总分：${totalCurrent}/510
- 目标总分：${targetTotal}/510${input.targetSchool ? `\n- 目标学校：${input.targetSchool}` : ""}
- 每天可用学习时间：${input.availableHoursPerDay}小时（每周${totalWeeklyHours}小时）
- 距中考：${weeksUntilExam}周（当前处于**${getTimePhaseName(timePhase)}**）

## 各科成绩与分析

| 科目 | 当前/满分 | 差距 | 建议时间占比 |
|------|-----------|------|-------------|
${timeTable}

## 各科知识库数据

${subjectContexts}
${policyStr}
${districtStr}
${admissionStr}

---

请基于以上数据，为这位同学生成一份 **全科学习规划报告**，包含：

## 第一部分：全局诊断与策略

1. **一句话总评**：当前水平定位、与目标的差距、核心策略方向

2. **各科诊断表**（表格）：
   | 科目 | 当前分 | 目标分 | 策略定位 | 核心任务 | 预期提分 |
   策略定位分为：主攻（投入最多）、重点（次优先）、保稳（维持）、放养（投入最少）

3. **提分路径**：按"投入产出比"从高到低排序，说明每科主要提分点在哪里
   - 引用各科的提分优先级数据
   - 数学可以精确到模块和题号

4. **总体时间线**（按月/阶段划分）：
   - 每个阶段各科的重点任务
   - 阶段性目标（用分数衡量）

## 第二部分：本周执行计划

精确到每天的学习安排：
- 每天按时间段分配不同科目
- 优先级高的科目安排在精力最好的时段
- 每天标注具体任务（对于数学可以精确到题号和页码）
- 每天的完成标准
- 周末安排阶段检测

## 第三部分：各科专项建议（简要）

每科3-5行的核心备考建议，包括：
- 重点攻克的知识点/题型
- 推荐的学习方法和材料
- 需要避免的常见误区

---

篇幅控制：第一部分40%，第二部分40%，第三部分20%。`;

  return { system, user };
}

// ============================================================
// 场景1：模块突破模式
// ============================================================

export interface ModuleDrillInput {
  moduleId: string;       // 模块 ID（如 "functions"）
  level: string;          // 当前水平 L0/L1/L2/L3
  district: string;       // 所在区
  hoursPerWeek: number;   // 每周可投入该模块的小时数
  weeksUntilExam: number; // 距中考周数
  problem?: string;       // 学生自述的具体问题（可选）
}

const MODULE_NAMES: Record<string, string> = {
  numbersAndExpressions: "数与式",
  equationsAndInequalities: "方程与不等式",
  functions: "函数",
  triangles: "三角形",
  circles: "圆",
  statisticsAndProbability: "统计与概率",
  geometryComprehensive: "几何综合/压轴",
};

export function buildModuleDrillPrompt(
  input: ModuleDrillInput,
  kb: KnowledgeBase
): { system: string; user: string } {
  const { moduleId, level, district, hoursPerWeek, weeksUntilExam } = input;
  const moduleName = MODULE_NAMES[moduleId] || moduleId;
  const kbKey = MODULE_TO_KB_KEY[moduleId];
  const lpKey = MODULE_TO_LP_KEY[moduleId];

  // 诊断标准
  const diag = kb.diagnostics[kbKey];
  let diagStr = "";
  if (diag?.levels) {
    const lvl = diag.levels.find((l: any) => l.id === level);
    if (lvl) {
      diagStr = `当前水平（${level}）：${lvl.description}\n典型表现：${(lvl.signals || []).join("；")}`;
    }
  }

  // 易错点（该模块全部，不限制数量）
  let mistakesStr = "";
  const cmData = kb.commonMistakes[kbKey];
  if (cmData?.by_level?.[level]) {
    const levelMistakes = cmData.by_level[level];
    const focusIds: string[] = levelMistakes.focus || [];
    const relevantMistakes = (cmData.mistakes || [])
      .filter((mk: any) => focusIds.includes(mk.id));
    if (relevantMistakes.length > 0) {
      mistakesStr = relevantMistakes.map((mk: any) =>
        `- **${mk.name}**（丢${mk.typical_score_loss}分，频率${mk.frequency}）\n  问题：${mk.description}\n  纠正：${mk.fix_method || "暂无"}`
      ).join("\n");
    }
  }

  // 学习路径
  const lp = kb.learningPaths[lpKey];
  const targetLevel = level === "L0" ? "L1" : level === "L1" ? "L2" : level === "L2" ? "L3" : "L3";
  const upgradeKey = `${level}_to_${targetLevel}`;
  let pathStr = "";
  const pathData = lp?.[upgradeKey];
  if (pathData) {
    pathStr = yaml.dump({
      target: pathData.target,
      estimated_hours: pathData.estimated_hours,
      steps: pathData.steps?.map((s: any) => ({
        order: s.order,
        topic: s.topic,
        goal: s.goal,
        resources: s.resources,
        estimated_hours: s.estimated_hours,
      })),
    }, { lineWidth: 200 });
  }

  // 模拟题（该模块全部，不限 5 道）
  const mockQuestions: any[] = [];
  for (const exam of kb.mockExams) {
    const source = `${exam.year || ""}${exam.district || ""}${exam.exam_type || ""}`;
    for (const q of exam.questions || []) {
      if (q.module !== moduleId) continue;
      mockQuestions.push({ ...q, source });
    }
  }
  const diffOrder: Record<string, number> = { "基础": 0, "中档": 1, "较难": 2, "压轴": 3 };
  mockQuestions.sort((a, b) => (diffOrder[a.difficulty] ?? 1) - (diffOrder[b.difficulty] ?? 1));

  let mockStr = "";
  if (mockQuestions.length > 0) {
    mockStr = mockQuestions.map((q) =>
      `- ${q.source} 第${q.id}题（${q.type}，${q.score}分，${q.difficulty}）：${(q.question || "").split("\n")[0].slice(0, 80)}`
    ).join("\n");
  }

  // 真题中该模块相关题号
  let examStr = "";
  const summary = kb.examAnalysis.summary;
  if (summary?.module_frequency) {
    const mf = summary.module_frequency[moduleId] || summary.module_frequency[kbKey];
    if (mf) {
      examStr = yaml.dump(mf, { lineWidth: 200 });
    }
  }

  // 教辅推荐
  let resourceStr = "";
  const recMatrix = kb.resources.workbooks?.recommendation_matrix;
  if (recMatrix) {
    const levelKey = level === "L0" ? "L0_student" : level === "L1" ? "L1_student" : level === "L2" ? "L2_student" : "L3_student";
    const rec = recMatrix[levelKey];
    if (rec) {
      resourceStr = `主力教辅：${rec.primary}\n辅助教辅：${rec.secondary}` +
        (rec.optional ? `\n可选：${rec.optional}` : "") +
        (rec.avoid ? `\n不推荐：${rec.avoid}` : "");
    }
  }

  const timePhase = getTimePhase(weeksUntilExam);
  const drillWeeks = Math.min(2, Math.max(1, Math.floor(weeksUntilExam / 5)));

  // 教材章节索引（供 drill 模式引用）
  const districtCn = district.replace("区", "");
  const useRenjiao = ["海淀", "西城", "东城", "朝阳", "丰台"].includes(districtCn);
  const tbVersion = useRenjiao ? "人教版" : "北京版";
  const tbData = kb.resources.textbooks?.[tbVersion === "人教版" ? "人教版" : "北京版"];
  let drillTextbookStr = "";
  if (tbData?.volumes) {
    const relevantChapters: string[] = [];
    for (const vol of tbData.volumes) {
      for (const ch of vol.key_chapters || []) {
        // 匹配当前模块相关的章节
        const mapsTo = (ch.maps_to_module || "").toLowerCase();
        if (mapsTo.includes(moduleId.toLowerCase()) || mapsTo.includes(moduleName)) {
          relevantChapters.push(`${vol.volume} ${ch.chapter}(${ch.relevance})`);
        }
      }
    }
    if (relevantChapters.length > 0) {
      drillTextbookStr = `\n## 相关教材章节（${tbVersion}）\n${relevantChapters.join("\n")}\n`;
    }
  }

  const system = `你是一位经验丰富的北京中考数学辅导专家，专门帮助学生突破薄弱模块。你拥有完整的真题数据库和${kb.mockExams.length}套各区模考试卷题库。

核心要求：
1. 你现在只关注**${moduleName}**这一个模块，给出精准的专项突破方案
2. 所有建议必须具体到题号、页码、时间——学生拿到就能直接执行。下方提供了教材章节索引，请据此精确引用（如"人教版八下§19.1 一次函数 p.73"）
3. 当前处于${getTimePhaseName(timePhase)}，策略要匹配时间紧迫程度
4. 用分数说话：该模块从${level}提到${targetLevel}，能多拿几分，对应哪些真题题号
5. 输出用 Markdown 格式`;

  const user = `## 模块突破请求

- 模块：**${moduleName}**
- 当前水平：**${level}**（目标升到 ${targetLevel}）
- 所在区：${district}
- 每周可投入：${hoursPerWeek}小时
- 距中考：${weeksUntilExam}周（${getTimePhaseName(timePhase)}）${input.problem ? `\n- 学生自述问题：${input.problem}` : ""}

## 诊断数据

${diagStr}

## 该水平段易错点

${mistakesStr || "暂无数据"}

## 学习路径参考（${level} → ${targetLevel}）

${pathStr || "暂无数据"}

## 可用的模拟题（${mockQuestions.length}道）

${mockStr || "暂无"}

## 真题中该模块的考查规律

${examStr || "暂无"}

## 推荐教辅

${resourceStr || "暂无"}
${drillTextbookStr}
---

请生成一份 **${moduleName}** 模块的 **${drillWeeks}周专项突破计划**，包含：

1. **问题诊断**（3-5行）：该模块在${level}水平的核心问题是什么，丢分点在哪，中考中对应哪些题号和分值

2. **突破路线**（简要）：${drillWeeks}周分几个阶段，每阶段攻克什么

3. **每日详细计划**（${drillWeeks}周，每天）：
   - 时间段 + 任务 + 材料（教材节+页码 / 教辅+题号 / 模拟题+题号）
   - 每天的 ✅ 完成标准
   - 从上面的模拟题库中选题作为练习，直接引用题号
   - 安排"诊断→学习→练习→检测"的循环
   - 最后一天安排过关测试

4. **过关标准**：怎样算突破成功（用真题/模拟题检验，具体到题号）`;

  return { system, user };
}
