/**
 * 快速测评评分引擎
 * 根据 10 道选择题的作答结果，精确诊断 7 模块水平
 */

export type Level = "L0" | "L1" | "L2" | "L3";

export interface QuestionResult {
  questionId: number;
  answer: string | null; // A/B/C/D 或 null（超时）
  timeSpent: number; // 秒
}

export interface ModuleAssessment {
  moduleId: string;
  moduleName: string;
  level: Level;
  confidence: "high" | "medium" | "low"; // 置信度（该模块有几道题）
  weaknesses: string[]; // 检测到的具体弱点
  subTopics: { name: string; levelSignal: Level }[];
}

export interface AssessmentResult {
  totalCorrect: number;
  totalQuestions: number;
  estimatedScore: number; // 映射到百分制
  modules: ModuleAssessment[];
  // 转换为 /plan 页面需要的 moduleAssessments 格式
  moduleAssessments: Record<string, string>;
}

// 题目元数据（与 YAML 对应，硬编码以避免服务端读取）
interface QuestionMeta {
  id: number;
  module: string;
  difficulty: "基础" | "中档" | "较难";
  correct: string;
  correctSignal: Level;
  diagnosisMap: Record<string, { levelSignal: Level; weakness: string; subTopic: string }>;
}

const MODULE_NAMES: Record<string, string> = {
  numbersAndExpressions: "数与式",
  equationsAndInequalities: "方程与不等式",
  functions: "函数",
  triangles: "三角形",
  circles: "圆",
  statisticsAndProbability: "统计与概率",
  geometryComprehensive: "几何综合",
};

