/**
 * 知识库读取模块
 * 从 YAML 文件中读取结构化知识数据
 */
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

const KB_ROOT = path.join(process.cwd(), "..", "knowledge-base");

function readYaml(relativePath: string): any {
  const filePath = path.join(KB_ROOT, relativePath);
  const content = fs.readFileSync(filePath, "utf-8");
  return yaml.load(content);
}

// 缓存已读取的知识库数据
let cachedKB: KnowledgeBase | null = null;

export interface KnowledgeBase {
  policy: any;
  districts: Record<string, any>;
  examSpec: any;
  questionTypes: any;
  weightAnalysis: any;
  curriculum: any;
  diagnostics: Record<string, any>;
  learningPaths: Record<string, any>;
  resources: {
    textbooks: any;
    workbooks: any;
    onlinePlatforms: any;
    examPapers: any;
  };
  // 易错点
  commonMistakes: Record<string, any>;
  // 模拟题（一模/二模）
  mockExams: any[];
  // 真题分析和录取分数线
  examAnalysis: {
    summary: any;
    yearly: Record<string, any>;
  };
  admission: {
    scoringSystem: any;
    districts: Record<string, any>;
    mathTargetMapping: any;
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

export function loadKnowledgeBase(): KnowledgeBase {
  if (cachedKB) return cachedKB;

  cachedKB = {
    policy: readYaml("regions/beijing/policy.yaml"),
    districts: {
      haidian: readYaml("regions/beijing/districts/haidian.yaml"),
      xicheng: readYaml("regions/beijing/districts/xicheng.yaml"),
      dongcheng: readYaml("regions/beijing/districts/dongcheng.yaml"),
      chaoyang: readYaml("regions/beijing/districts/chaoyang.yaml"),
    },
    examSpec: readYaml("subjects/math/beijing/exam-spec.yaml"),
    questionTypes: readYaml("subjects/math/beijing/question-types.yaml"),
    weightAnalysis: readYaml("subjects/math/beijing/weight-analysis.yaml"),
    curriculum: readYaml("subjects/math/curriculum.yaml"),
    diagnostics: {
      "numbers-and-expressions": readYaml("diagnostics/math/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYaml("diagnostics/math/equations-and-inequalities.yaml"),
      functions: readYaml("diagnostics/math/functions.yaml"),
      triangles: readYaml("diagnostics/math/triangles.yaml"),
      quadrilaterals: readYaml("diagnostics/math/quadrilaterals.yaml"),
      circles: readYaml("diagnostics/math/circles.yaml"),
      "geometry-comprehensive": readYaml("diagnostics/math/geometry-comprehensive.yaml"),
      "statistics-and-probability": readYaml("diagnostics/math/statistics-and-probability.yaml"),
    },
    learningPaths: {
      "numbers-and-expressions": readYaml("learning-paths/math/beijing/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYaml("learning-paths/math/beijing/equations-and-inequalities.yaml"),
      functions: readYaml("learning-paths/math/beijing/functions.yaml"),
      triangles: readYaml("learning-paths/math/beijing/triangles.yaml"),
      "quadrilaterals-and-circles": readYaml("learning-paths/math/beijing/quadrilaterals-and-circles.yaml"),
      "statistics-and-probability": readYaml("learning-paths/math/beijing/statistics-and-probability.yaml"),
      "geometry-comprehensive": readYaml("learning-paths/math/beijing/geometry-comprehensive.yaml"),
    },
    resources: {
      textbooks: readYaml("resources/textbooks.yaml"),
      workbooks: readYaml("resources/workbooks.yaml"),
      onlinePlatforms: readYaml("resources/online-platforms.yaml"),
      examPapers: readYaml("resources/exam-papers.yaml"),
    },
    mockExams: loadMockExams(),
    commonMistakes: {
      "numbers-and-expressions": readYaml("common-mistakes/math/numbers-and-expressions.yaml"),
      "equations-and-inequalities": readYaml("common-mistakes/math/equations-and-inequalities.yaml"),
      functions: readYaml("common-mistakes/math/functions.yaml"),
      triangles: readYaml("common-mistakes/math/triangles.yaml"),
      quadrilaterals: readYaml("common-mistakes/math/quadrilaterals.yaml"),
      circles: readYaml("common-mistakes/math/circles.yaml"),
      "geometry-comprehensive": readYaml("common-mistakes/math/geometry-comprehensive.yaml"),
      "statistics-and-probability": readYaml("common-mistakes/math/statistics-and-probability.yaml"),
    },
    examAnalysis: {
      summary: readYaml("exam-analysis/math/beijing/summary.yaml"),
      yearly: {
        "2025": readYaml("exam-analysis/math/beijing/2025.yaml"),
        "2024": readYaml("exam-analysis/math/beijing/2024.yaml"),
        "2023": readYaml("exam-analysis/math/beijing/2023.yaml"),
        "2022": readYaml("exam-analysis/math/beijing/2022.yaml"),
        "2021": readYaml("exam-analysis/math/beijing/2021.yaml"),
      },
    },
    admission: {
      scoringSystem: readYaml("admission/beijing/scoring-system.yaml"),
      districts: {
        chaoyang: readYaml("admission/beijing/chaoyang.yaml"),
        haidian: readYaml("admission/beijing/haidian.yaml"),
        xicheng: readYaml("admission/beijing/xicheng.yaml"),
        dongcheng: readYaml("admission/beijing/dongcheng.yaml"),
      },
      mathTargetMapping: readYaml("admission/beijing/math-target-mapping.yaml"),
    },
  };

  return cachedKB;
}
