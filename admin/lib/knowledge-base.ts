/**
 * 知识库读取模块
 * 从 YAML 文件中读取结构化知识数据
 * 支持多科目：数学、语文、英语、物理、道法、体育
 */
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

const KB_ROOT = path.join(process.cwd(), "..", "knowledge-base");

function readYaml(relativePath: string): any {
  const filePath = path.join(KB_ROOT, relativePath);
  if (!fs.existsSync(filePath)) return null;
  const content = fs.readFileSync(filePath, "utf-8");
  return yaml.load(content);
}

function readYamlRequired(relativePath: string): any {
  const filePath = path.join(KB_ROOT, relativePath);
  const content = fs.readFileSync(filePath, "utf-8");
  return yaml.load(content);
}

// 缓存已读取的知识库数据
let cachedKB: KnowledgeBase | null = null;

// 单科目的考试大纲与分析数据
export interface SubjectData {
  curriculum: any;
  examSpec: any;
  questionTypes: any;
  weightAnalysis: any;
  examAnalysis: {
    summary: any;
    yearly: Record<string, any>;
  };
}

// 体育科目特殊结构
export interface PEData {
  examSpec: any;
  scoringStandards: any;
  trainingPlans: any;
}

export interface KnowledgeBase {
  // 跨科目共用
  policy: any;
  districts: Record<string, any>;
  resources: {
    textbooks: any;
    workbooks: any;
    onlinePlatforms: any;
    examPapers: any;
  };
  admission: {
    scoringSystem: any;
    districts: Record<string, any>;
    mathTargetMapping: any;
  };

  // 数学（保持向后兼容）
  examSpec: any;
  questionTypes: any;
  weightAnalysis: any;
  curriculum: any;
  diagnostics: Record<string, any>;
  learningPaths: Record<string, any>;
  commonMistakes: Record<string, any>;
  mockExams: any[];
  examAnalysis: {
    summary: any;
    yearly: Record<string, any>;
  };

  // 多科目数据
  subjects: {
    chinese: SubjectData;
    english: SubjectData;
    physics: SubjectData;
    politics: SubjectData;
    pe: PEData;
  };
}

function loadMockExams(): any[] {
  const mockDir = path.join(KB_ROOT, "mock-exams", "math", "beijing");
  if (!fs.existsSync(mockDir)) return [];
  return fs
    .readdirSync(mockDir)
    .filter((f) => f.endsWith(".yaml"))
    .map((f) => readYaml(path.join("mock-exams", "math", "beijing", f)));
}

function loadSubjectData(subjectDir: string): SubjectData {
  return {
    curriculum: readYaml(`subjects/${subjectDir}/curriculum.yaml`),
    examSpec: readYaml(`subjects/${subjectDir}/beijing/exam-spec.yaml`),
    questionTypes: readYaml(`subjects/${subjectDir}/beijing/question-types.yaml`),
    weightAnalysis: readYaml(`subjects/${subjectDir}/beijing/weight-analysis.yaml`),
    examAnalysis: loadSubjectExamAnalysis(subjectDir),
  };
}

function loadSubjectExamAnalysis(subjectDir: string): { summary: any; yearly: Record<string, any> } {
  const yearly: Record<string, any> = {};
  for (const year of ["2021", "2022", "2023", "2024", "2025"]) {
    const data = readYaml(`exam-analysis/${subjectDir}/beijing/${year}.yaml`);
    if (data) yearly[year] = data;
  }
  return {
    summary: readYaml(`exam-analysis/${subjectDir}/beijing/summary.yaml`),
    yearly,
  };
}

function loadPEData(): PEData {
  return {
    examSpec: readYaml("subjects/pe/beijing/exam-spec.yaml"),
    scoringStandards: readYaml("subjects/pe/beijing/scoring-standards.yaml"),
    trainingPlans: readYaml("subjects/pe/beijing/training-plans.yaml"),
  };
}