const QUESTIONS: QuestionMeta[] = [
  {
    id: 1, module: "numbersAndExpressions", difficulty: "基础", correct: "B", correctSignal: "L2",
    diagnosisMap: {
      A: { levelSignal: "L1", weakness: "平方差公式与完全平方混淆", subTopic: "因式分解-公式法" },
      C: { levelSignal: "L0", weakness: "平方差公式记错", subTopic: "因式分解-公式法" },
      D: { levelSignal: "L0", weakness: "因式分解基础概念缺失", subTopic: "因式分解" },
      timeout: { levelSignal: "L0", weakness: "基础运算速度不足", subTopic: "因式分解" },
    },
  },
  {
    id: 2, module: "equationsAndInequalities", difficulty: "基础", correct: "A", correctSignal: "L2",
    diagnosisMap: {
      B: { levelSignal: "L1", weakness: "因式分解后符号搞反", subTopic: "一元二次方程-因式分解法" },
      C: { levelSignal: "L1", weakness: "凑数错误", subTopic: "一元二次方程-因式分解法" },
      D: { levelSignal: "L0", weakness: "一元二次方程解法未掌握", subTopic: "一元二次方程" },
      timeout: { levelSignal: "L0", weakness: "一元二次方程不熟练", subTopic: "一元二次方程" },
    },
  },
  {
    id: 3, module: "statisticsAndProbability", difficulty: "基础", correct: "B", correctSignal: "L2",
    diagnosisMap: {
      A: { levelSignal: "L1", weakness: "未排序直接取中间数", subTopic: "中位数-排序" },
      C: { levelSignal: "L1", weakness: "偶数个数据取平均值方法错", subTopic: "中位数-偶数个数据" },
      D: { levelSignal: "L0", weakness: "中位数概念不理解", subTopic: "统计基础" },
      timeout: { levelSignal: "L0", weakness: "统计基础概念缺失", subTopic: "统计基础" },
    },
  },
  {
    id: 4, module: "functions", difficulty: "中档", correct: "B", correctSignal: "L2",
    diagnosisMap: {
      A: { levelSignal: "L1", weakness: "k<0图象方向理解不准", subTopic: "一次函数-k和b的几何意义" },
      C: { levelSignal: "L0", weakness: "k和b对图象影响不理解", subTopic: "一次函数-图象与性质" },
      D: { levelSignal: "L0", weakness: "一次函数图象基础缺失", subTopic: "一次函数" },
      timeout: { levelSignal: "L0", weakness: "函数图象判断不熟练", subTopic: "一次函数" },
    },
  },
  {
    id: 5, module: "triangles", difficulty: "中档", correct: "C", correctSignal: "L2",
    diagnosisMap: {
      A: { levelSignal: "L1", weakness: "SAS判定理解不牢", subTopic: "全等三角形-判定条件" },
      B: { levelSignal: "L1", weakness: "ASA判定理解不牢", subTopic: "全等三角形-判定条件" },
      D: { levelSignal: "L0", weakness: "全等三角形判定条件未掌握", subTopic: "全等三角形" },
      timeout: { levelSignal: "L0", weakness: "全等三角形判定不熟练", subTopic: "全等三角形" },
    },
  },
  {
    id: 6, module: "equationsAndInequalities", difficulty: "中档", correct: "A", correctSignal: "L2",
    diagnosisMap: {
      B: { levelSignal: "L1", weakness: "解出x=1但未验根（增根）", subTopic: "分式方程-验根" },
      C: { levelSignal: "L1", weakness: "因式分解错误导致解错", subTopic: "分式方程-去分母" },
      D: { levelSignal: "L0", weakness: "分式方程解法未掌握", subTopic: "分式方程" },
      timeout: { levelSignal: "L1", weakness: "分式方程运算速度不足", subTopic: "分式方程" },
    },
  },
  {
    id: 7, module: "circles", difficulty: "中档", correct: "A", correctSignal: "L2",
    diagnosisMap: {
      B: { levelSignal: "L1", weakness: "勾股定理列式错误", subTopic: "切线-勾股定理" },
      C: { levelSignal: "L0", weakness: "切线⊥半径性质未建立", subTopic: "切线性质" },
      D: { levelSignal: "L0", weakness: "圆的切线相关知识缺失", subTopic: "圆" },
      timeout: { levelSignal: "L0", weakness: "圆的计算不熟练", subTopic: "圆" },
    },
  },
  {
    id: 8, module: "functions", difficulty: "较难", correct: "A", correctSignal: "L3",
    diagnosisMap: {
      B: { levelSignal: "L1", weakness: "配方法常数项计算错误", subTopic: "二次函数-配方法" },
      C: { levelSignal: "L0", weakness: "顶点公式x=-b/2a符号搞反", subTopic: "二次函数-顶点坐标" },
      D: { levelSignal: "L1", weakness: "配方法/顶点公式不熟练", subTopic: "二次函数" },
      timeout: { levelSignal: "L1", weakness: "二次函数计算速度不足", subTopic: "二次函数" },
    },
  },
  {
    id: 9, module: "geometryComprehensive", difficulty: "较难", correct: "A", correctSignal: "L3",
    diagnosisMap: {
      B: { levelSignal: "L1", weakness: "未识别旋转后等腰直角三角形", subTopic: "旋转-等腰直角三角形" },
      C: { levelSignal: "L0", weakness: "旋转变换性质不理解", subTopic: "旋转变换" },
      D: { levelSignal: "L0", weakness: "几何综合题无思路", subTopic: "几何综合" },
      timeout: { levelSignal: "L1", weakness: "旋转类题目分析速度不足", subTopic: "旋转变换" },
    },
  },
  {
    id: 10, module: "functions", difficulty: "较难", correct: "C", correctSignal: "L3",
    diagnosisMap: {
      A: { levelSignal: "L1", weakness: "图象交点找对但不等号方向反", subTopic: "函数图象-不等式" },
      B: { levelSignal: "L1", weakness: "忽略第三象限交点", subTopic: "反比例函数-象限" },
      D: { levelSignal: "L1", weakness: "函数综合方法不熟练", subTopic: "函数综合" },
      timeout: { levelSignal: "L1", weakness: "函数综合分析速度不足", subTopic: "函数综合" },
    },
  },
];

// 题目文本数据（前端展示用）
export const QUESTION_TEXTS = [
  {
    id: 1,
    question: "因式分解：x² - 4 的结果是？",
    options: { A: "(x-2)²", B: "(x+2)(x-2)", C: "(x+4)(x-4)", D: "不会做" },
  },
  {
    id: 2,
    question: "一元二次方程 x² - 5x + 6 = 0 的解是？",
    options: { A: "x₁=2, x₂=3", B: "x₁=-2, x₂=-3", C: "x₁=1, x₂=6", D: "不会做" },
  },
  {
    id: 3,
    question: "数据 3, 5, 2, 8, 7, 1 的中位数是？",
    options: { A: "5", B: "4", C: "4.5", D: "不会做" },
  },
  {
    id: 4,
    question: "一次函数 y = -2x + 3 的图象经过哪些象限？",
    options: { A: "一、二、三象限", B: "一、二、四象限", C: "一、三、四象限", D: "不会做" },
  },
  {
    id: 5,
    question: "△ABC 和 △DEF 中，已知 AB=DE，∠A=∠D，还需补充一个条件使两三角形全等，下列不能补充的是？",
    options: { A: "AC = DF", B: "∠B = ∠E", C: "BC = EF", D: "不会做" },
  },
  {
    id: 6,
    question: "解分式方程 1/(x-1) = 2/(x²-1)，正确的解是？",
    options: { A: "x = 3", B: "x = 1", C: "x = -1", D: "不会做" },
  },
  {
    id: 7,
    question: "PA 是圆O的切线，A为切点，PO交圆O于点B。若 PA=8，PB=4，则圆O的半径是？",
    options: { A: "6", B: "5", C: "4", D: "不会做" },
  },
  {
    id: 8,
    question: "抛物线 y = 2x² - 8x + 5 的顶点坐标是？",
    options: { A: "(2, -3)", B: "(2, 5)", C: "(-2, 29)", D: "不会做" },
  },
  {
    id: 9,
    question: "正方形ABCD中，E是BC上一点，将△ABE绕点B顺时针旋转90°得△CBF，连接EF。若AB=4，BE=3，则EF的长度是？",
    options: { A: "3√2", B: "5", C: "4", D: "不会做" },
  },
  {
    id: 10,
    question: "一次函数 y₁=x+1 和反比例函数 y₂=k/x 交于点A(2,3)，则 y₁>y₂ 的x取值范围是？",
    options: { A: "x<-3 或 0<x<2", B: "x>2 或 x<0", C: "-3<x<0 或 x>2", D: "不会做" },
  },
];

