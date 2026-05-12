/**
 * 诊断算法模块
 * 根据考生输入，确定性地计算各模块水平等级和时间分配
 */

// 考生输入
export interface StudentInput {
  district: string; // 所在区
  totalScore: number; // 最近一次数学总分（满分100）
  availableHoursPerDay: number; // 每天可用学习时间（小时）
  targetSchoolScore?: number; // 目标校分数线（可选）
  daysUntilExam: number; // 距中考天数
  moduleAssessments: {
    numbersAndExpressions: SelfAssessment;
    equationsAndInequalities: SelfAssessment;
    functions: SelfAssessment;
    triangles: SelfAssessment;
    circles: SelfAssessment;
    statisticsAndProbability: SelfAssessment;
    geometryComprehensive: SelfAssessment;
  };
}

export type SelfAssessment = "很差" | "薄弱" | "还行" | "不错" | "擅长" | "不确定";

export type Level = "L0" | "L1" | "L2" | "L3";

// 诊断结果
export interface DiagnosisResult {
  totalScore: number;
  estimatedTotalLevel: string;
  modules: ModuleDiagnosis[];
  timeAllocation: TimeAllocation[];
  targetScore: number;
  potentialGain: number;
  totalWeeklyHours: number;
  weeksUntilExam: number;
}

export interface ModuleDiagnosis {
  id: string;
  name: string;
  level: Level;
  levelName: string;
  examWeight: string;
  typicalScore: string;
  currentEstimatedScore: number;
  targetLevel: Level;
  potentialGain: number;
  priority: number; // 1=最高优先
}

export interface TimeAllocation {
  moduleId: string;
  moduleName: string;
  percentage: number;
  hoursPerWeek: number;
}

// 自评 → 水平等级映射
function assessmentToLevel(assessment: SelfAssessment, totalScore?: number): Level {
  switch (assessment) {
    case "很差":
      return "L0";
    case "薄弱":
      return "L1";
    case "还行":
      return "L2";
    case "不错":
      return "L2";
    case "擅长":
      return "L3";
    case "不确定":
      // 基于总分推算水平
      return estimateLevelFromScore(totalScore || 60);
  }
}

// 基于总分推算模块水平（当学生选"不确定"时使用）
function estimateLevelFromScore(totalScore: number): Level {
  if (totalScore >= 85) return "L2";      // 85+ → 基本熟练
  if (totalScore >= 70) return "L1";      // 70-84 → 概念模糊偏上
  if (totalScore >= 55) return "L1";      // 55-69 → 概念模糊
  return "L0";                             // <55 → 基础薄弱
}

// 水平等级 → 预估得分率
function levelToScoreRate(level: Level): number {
  switch (level) {
    case "L0":
      return 0.3;
    case "L1":
      return 0.55;
    case "L2":
      return 0.75;
    case "L3":
      return 0.92;
  }
}

// 各模块在中考中的分值权重（满分100分中的占比）
const MODULE_WEIGHTS: Record<string, { name: string; maxScore: number; examWeight: string; typicalScore: string }> = {
  numbersAndExpressions: { name: "数与式", maxScore: 16, examWeight: "★★★", typicalScore: "10-16分" },
  equationsAndInequalities: { name: "方程与不等式", maxScore: 12, examWeight: "★★★", typicalScore: "8-12分" },
  functions: { name: "函数", maxScore: 22, examWeight: "★★★", typicalScore: "16-22分" },
  triangles: { name: "三角形", maxScore: 16, examWeight: "★★★", typicalScore: "12-18分" },
  circles: { name: "圆", maxScore: 8, examWeight: "★★", typicalScore: "6-8分" },
  statisticsAndProbability: { name: "统计与概率", maxScore: 12, examWeight: "★★★", typicalScore: "8-12分" },
  geometryComprehensive: { name: "几何综合/压轴", maxScore: 14, examWeight: "★★★", typicalScore: "7-14分" },
};

