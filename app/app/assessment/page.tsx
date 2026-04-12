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

const LEVEL_COLORS: Record<string, string> = {
  L0: "bg-red-100 text-red-700 border-red-300",
  L1: "bg-orange-100 text-orange-700 border-orange-300",
  L2: "bg-green-100 text-green-700 border-green-300",
  L3: "bg-emerald-100 text-emerald-700 border-emerald-300",
};

const LEVEL_NAMES: Record<string, string> = {
  L0: "基础薄弱",
  L1: "概念模糊",
  L2: "基本熟练",
  L3: "熟练精通",
};

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

    const weakModules = sortedModules.filter((m) => m.level === "L0" || m.level === "L1");
    const strongModules = sortedModules.filter((m) => m.level === "L2" || m.level === "L3");

    // 构造跳转到 /plan 的 URL 参数
    const planParams = new URLSearchParams();
    planParams.set("score", String(r.estimatedScore));
    planParams.set("fromAssessment", "1");
    // 把 moduleAssessments 编码为 JSON
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
          <h1 className="text-2xl font-bold text-gray-900 mb-2">测评结果</h1>
          <p className="text-gray-500">
            答对 {r.totalCorrect}/{r.totalQuestions} 题 · 预估分数 {r.estimatedScore} 分
          </p>
        </div>

        {/* 模块水平卡片 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
          <h3 className="font-semibold text-gray-800 mb-4">7 模块水平诊断</h3>
          <div className="space-y-3">
            {sortedModules.map((m) => (
              <div key={m.moduleId} className="flex items-center justify-between">
                <span className="text-sm text-gray-700 flex-1">{m.moduleName}</span>
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium border ${LEVEL_COLORS[m.level]}`}
                  >
                    {m.level} {LEVEL_NAMES[m.level]}
                  </span>
                  {m.confidence === "low" && (
                    <span className="text-xs text-gray-400" title="该模块题量较少，精度有限">
                      *
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-3">* 表示该模块仅 1 题，精度有限</p>
        </div>

        {/* 薄弱点详情 */}
        {weakModules.length > 0 && (
          <div className="bg-red-50 rounded-xl border border-red-100 p-6 mb-4">
            <h3 className="font-semibold text-red-800 mb-3">🔍 检测到的具体弱点</h3>
            <div className="space-y-2">
              {weakModules.map((m) =>
                m.weaknesses.map((w, i) => (
                  <div key={`${m.moduleId}-${i}`} className="flex items-start gap-2 text-sm">
                    <span className="text-red-400 mt-0.5">•</span>
                    <div>
                      <span className="text-red-700 font-medium">{m.moduleName}：</span>
                      <span className="text-red-600">{w}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 优势模块 */}
        {strongModules.length > 0 && (
          <div className="bg-green-50 rounded-xl border border-green-100 p-6 mb-4">
            <h3 className="font-semibold text-green-800 mb-3">✅ 优势模块</h3>
            <div className="flex flex-wrap gap-2">
              {strongModules.map((m) => (
                <span
                  key={m.moduleId}
                  className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm"
                >
                  {m.moduleName} ({m.level})
                </span>
              ))}
            </div>
          </div>
        )}

        {/* CTA */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <h3 className="font-semibold text-gray-800 mb-2">基于测评结果，获取精准学习计划</h3>
          <p className="text-sm text-gray-500 mb-4">
            测评数据已就绪，AI 将根据你的实际水平（而非自评）生成个性化计划
          </p>
          <div className="flex gap-3">
            <Link
              href={`/plan?${planParams.toString()}`}
              className="flex-1 text-center px-4 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 transition-colors"
            >
              📊 生成全面学习计划
            </Link>
            <Link
              href="/drill"
              className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
            >
              🎯 先练最弱模块
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
