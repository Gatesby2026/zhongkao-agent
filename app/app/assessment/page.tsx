"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { QUESTION_TEXTS, evaluateAssessment, type QuestionResult, type AssessmentResult } from "../../lib/assessment";

const TOTAL_QUESTIONS = 10;
const TIME_LIMIT = 60; // 每题限时（秒）

const DIFFICULTY_COLORS: Record<string, string> = {
  "基础": "bg-green-100 text-green-700",
  "中档": "bg-yellow-100 text-yellow-700",
  "较难": "bg-red-100 text-red-700",
};

const DIFFICULTIES = ["基础", "基础", "基础", "中档", "中档", "中档", "中档", "较难", "较难", "较难"];

// 通俗化水平描述（家长看得懂）
const LEVEL_LABEL: Record<string, string> = {
  L0: "基础薄弱",
  L1: "需要巩固",
  L2: "掌握不错",
  L3: "掌握很好",
};

// 各模块中考占分估算（北京中考数学 100 分）
const MODULE_EXAM_WEIGHT: Record<string, { min: number; max: number }> = {
  numbersAndExpressions: { min: 10, max: 15 },
  equationsAndInequalities: { min: 10, max: 15 },
  functions: { min: 15, max: 20 },
  triangles: { min: 12, max: 18 },
  circles: { min: 8, max: 12 },
  statisticsAndProbability: { min: 8, max: 10 },
  geometryComprehensive: { min: 12, max: 14 },
};

// 按水平估算提分空间
function estimateGain(level: string, weight: { min: number; max: number }): { min: number; max: number } {
  const range = weight.max - weight.min;
  if (level === "L0") return { min: Math.round(weight.min * 0.5), max: Math.round(weight.max * 0.7) };
  if (level === "L1") return { min: Math.round(range * 0.3), max: Math.round(range * 0.6 + 3) };
  return { min: 0, max: 0 };
}

