import { getDb } from "./db";

// ============================================================
// 学生画像类型定义
// ============================================================

export type ModuleId =
  | "numbersAndExpressions"
  | "equationsAndInequalities"
  | "functions"
  | "triangles"
  | "circles"
  | "statisticsAndProbability"
  | "geometryComprehensive";

export type LevelSource = "self" | "assessment" | "drill" | "llm";

export interface ModuleProfile {
  level: string;            // "很差" | "薄弱" | "还行" | "不错" | "擅长" | "不确定"
  source: LevelSource;      // 评估来源
  confidence: number;        // 0.0 ~ 1.0
  updatedAt: string;
}

export interface StudentProfile {
  // 基础信息
  district: string;
  school: string;
  grade: string;
  currentScore: number;

  // 目标
  targetSchool: string;
  targetScore: number;
  hoursPerDay: number;

  // 模块评估
  modules: Record<ModuleId, ModuleProfile>;

  // 知识点级掌握（细粒度，Phase 2+）
  knowledgePoints: Record<string, {
    mastery: number;         // 0.0 ~ 1.0
    errorPatterns: string[];
    lastUpdated: string;
  }>;

  // 偏好
  preferences: {
    role: "student" | "parent" | "tutor";
    style: string;
    priority: string;
  };

  // 完整度
  completeness: number;     // 0 ~ 100
}

// ============================================================
// 来源权重 & 置信度映射
// ============================================================

const SOURCE_CONFIDENCE: Record<LevelSource, number> = {
  self: 0.3,
  assessment: 0.6,
  drill: 0.8,
  llm: 0.9,
};

const LEVEL_TO_NUM: Record<string, number> = {
  "很差": 0, "薄弱": 1, "还行": 2, "不错": 3, "擅长": 4, "不确定": -1,
};

// ============================================================
// 画像完整度计算
// ============================================================

export function calculateCompleteness(profile: StudentProfile): number {
  let score = 0;
  const maxScore = 100;

  // 基础信息 (15分)
  if (profile.district) score += 5;
  if (profile.school) score += 5;
  if (profile.currentScore > 0) score += 5;

  // 目标层 (15分)
  if (profile.targetSchool) score += 8;
  if (profile.hoursPerDay > 0) score += 7;

  // 学科能力 (55分) — 核心权重最大
  const moduleIds = Object.keys(profile.modules) as ModuleId[];
  const totalModules = moduleIds.length || 7;
  let moduleScore = 0;
  for (const mid of moduleIds) {
    const m = profile.modules[mid];
    if (m && m.level !== "不确定") {
      moduleScore += m.confidence;
    }
  }
  score += (moduleScore / totalModules) * 55;

  // 行为数据 (15分) — 根据历史记录判断
  // 这部分在读取时从 assessment_records / drill_records 统计
  // 暂时用 preferences 是否填了来近似
  if (profile.preferences?.role) score += 5;
  // 剩余 10 分由调用方根据历史记录补充

  return Math.min(100, Math.round(score));
}

// ============================================================
// 画像 CRUD
// ============================================================

/**
 * 获取用户画像
 */
export function getProfile(userId: number): StudentProfile | null {
  const db = getDb();
  const row = db.prepare(`SELECT * FROM profiles WHERE user_id = ?`).get(userId) as any;
  if (!row) return null;

  const modules = safeJsonParse(row.modules_json, {});
  const knowledgePoints = safeJsonParse(row.knowledge_points_json, {});
  const preferences = safeJsonParse(row.preferences_json, {});

  const profile: StudentProfile = {
    district: row.district || "",
    school: row.school || "",
    grade: row.grade || "初三",
    currentScore: row.current_score || 0,
    targetSchool: row.target_school || "",
    targetScore: row.target_score || 0,
    hoursPerDay: row.hours_per_day || 1.5,
    modules,
    knowledgePoints,
    preferences,
    completeness: row.completeness || 0,
  };

  // 重新计算完整度
  profile.completeness = calculateCompleteness(profile);
  return profile;
}