export function loadKnowledgeBase(): KnowledgeBase {
  if (cachedKB) return cachedKB;

  cachedKB = {
    // 跨科目共用
    policy: readYamlRequired("regions/beijing/policy.yaml"),
    districts: {
      haidian: readYamlRequired("regions/beijing/districts/haidian.yaml"),
      xicheng: readYamlRequired("regions/beijing/districts/xicheng.yaml"),
      dongcheng: readYamlRequired("regions/beijing/districts/dongcheng.yaml"),
      chaoyang: readYamlRequired("regions/beijing/districts/chaoyang.yaml"),
    },
    resources: {
      textbooks: readYamlRequired("resources/textbooks.yaml"),
      workbooks: readYamlRequired("resources/workbooks.yaml"),
      onlinePlatforms: readYamlRequired("resources/online-platforms.yaml"),
      examPapers: readYamlRequired("resources/exam-papers.yaml"),
    },
    admission: {
      scoringSystem: readYamlRequired("admission/beijing/scoring-system.yaml"),
      districts: {
        chaoyang: readYamlRequired("admission/beijing/chaoyang.yaml"),
        haidian: readYamlRequired("admission/beijing/haidian.yaml"),
        xicheng: readYamlRequired("admission/beijing/xicheng.yaml"),
        dongcheng: readYamlRequired("admission/beijing/dongcheng.yaml"),
      },
      mathTargetMapping: readYamlRequired("admission/beijing/math-target-mapping.yaml"),
    },

    // 数学（保持向后兼容，原有代码不需要改动）
    examSpec: readYamlRequired("subjects/math/beijing/exam-spec.yaml"),
    questionTypes: readYamlRequired("subjects/math/beijing/question-types.yaml"),
    weightAnalysis: readYamlRequired("subjects/math/beijing/weight-analysis.yaml"),
    curriculum: readYamlRequired("subjects/math/curriculum.yaml"),
    diagnostics: {
      "numbers-and-expressions": readYamlRequired("diagnostics/math/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYamlRequired("diagnostics/math/equations-and-inequalities.yaml"),
      functions: readYamlRequired("diagnostics/math/functions.yaml"),
      triangles: readYamlRequired("diagnostics/math/triangles.yaml"),
      quadrilaterals: readYamlRequired("diagnostics/math/quadrilaterals.yaml"),
      circles: readYamlRequired("diagnostics/math/circles.yaml"),
      "geometry-comprehensive": readYamlRequired("diagnostics/math/geometry-comprehensive.yaml"),
      "statistics-and-probability": readYamlRequired("diagnostics/math/statistics-and-probability.yaml"),
    },
    learningPaths: {
      "numbers-and-expressions": readYamlRequired("learning-paths/math/beijing/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYamlRequired("learning-paths/math/beijing/equations-and-inequalities.yaml"),
      functions: readYamlRequired("learning-paths/math/beijing/functions.yaml"),
      triangles: readYamlRequired("learning-paths/math/beijing/triangles.yaml"),
      "quadrilaterals-and-circles": readYamlRequired("learning-paths/math/beijing/quadrilaterals-and-circles.yaml"),
      "statistics-and-probability": readYamlRequired("learning-paths/math/beijing/statistics-and-probability.yaml"),
      "geometry-comprehensive": readYamlRequired("learning-paths/math/beijing/geometry-comprehensive.yaml"),
    },
    commonMistakes: {
      "numbers-and-expressions": readYamlRequired("common-mistakes/math/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYamlRequired("common-mistakes/math/equations-and-inequalities.yaml"),
      functions: readYamlRequired("common-mistakes/math/functions.yaml"),
      triangles: readYamlRequired("common-mistakes/math/triangles.yaml"),
      quadrilaterals: readYamlRequired("common-mistakes/math/quadrilaterals.yaml"),
      circles: readYamlRequired("common-mistakes/math/circles.yaml"),
      "geometry-comprehensive": readYamlRequired("common-mistakes/math/geometry-comprehensive.yaml"),
      "statistics-and-probability": readYamlRequired("common-mistakes/math/statistics-and-probability.yaml"),
    },
    mockExams: loadMockExams(),
    examAnalysis: {
      summary: readYamlRequired("exam-analysis/math/beijing/summary.yaml"),
      yearly: {
        "2025": readYamlRequired("exam-analysis/math/beijing/2025.yaml"),
        "2024": readYamlRequired("exam-analysis/math/beijing/2024.yaml"),
        "2023": readYamlRequired("exam-analysis/math/beijing/2023.yaml"),
        "2022": readYamlRequired("exam-analysis/math/beijing/2022.yaml"),
        "2021": readYamlRequired("exam-analysis/math/beijing/2021.yaml"),
      },
    },

    // 多科目数据
    subjects: {
      chinese: loadSubjectData("chinese"),
      english: loadSubjectData("english"),
      physics: loadSubjectData("physics"),
      politics: loadSubjectData("politics"),
      pe: loadPEData(),
    },
  };

  return cachedKB;
}

/**
 * 按科目名获取科目数据（便捷方法）
 */
export function getSubjectData(kb: KnowledgeBase, subject: string): SubjectData | PEData | null {
  const subjectMap: Record<string, keyof KnowledgeBase["subjects"]> = {
    "语文": "chinese",
    "chinese": "chinese",
    "英语": "english",
    "english": "english",
    "物理": "physics",
    "physics": "physics",
    "道德与法治": "politics",
    "道法": "politics",
    "politics": "politics",
    "体育": "pe",
    "pe": "pe",
  };
  const key = subjectMap[subject];
  if (!key) return null;
  return kb.subjects[key];
}

/**
 * 获取所有科目的考试规格概览（用于总分规划）
 */
export function getAllSubjectsOverview(kb: KnowledgeBase): Array<{
  subject: string;
  fullScore: number;
  examSpec: any;
}> {
  return [
    { subject: "语文", fullScore: 100, examSpec: kb.subjects.chinese.examSpec },
    { subject: "数学", fullScore: 100, examSpec: kb.examSpec },
    { subject: "英语", fullScore: 100, examSpec: kb.subjects.english.examSpec },
    { subject: "物理", fullScore: 80, examSpec: kb.subjects.physics.examSpec },
    { subject: "道德与法治", fullScore: 80, examSpec: kb.subjects.politics.examSpec },
    { subject: "体育", fullScore: 50, examSpec: kb.subjects.pe.examSpec },
  ];
}