// 升级难度系数（从当前level升到下一个level的难度）
function upgradeDifficulty(fromLevel: Level): number {
  switch (fromLevel) {
    case "L0":
      return 1.0; // 最容易提升
    case "L1":
      return 1.5;
    case "L2":
      return 2.5;
    case "L3":
      return 10; // 已经是最高，几乎无提升空间
  }
}

// 下一个等级
function nextLevel(level: Level): Level {
  switch (level) {
    case "L0":
      return "L1";
    case "L1":
      return "L2";
    case "L2":
      return "L3";
    case "L3":
      return "L3";
  }
}

function levelName(level: Level): string {
  switch (level) {
    case "L0":
      return "基础薄弱";
    case "L1":
      return "概念模糊";
    case "L2":
      return "基本熟练";
    case "L3":
      return "熟练精通";
  }
}

export function diagnose(input: StudentInput): DiagnosisResult {
  const weeksUntilExam = Math.floor(input.daysUntilExam / 7);
  const totalWeeklyHours = input.availableHoursPerDay * 7;

  // 1. 诊断各模块水平
  const assessments = input.moduleAssessments;
  const moduleEntries = Object.entries(assessments) as [string, SelfAssessment][];

  const modules: ModuleDiagnosis[] = moduleEntries.map(([key, assessment]) => {
    const level = assessmentToLevel(assessment, input.totalScore);
    const weight = MODULE_WEIGHTS[key];
    const currentScore = Math.round(weight.maxScore * levelToScoreRate(level));
    const targetLvl = nextLevel(level);
    const targetScore = Math.round(weight.maxScore * levelToScoreRate(targetLvl));
    const gain = targetScore - currentScore;

    return {
      id: key,
      name: weight.name,
      level,
      levelName: levelName(level),
      examWeight: weight.examWeight,
      typicalScore: weight.typicalScore,
      currentEstimatedScore: currentScore,
      targetLevel: targetLvl,
      potentialGain: Math.max(gain, 0),
      priority: 0, // 后面计算
    };
  });

  // 2. 计算提分优先级（边际收益 = 预期提分 / 难度系数）
  const modulesWithROI = modules.map((m) => ({
    ...m,
    roi: m.potentialGain / upgradeDifficulty(m.level),
  }));

  // 按 ROI 排序
  modulesWithROI.sort((a, b) => b.roi - a.roi);
  modulesWithROI.forEach((m, i) => {
    m.priority = i + 1;
  });

  // 3. 计算时间分配（基于 ROI 的加权分配）
  const totalROI = modulesWithROI.reduce((sum, m) => sum + m.roi, 0);
  const timeAllocation: TimeAllocation[] = modulesWithROI.map((m) => {
    const pct = totalROI > 0 ? Math.round((m.roi / totalROI) * 100) : Math.round(100 / modules.length);
    return {
      moduleId: m.id,
      moduleName: m.name,
      percentage: pct,
      hoursPerWeek: Math.round((pct / 100) * totalWeeklyHours * 10) / 10,
    };
  });

  // 修正百分比总和为100
  const pctSum = timeAllocation.reduce((s, t) => s + t.percentage, 0);
  if (pctSum !== 100 && timeAllocation.length > 0) {
    timeAllocation[0].percentage += 100 - pctSum;
    timeAllocation[0].hoursPerWeek = Math.round((timeAllocation[0].percentage / 100) * totalWeeklyHours * 10) / 10;
  }

  // 4. 计算总分和目标
  const currentTotal = modules.reduce((s, m) => s + m.currentEstimatedScore, 0);
  const potentialGain = modules.reduce((s, m) => s + m.potentialGain, 0);
  const targetScore = input.targetSchoolScore || Math.min(currentTotal + potentialGain, 100);

  return {
    totalScore: input.totalScore,
    estimatedTotalLevel:
      input.totalScore >= 90 ? "优秀" : input.totalScore >= 75 ? "良好" : input.totalScore >= 60 ? "及格" : "待提高",
    modules: modulesWithROI,
    timeAllocation,
    targetScore,
    potentialGain,
    totalWeeklyHours,
    weeksUntilExam,
  };
}
