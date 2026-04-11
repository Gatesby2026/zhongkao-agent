/**
 * Prompt 构建模块
 * 根据诊断结果 + 知识库片段，组装发给 LLM 的 prompt
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

export function buildPrompt(
  diagnosis: DiagnosisResult,
  kb: KnowledgeBase,
  district: string
): { system: string; user: string } {
  // 筛选需要提升的模块（排除 L3 的）
  const modulesToImprove = diagnosis.modules
    .filter((m) => m.level !== "L3")
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 5); // 最多取前5个优先模块

  // 组装每个模块的知识库片段
  const moduleContexts = modulesToImprove.map((m) => {
    const kbKey = MODULE_TO_KB_KEY[m.id];
    const lpKey = MODULE_TO_LP_KEY[m.id];
    const diag = kb.diagnostics[kbKey];
    const lp = kb.learningPaths[lpKey];

    // 找到对应的升级路径
    const upgradeKey = `${m.level}_to_${m.targetLevel}`;
    let pathData = null;

    if (lp) {
      // 学习路径文件中的key格式可能不同，尝试多种
      pathData = lp[upgradeKey] || lp[`${m.id}_${upgradeKey}`];
      // 针对四边形和圆的特殊处理
      if (!pathData && lpKey === "quadrilaterals-and-circles") {
        pathData =
          lp[`circles_${upgradeKey}`] ||
          lp[`quadrilaterals_${upgradeKey}`] ||
          lp[upgradeKey];
      }
    }

    // 找到诊断标准中对应level的描述
    let levelDesc = "";
    if (diag?.levels) {
      const lvl = diag.levels.find((l: any) => l.id === m.level);
      if (lvl) {
        levelDesc = `当前水平描述：${lvl.description}\n典型表现：${(lvl.signals || []).join("；")}`;
      }
    }

    return `
### ${m.name}（当前 ${m.level} - ${m.levelName}，目标 ${m.targetLevel}，优先级 #${m.priority}）
预计提分：${m.potentialGain}分
${levelDesc}

${pathData ? `学习路径：\n${yaml.dump(pathData, { lineWidth: 200 }).slice(0, 2000)}` : "（使用通用提升建议）"}
`;
  }).join("\n");

  // 获取区域特色
  const districtKey = district.replace("区", "").toLowerCase();
  const districtMap: Record<string, string> = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng", "朝阳": "chaoyang",
  };
  const dKey = districtMap[districtKey] || "haidian";
  const districtInfo = kb.districts[dKey];

  // 时间分配
  const timeAllocStr = diagnosis.timeAllocation
    .filter((t) => t.percentage > 0)
    .map((t) => `${t.moduleName}：${t.percentage}%（每周${t.hoursPerWeek}小时）`)
    .join("\n");

  // 教辅推荐矩阵
  const workbookRec = kb.resources.workbooks?.recommendation_matrix;

  const system = `你是一位经验丰富的北京中考数学辅导专家，已经帮助数百名学生成功备考。

你的任务是根据学生的诊断数据和知识库中的学习路径，生成一份详细的、可执行的个性化学习规划。

要求：
1. 语气亲切但专业，像一个经验丰富的班主任在跟学生和家长谈话
2. 所有建议必须具体到"用什么书的哪个部分、怎么用、做多少题"
3. 过关标准必须可量化（"连续做对10题"而非"掌握即可"）
4. 先讲策略（为什么这么安排），再讲具体计划
5. 适当鼓励，但不要空洞——用数据说话（"你的函数从L0提到L1，预计可以提8-12分"）
6. 注意该生所在区（${district}）的特点
7. 输出用 Markdown 格式，结构清晰`;

  const user = `## 学生基本情况

- 所在区：${district}
- 数学成绩：${diagnosis.totalScore}/100（${diagnosis.estimatedTotalLevel}）
- 每周可用学习时间：${diagnosis.totalWeeklyHours}小时
- 距中考：${diagnosis.weeksUntilExam}周
- 目标分数：${diagnosis.targetScore}分

## 各模块诊断结果

${diagnosis.modules.map((m) => `| ${m.name} | ${m.level}(${m.levelName}) | 预估${m.currentEstimatedScore}分 | 可提${m.potentialGain}分 | 优先级#${m.priority} |`).join("\n")}

## 建议的时间分配

${timeAllocStr}

## 各模块的知识库学习路径

${moduleContexts}

## 所在区特色

${districtInfo ? yaml.dump(districtInfo.math_features || {}, { lineWidth: 200 }) : "暂无区级特色数据"}

---

请基于以上数据，为这位同学生成一份完整的学习规划报告，包含：

1. **整体分析**（2-3段）：当前水平总结、提分空间分析、核心策略
2. **各模块详细计划**（按优先级排列，每个模块包含）：
   - 当前问题诊断
   - 具体学习步骤（第1步做什么→第2步做什么）
   - 推荐资源和使用方法
   - 过关标准
   - 预计耗时
3. **周计划模板**（给出第1周和第2周的具体安排示例）
4. **注意事项**（3-5条关键提醒）`;

  return { system, user };
}