export default function AssessmentPage() {
  const [stage, setStage] = useState<"intro" | "testing" | "result">("intro");
  const [currentQ, setCurrentQ] = useState(0);
  const [timeLeft, setTimeLeft] = useState(TIME_LIMIT);
  const [results, setResults] = useState<QuestionResult[]>([]);
  const [assessmentResult, setAssessmentResult] = useState<AssessmentResult | null>(null);
  const [startTime, setStartTime] = useState(0);

  // 倒计时
  useEffect(() => {
    if (stage !== "testing") return;
    if (timeLeft <= 0) {
      handleAnswer(null); // 超时
      return;
    }
    const timer = setTimeout(() => setTimeLeft((t) => t - 1), 1000);
    return () => clearTimeout(timer);
  }, [stage, timeLeft, currentQ]);

  const handleAnswer = useCallback(
    (answer: string | null) => {
      const timeSpent = TIME_LIMIT - timeLeft;
      const result: QuestionResult = {
        questionId: currentQ + 1,
        answer,
        timeSpent,
      };
      const newResults = [...results, result];
      setResults(newResults);

      if (currentQ + 1 >= TOTAL_QUESTIONS) {
        // 测评完成
        const assessment = evaluateAssessment(newResults);
        setAssessmentResult(assessment);
        setStage("result");
      } else {
        setCurrentQ(currentQ + 1);
        setTimeLeft(TIME_LIMIT);
        setStartTime(Date.now());
      }
    },
    [currentQ, results, timeLeft]
  );

  const startTest = () => {
    setStage("testing");
    setCurrentQ(0);
    setTimeLeft(TIME_LIMIT);
    setResults([]);
    setStartTime(Date.now());
  };

  // 介绍页
  if (stage === "intro") {
    return (
      <main className="max-w-2xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
            &larr; 返回首页
          </Link>
        </div>
        <div className="text-center mb-8">
          <div className="text-5xl mb-4">📝</div>
          <h1 className="text-3xl font-bold text-gray-900 mb-3">5 分钟快速测评</h1>
          <p className="text-gray-500 mb-6">
            10 道精选题，精确定位你的 7 个模块水平
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <div className="grid grid-cols-3 gap-4 text-center mb-6">
            <div className="bg-blue-50 rounded-lg p-3">
              <div className="text-2xl font-bold text-blue-700">10</div>
              <div className="text-xs text-blue-500">道题</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-3">
              <div className="text-2xl font-bold text-purple-700">5</div>
              <div className="text-xs text-purple-500">分钟</div>
            </div>
            <div className="bg-green-50 rounded-lg p-3">
              <div className="text-2xl font-bold text-green-700">7</div>
              <div className="text-xs text-green-500">模块诊断</div>
            </div>
          </div>

          <div className="space-y-2 text-sm text-gray-600 mb-6">
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span> 每题限时 60 秒，超时自动跳过
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span> 不确定可以选"不会做"，不影响其他模块评估
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span> 测评结果可直接生成个性化学习计划
            </div>
          </div>

          <button
            onClick={startTest}
            className="w-full py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-medium text-lg hover:from-blue-700 hover:to-indigo-700 transition-all shadow-md"
          >
            开始测评
          </button>
        </div>

        <p className="text-center text-xs text-gray-400">
          比自评准 10 倍 · 每个选项都在诊断你的知识点
        </p>
      </main>
    );
  }

  // 测评进行中
  if (stage === "testing") {
    const q = QUESTION_TEXTS[currentQ];
    const diff = DIFFICULTIES[currentQ];
    const progress = ((currentQ) / TOTAL_QUESTIONS) * 100;
    const isUrgent = timeLeft <= 10;

    return (
      <main className="max-w-2xl mx-auto px-4 py-8">
        {/* 进度条 */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-500 mb-2">
            <span>第 {currentQ + 1} / {TOTAL_QUESTIONS} 题</span>
            <span className={`font-mono font-bold ${isUrgent ? "text-red-600 animate-pulse" : "text-gray-600"}`}>
              {timeLeft}s
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* 题目卡片 */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-4">
          <div className="flex items-center gap-2 mb-4">
            <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[diff]}`}>
              {diff}
            </span>
            <span className="text-xs text-gray-400">Q{currentQ + 1}</span>
          </div>

          <h2 className="text-lg font-medium text-gray-900 mb-6 leading-relaxed">
            {q.question}
          </h2>

          {/* 选项 */}
          <div className="space-y-3">
            {Object.entries(q.options).map(([key, text]) => (
              <button
                key={key}
                onClick={() => handleAnswer(key)}
                className={`w-full text-left px-4 py-3 rounded-lg border-2 transition-all ${
                  key === "D"
                    ? "border-gray-200 bg-gray-50 hover:bg-gray-100 text-gray-500"
                    : "border-gray-200 bg-white hover:border-blue-400 hover:bg-blue-50 text-gray-800"
                }`}
              >
                <span className="font-medium text-gray-400 mr-3">{key}.</span>
                {text}
              </button>
            ))}
          </div>
        </div>

        {/* 倒计时进度条 */}
        <div className="w-full bg-gray-100 rounded-full h-1">
          <div
            className={`h-1 rounded-full transition-all duration-1000 ${isUrgent ? "bg-red-500" : "bg-blue-400"}`}
            style={{ width: `${(timeLeft / TIME_LIMIT) * 100}%` }}
          />
        </div>
      </main>
    );
  }

  // 结果页
  if (stage === "result" && assessmentResult) {
    const r = assessmentResult;
    // 按优先级排序（L0 最前，L3 最后）
    const sortedModules = [...r.modules].sort((a, b) => {
      const order = { L0: 0, L1: 1, L2: 2, L3: 3 };
      return order[a.level] - order[b.level];
    });

    // 三组分类：需重点补 / 需巩固 / 掌握不错
    const criticalModules = sortedModules.filter((m) => m.level === "L0");
    const needWorkModules = sortedModules.filter((m) => m.level === "L1");
    const goodModules = sortedModules.filter((m) => m.level === "L2" || m.level === "L3");

    // 计算总提分预期
    const totalGain = [...criticalModules, ...needWorkModules].reduce((sum, m) => {
      const w = MODULE_EXAM_WEIGHT[m.moduleId];
      const g = estimateGain(m.level, w);
      return { min: sum.min + g.min, max: sum.max + g.max };
    }, { min: 0, max: 0 });

    // 薄弱模块的中考总占分
    const weakWeight = [...criticalModules, ...needWorkModules].reduce((sum, m) => {
      const w = MODULE_EXAM_WEIGHT[m.moduleId];
      return { min: sum.min + w.min, max: sum.max + w.max };
    }, { min: 0, max: 0 });

    // 构造跳转到 /plan 的 URL 参数
    const planParams = new URLSearchParams();
    planParams.set("score", String(r.estimatedScore));
    planParams.set("fromAssessment", "1");
    planParams.set("modules", JSON.stringify(r.moduleAssessments));

    return (
      <main className="max-w-2xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
            &larr; 返回首页
          </Link>
        </div>

        {/* 总览 */}
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">📊</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            测评完成！以下是孩子的数学情况
          </h1>
          <p className="text-gray-500">
            答对 {r.totalCorrect}/{r.totalQuestions} 题 · 预估数学 {r.estimatedScore} 分
          </p>
          <p className="text-xs text-amber-600 mt-2 bg-amber-50 inline-block px-3 py-1 rounded-full">
            本次测评仅覆盖数学，其他科目规划基于成绩估算
          </p>
        </div>

        {/* 🔴 需要重点补的模块 */}
        {criticalModules.length > 0 && (
          <div className="bg-red-50 rounded-xl border border-red-200 p-5 mb-4">
            <h3 className="font-semibold text-red-800 mb-1">
              🔴 需要重点补的
            </h3>
            <p className="text-xs text-red-500 mb-4">
              这些模块中考共占约 {criticalModules.reduce((s, m) => s + MODULE_EXAM_WEIGHT[m.moduleId].min, 0)}-{criticalModules.reduce((s, m) => s + MODULE_EXAM_WEIGHT[m.moduleId].max, 0)} 分
            </p>
            <div className="space-y-4">
              {criticalModules.map((m) => {
                const w = MODULE_EXAM_WEIGHT[m.moduleId];
                const g = estimateGain(m.level, w);
                return (
                  <div key={m.moduleId} className="bg-white/70 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-gray-800">{m.moduleName}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">
                        {LEVEL_LABEL[m.level]}
                      </span>
                    </div>
                    {m.weaknesses.length > 0 && (
                      <p className="text-sm text-gray-600 mb-2">
                        情况：{m.weaknesses[0]}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                      <span>中考占比：约 {w.min}-{w.max} 分</span>
                      <span className="text-green-600 font-medium">
                        补上预计多拿 {g.min}-{g.max} 分
                      </span>
                    </div>
                    {m.subTopics.length > 0 && (
                      <p className="text-xs text-gray-400 mt-1">
                        诊断依据：测评中 {m.subTopics.map(t => t.name).join("、")} 相关题目表现
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 🟡 需要巩固的模块 */}
        {needWorkModules.length > 0 && (
          <div className="bg-amber-50 rounded-xl border border-amber-200 p-5 mb-4">
            <h3 className="font-semibold text-amber-800 mb-1">
              🟡 需要巩固的
            </h3>
            <p className="text-xs text-amber-500 mb-4">
              基本掌握但有薄弱点，中考共占约 {needWorkModules.reduce((s, m) => s + MODULE_EXAM_WEIGHT[m.moduleId].min, 0)}-{needWorkModules.reduce((s, m) => s + MODULE_EXAM_WEIGHT[m.moduleId].max, 0)} 分
            </p>
            <div className="space-y-4">
              {needWorkModules.map((m) => {
                const w = MODULE_EXAM_WEIGHT[m.moduleId];
                const g = estimateGain(m.level, w);
                return (
                  <div key={m.moduleId} className="bg-white/70 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-gray-800">{m.moduleName}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                        {LEVEL_LABEL[m.level]}
                      </span>
                    </div>
                    {m.weaknesses.length > 0 && (
                      <p className="text-sm text-gray-600 mb-2">
                        情况：{m.weaknesses[0]}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                      <span>中考占比：约 {w.min}-{w.max} 分</span>
                      {g.max > 0 && (
                        <span className="text-green-600 font-medium">
                          巩固后可多拿 {g.min}-{g.max} 分
                        </span>
                      )}
                    </div>
                    {m.subTopics.length > 0 && (
                      <p className="text-xs text-gray-400 mt-1">
                        诊断依据：测评中 {m.subTopics.map(t => t.name).join("、")} 相关题目表现
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 🟢 掌握不错的模块 */}
        {goodModules.length > 0 && (
          <div className="bg-green-50 rounded-xl border border-green-100 p-5 mb-4">
            <h3 className="font-semibold text-green-800 mb-3">🟢 掌握不错的</h3>
            <div className="flex flex-wrap gap-2">
              {goodModules.map((m) => (
                <span
                  key={m.moduleId}
                  className="px-3 py-1.5 bg-green-100 text-green-700 rounded-full text-sm"
                >
                  {m.moduleName} · {LEVEL_LABEL[m.level]}
                </span>
              ))}
            </div>
            <p className="text-xs text-green-600 mt-3">
              这些模块保持练习即可，不需要额外投入
            </p>
          </div>
        )}

        {/* 总结 + 结果承诺 */}
        <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 p-5 mb-4">
          <h3 className="font-semibold text-indigo-800 mb-3">💡 总结与建议</h3>
          {(criticalModules.length > 0 || needWorkModules.length > 0) ? (
            <>
              <p className="text-sm text-gray-700 mb-2">
                核心策略：先补
                <span className="font-medium text-red-600">
                  {[...criticalModules, ...needWorkModules].map(m => m.moduleName).join("和")}
                </span>
                ，这些模块中考共占约 {weakWeight.min}-{weakWeight.max} 分，投入产出比最高。
              </p>
              <div className="bg-white/70 rounded-lg p-3 mt-3">
                <p className="text-sm font-medium text-indigo-700">
                  按方案执行 4 周，数学预计提升 {totalGain.min}-{totalGain.max} 分
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  前提：每天执行 45 分钟 · 基于 10 题测评诊断，做更多练习后预估会更准确
                </p>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-700">
              各模块掌握情况良好！建议保持练习节奏，关注压轴题和综合题的训练。
            </p>
          )}
        </div>

        {/* CTA */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <h3 className="font-semibold text-gray-800 mb-2">下一步：获取专属提分方案</h3>
          <p className="text-sm text-gray-500 mb-4">
            测评数据已就绪，AI 将根据实际水平（而非自评）生成个性化方案
          </p>
          <div className="flex gap-3">
            <Link
              href={`/plan?${planParams.toString()}`}
              className="flex-1 text-center px-4 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-xl font-medium hover:from-green-700 hover:to-emerald-700 transition-colors"
            >
              生成我的提分方案
            </Link>
            <Link
              href="/drill"
              className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
            >
              先练最弱模块
            </Link>
          </div>
        </div>

        {/* 重新测评 */}
        <div className="text-center">
          <button
            onClick={() => {
              setStage("intro");
              setCurrentQ(0);
              setResults([]);
              setAssessmentResult(null);
            }}
            className="text-sm text-gray-400 hover:text-gray-600 underline"
          >
            重新测评
          </button>
        </div>
      </main>
    );
  }

  return null;
}