/**
 * 更新用户画像（部分更新）
 */
export function updateProfile(userId: number, updates: Partial<StudentProfile>): StudentProfile | null {
  const db = getDb();

  // 先获取当前画像
  const current = getProfile(userId);
  if (!current) return null;

  // 合并更新
  const merged = { ...current, ...updates };

  // 如果更新了 modules，合并而不是替换
  if (updates.modules) {
    merged.modules = { ...current.modules, ...updates.modules };
  }
  if (updates.knowledgePoints) {
    merged.knowledgePoints = { ...current.knowledgePoints, ...updates.knowledgePoints };
  }
  if (updates.preferences) {
    merged.preferences = { ...current.preferences, ...updates.preferences };
  }

  // 重新计算完整度
  merged.completeness = calculateCompleteness(merged);

  db.prepare(`
    UPDATE profiles SET
      district = ?,
      school = ?,
      grade = ?,
      current_score = ?,
      target_school = ?,
      target_score = ?,
      hours_per_day = ?,
      modules_json = ?,
      knowledge_points_json = ?,
      preferences_json = ?,
      completeness = ?,
      updated_at = CURRENT_TIMESTAMP
    WHERE user_id = ?
  `).run(
    merged.district,
    merged.school,
    merged.grade,
    merged.currentScore,
    merged.targetSchool,
    merged.targetScore,
    merged.hoursPerDay,
    JSON.stringify(merged.modules),
    JSON.stringify(merged.knowledgePoints),
    JSON.stringify(merged.preferences),
    merged.completeness,
    userId,
  );

  return merged;
}

/**
 * 从测评结果更新模块水平
 */
export function updateModulesFromAssessment(
  userId: number,
  moduleResults: Record<string, { level: string; weaknesses: string[] }>
): void {
  const now = new Date().toISOString();
  const modules: Record<string, ModuleProfile> = {};

  for (const [moduleId, result] of Object.entries(moduleResults)) {
    modules[moduleId as ModuleId] = {
      level: result.level,
      source: "assessment",
      confidence: SOURCE_CONFIDENCE.assessment,
      updatedAt: now,
    };
  }

  updateProfile(userId, { modules: modules as any });
}

/**
 * 从刷题结果微调模块水平
 */
export function updateModuleFromDrill(
  userId: number,
  moduleId: ModuleId,
  correctRate: number
): void {
  const profile = getProfile(userId);
  if (!profile) return;

  const current = profile.modules[moduleId];
  const now = new Date().toISOString();

  // 根据正确率推断 level
  let newLevel: string;
  if (correctRate >= 0.9) newLevel = "擅长";
  else if (correctRate >= 0.75) newLevel = "不错";
  else if (correctRate >= 0.6) newLevel = "还行";
  else if (correctRate >= 0.4) newLevel = "薄弱";
  else newLevel = "很差";

  // 如果已有评估，用指数移动平均融合
  if (current && current.level !== "不确定" && LEVEL_TO_NUM[current.level] >= 0) {
    const alpha = 0.3; // 新数据权重
    const currentNum = LEVEL_TO_NUM[current.level];
    const newNum = LEVEL_TO_NUM[newLevel];
    const blended = currentNum * (1 - alpha) + newNum * alpha;

    // 映射回 level
    if (blended >= 3.5) newLevel = "擅长";
    else if (blended >= 2.5) newLevel = "不错";
    else if (blended >= 1.5) newLevel = "还行";
    else if (blended >= 0.5) newLevel = "薄弱";
    else newLevel = "很差";
  }

  const updatedModule: ModuleProfile = {
    level: newLevel,
    source: "drill",
    confidence: Math.min(1.0, (current?.confidence || 0) + 0.1), // 每次刷题增加置信度
    updatedAt: now,
  };

  updateProfile(userId, {
    modules: { [moduleId]: updatedModule } as any,
  });
}

// ============================================================
// 辅助函数
// ============================================================

function safeJsonParse(str: string, fallback: any): any {
  try {
    return JSON.parse(str || "{}");
  } catch {
    return fallback;
  }
}