/**
 * 评分引擎：根据答题结果计算各模块水平
 */
export function evaluateAssessment(results: QuestionResult[]): AssessmentResult {
  // 收集每个模块的证据
  const moduleEvidence: Record<string, {
    signals: Level[];
    weaknesses: string[];
    subTopics: { name: string; levelSignal: Level }[];
    correctCount: number;
    totalCount: number;
  }> = {};

  // 初始化所有模块
  for (const moduleId of Object.keys(MODULE_NAMES)) {
    moduleEvidence[moduleId] = {
      signals: [],
      weaknesses: [],
      subTopics: [],
      correctCount: 0,
      totalCount: 0,
    };
  }

  let totalCorrect = 0;

  for (const result of results) {
    const q = QUESTIONS.find((q) => q.id === result.questionId);
    if (!q) continue;

    const evidence = moduleEvidence[q.module];
    evidence.totalCount++;

    if (result.answer === null || result.timeSpent > 60) {
      // 超时
      const diag = q.diagnosisMap.timeout;
      evidence.signals.push(diag.levelSignal);
      evidence.weaknesses.push(diag.weakness);
      evidence.subTopics.push({ name: diag.subTopic, levelSignal: diag.levelSignal });
    } else if (result.answer === q.correct) {
      // 答对
      totalCorrect++;
      evidence.correctCount++;
      evidence.signals.push(q.correctSignal);
    } else {
      // 答错 — 查错因
      const diag = q.diagnosisMap[result.answer];
      if (diag) {
        evidence.signals.push(diag.levelSignal);
        evidence.weaknesses.push(diag.weakness);
        evidence.subTopics.push({ name: diag.subTopic, levelSignal: diag.levelSignal });
      }
    }
  }

  // 计算每个模块的最终水平
  const modules: ModuleAssessment[] = Object.entries(moduleEvidence).map(([moduleId, ev]) => {
    let level: Level;
    let confidence: "high" | "medium" | "low";

    if (ev.totalCount === 0) {
      // 该模块没有题目（不应该发生）
      level = "L1";
      confidence = "low";
    } else if (ev.totalCount === 1) {
      // 只有 1 道题
      level = ev.signals[0] || "L1";
      confidence = "low";
    } else {
      // 多道题 — 取加权平均
      const levelValues: Record<Level, number> = { L0: 0, L1: 1, L2: 2, L3: 3 };
      const avg = ev.signals.reduce((sum, l) => sum + levelValues[l], 0) / ev.signals.length;

      if (avg >= 2.5) level = "L3";
      else if (avg >= 1.5) level = "L2";
      else if (avg >= 0.5) level = "L1";
      else level = "L0";

      confidence = ev.totalCount >= 3 ? "high" : "medium";
    }

    return {
      moduleId,
      moduleName: MODULE_NAMES[moduleId],
      level,
      confidence,
      weaknesses: ev.weaknesses,
      subTopics: ev.subTopics,
    };
  });

  // 映射为 /plan 页面的 moduleAssessments 格式
  const levelToAssessment: Record<Level, string> = {
    L0: "很差",
    L1: "薄弱",
    L2: "还行",
    L3: "擅长",
  };

  const moduleAssessments: Record<string, string> = {};
  for (const m of modules) {
    moduleAssessments[m.moduleId] = levelToAssessment[m.level];
  }

  // 估算百分制分数
  const estimatedScore = Math.round((totalCorrect / 10) * 100 * 0.85 + 15); // 简单线性映射

  return {
    totalCorrect,
    totalQuestions: 10,
    estimatedScore: Math.min(estimatedScore, 100),
    modules,
    moduleAssessments,
  };
}
