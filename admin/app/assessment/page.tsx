"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { QUESTION_TEXTS, evaluateAssessment, type QuestionResult, type AssessmentResult } from "../../lib/assessment";

const TOTAL_QUESTIONS = 10;
const TIME_LIMIT = 60;

const DIFFICULTY_COLORS: Record<string, string> = {
  "基础": "bg-green-100 text-green-700",
  "中档": "bg-yellow-100 text-yellow-700",
  "较难": "bg-red-100 text-red-700",
};

const DIFFICULTIES = ["基础", "基础", "基础", "中档", "中档", "中档", "中档", "较难", "较难", "较难"];

const LEVEL_LABEL: Record<string, string> = {
  L0: "基础薄弱", L1: "需要巩固", L2: "掌握不错", L3: "掌握很好",
};

const MODULE_EXAM_WEIGHT: Record<string, { min: number; max: number }> = {
  numbersAndExpressions: { min: 10, max: 15 },
  equationsAndInequalities: { min: 10, max: 15 },
  functions: { min: 15, max: 20 },
  triangles: { min: 12, max: 18 },
  circles: { min: 8, max: 12 },
  statisticsAndProbability: { min: 8, max: 10 },
  geometryComprehensive: { min: 12, max: 14 },
};

function estimateGain(level: string, weight: { min: number; max: number }): { min: number; max: number } {
  const range = weight.max - weight.min;
  if (level === "L0") return { min: Math.round(weight.min * 0.5), max: Math.round(weight.max * 0.7) };
  if (level === "L1") return { min: Math.round(range * 0.3), max: Math.round(range * 0.6 + 3) };
  return { min: 0, max: 0 };
}

// ============================================================
// 各科自评模块定义
// ============================================================
interface SelfEvalModule {
  id: string;
  name: string;
  desc: string;
  weight: string; // 中考占分说明
}

const SUBJECT_MODULES: Record<string, SelfEvalModule[]> = {
  语文: [
    { id: "chinese_basics", name: "基础·运用", desc: "字音字形、词语、病句、文学常识", weight: "约15分" },
    { id: "chinese_classical", name: "古诗文阅读", desc: "文言文、古诗词鉴赏、默写", weight: "约18分" },
    { id: "chinese_reading", name: "现代文阅读", desc: "记叙文、说明文/非连续性文本", weight: "约22分" },
    { id: "chinese_famous", name: "名著阅读", desc: "12部必读名著", weight: "约5分" },
    { id: "chinese_writing", name: "写作", desc: "审题立意、选材、语言表达", weight: "约40分" },
  ],
  英语: [
    { id: "english_listening", name: "听力口语", desc: "听力选择、朗读、转述、情景应答", weight: "约40分" },
    { id: "english_grammar", name: "语法词汇", desc: "时态、从句、代词、介词", weight: "约12分" },
    { id: "english_cloze", name: "完形填空", desc: "上下文逻辑、高频词汇", weight: "约8分" },
    { id: "english_reading", name: "阅读理解", desc: "ABC三篇，细节/主旨/推断", weight: "约26分" },
    { id: "english_writing", name: "书面表达", desc: "填词+话题作文", weight: "约14分" },
  ],
  物理: [
    { id: "physics_mechanics", name: "力学", desc: "压强、浮力、功率、简单机械", weight: "约28分" },
    { id: "physics_electricity", name: "电学", desc: "电路、欧姆定律、电功率", weight: "约28分" },
    { id: "physics_heat", name: "热学", desc: "物态变化、比热容、内能", weight: "约12分" },
    { id: "physics_optics", name: "光学", desc: "反射折射、透镜成像", weight: "约8分" },
    { id: "physics_experiments", name: "实验专项", desc: "读数、步骤、设计、数据处理", weight: "贯穿各模块" },
  ],
  道法: [
    { id: "politics_law", name: "法治教育", desc: "宪法、公民权利义务、未成年人保护", weight: "约24分" },
    { id: "politics_national", name: "国情教育", desc: "人大制度、基本国策、创新战略", weight: "约20分" },
    { id: "politics_moral", name: "道德教育", desc: "诚信、友善、责任、生活情境", weight: "约16分" },
    { id: "politics_current", name: "时政热点", desc: "时事分析、教材知识点关联", weight: "约12分" },
    { id: "politics_analysis", name: "材料分析", desc: "答题模板、综合探究", weight: "贯穿大题" },
  ],
};

const SELF_LEVELS = [
  { id: "L0", label: "很差", desc: "没什么印象", color: "bg-red-100 text-red-700 border-red-300" },
  { id: "L1", label: "薄弱", desc: "知道一些但经常错", color: "bg-orange-100 text-orange-700 border-orange-300" },
  { id: "L2", label: "还行", desc: "基础题能做对", color: "bg-yellow-100 text-yellow-700 border-yellow-300" },
  { id: "L3", label: "擅长", desc: "很少丢分", color: "bg-green-100 text-green-700 border-green-300" },
];

const SUBJECTS = [
  { key: "数学", icon: "📐", desc: "10题AI智能测评，精准定位7模块", badge: "深度测评", color: "border-blue-400 bg-blue-50" },
  { key: "语文", icon: "📖", desc: "5模块自评，快速定位薄弱项", badge: "快速自评", color: "border-amber-300 bg-amber-50" },
  { key: "英语", icon: "🔤", desc: "5模块自评，快速定位薄弱项", badge: "快速自评", color: "border-green-300 bg-green-50" },
  { key: "物理", icon: "⚡", desc: "5模块自评，快速定位薄弱项", badge: "快速自评", color: "border-purple-300 bg-purple-50" },
  { key: "道法", icon: "📜", desc: "5模块自评，快速定位薄弱项", badge: "快速自评", color: "border-rose-300 bg-rose-50" },
];

export default function AssessmentPage() {
  const { user, token } = useAuth();
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);

  // 数学深度测评 state
  const [stage, setStage] = useState<"intro" | "testing" | "result">("intro");
  const [currentQ, setCurrentQ] = useState(0);
  const [timeLeft, setTimeLeft] = useState(TIME_LIMIT);
  const [results, setResults] = useState<QuestionResult[]>([]);
  const [assessmentResult, setAssessmentResult] = useState<AssessmentResult | null>(null);
  const [startTime, setStartTime] = useState(0);
  const [saved, setSaved] = useState(false);

  // 其他科目自评 state
  const [selfEval, setSelfEval] = useState<Record<string, string>>({});
  const [selfEvalDone, setSelfEvalDone] = useState(false);
  const [selfSaved, setSelfSaved] = useState(false);

  // 倒计时
  useEffect(() => {
    if (stage !== "testing") return;
    if (timeLeft <= 0) { handleAnswer(null); return; }
    const timer = setTimeout(() => setTimeLeft(t => t - 1), 1000);
    return () => clearTimeout(timer);
  }, [stage, timeLeft, currentQ]);

  const handleAnswer = useCallback(
    (answer: string | null) => {
      const timeSpent = TIME_LIMIT - timeLeft;
      const result: QuestionResult = { questionId: currentQ + 1, answer, timeSpent };
      const newResults = [...results, result];
      setResults(newResults);

      if (currentQ + 1 >= TOTAL_QUESTIONS) {
        const assessment = evaluateAssessment(newResults);
        setAssessmentResult(assessment);
        setStage("result");
        if (token) {
          const moduleData: Record<string, { level: string; weaknesses: string[] }> = {};
          for (const m of assessment.modules) {
            moduleData[m.moduleId] = { level: assessment.moduleAssessments[m.moduleId], weaknesses: m.weaknesses };
          }
          fetch("/api/profile/assessment", {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ modules: moduleData, totalCorrect: assessment.totalCorrect, estimatedScore: assessment.estimatedScore, answers: newResults }),
          }).then(() => setSaved(true)).catch(() => {});
        }
      } else {
        setCurrentQ(currentQ + 1);
        setTimeLeft(TIME_LIMIT);
        setStartTime(Date.now());
      }
    },
    [currentQ, results, timeLeft]
  );

  const startMathTest = () => {
    setStage("testing");
    setCurrentQ(0);
    setTimeLeft(TIME_LIMIT);
    setResults([]);
    setStartTime(Date.now());
  };

  // 自评保存
  const handleSelfEvalSave = async () => {
    if (!selectedSubject || !token) return;
    const modules = SUBJECT_MODULES[selectedSubject];
    if (!modules) return;
    const moduleData: Record<string, { level: string; weaknesses: string[] }> = {};
    for (const m of modules) {
      moduleData[m.id] = { level: selfEval[m.id] || "L1", weaknesses: [] };
    }
    try {
      await fetch("/api/profile/assessment", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ modules: moduleData, totalCorrect: 0, estimatedScore: 0, subject: selectedSubject }),
      });
      setSelfSaved(true);
    } catch { /* */ }
  };

  // ====== 科目选择 ======
  if (!selectedSubject) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
        </div>
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">学科测评</h1>
          <p className="text-sm text-gray-500">选择科目，诊断各模块水平</p>
        </div>

        <div className="space-y-3">
          {SUBJECTS.map(s => (
            <button
              key={s.key}
              onClick={() => { setSelectedSubject(s.key); setSelfEval({}); setSelfEvalDone(false); setSelfSaved(false); }}
              className={`w-full text-left px-5 py-4 rounded-xl border-2 ${s.color} hover:shadow-sm transition-all`}
            >
              <div className="flex items-center gap-4">
                <span className="text-3xl">{s.icon}</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-gray-900">{s.key}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      s.badge === "深度测评" ? "bg-blue-200 text-blue-800" : "bg-gray-200 text-gray-600"
                    }`}>{s.badge}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{s.desc}</p>
                </div>
                <span className="text-gray-300">&rarr;</span>
              </div>
            </button>
          ))}
        </div>

        <p className="text-xs text-gray-400 text-center mt-6">
          数学支持 AI 智能测评（10道题精准诊断）<br />
          其他科目暂为自评模式，后续将逐步开放深度测评
        </p>
      </main>
    );
  }

  // ====== 非数学科目：自评模式 ======
  if (selectedSubject !== "数学") {
    const modules = SUBJECT_MODULES[selectedSubject] || [];
    const allEvaluated = modules.every(m => selfEval[m.id]);

    if (selfEvalDone) {
      // 自评结果
      const weak = modules.filter(m => selfEval[m.id] === "L0" || selfEval[m.id] === "L1");
      const good = modules.filter(m => selfEval[m.id] === "L2" || selfEval[m.id] === "L3");

      return (
        <main className="max-w-2xl mx-auto px-4 py-6">
          <div className="mb-4">
            <button onClick={() => { setSelectedSubject(null); setSelfEvalDone(false); }} className="text-sm text-gray-400 hover:text-gray-600">&larr; 选择其他科目</button>
          </div>

          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold text-gray-900 mb-1">
              {selectedSubject} 自评结果
            </h1>
            {selfSaved && <p className="text-xs text-green-600 mt-1">✓ 已保存到学习画像</p>}
            {!selfSaved && token && (
              <button onClick={handleSelfEvalSave} className="text-xs text-blue-600 underline mt-1">保存到画像</button>
            )}
          </div>

          {/* 薄弱模块 */}
          {weak.length > 0 && (
            <div className="bg-red-50 rounded-xl border border-red-200 p-5 mb-4">
              <h3 className="font-semibold text-red-800 mb-3">需要重点补的</h3>
              <div className="space-y-3">
                {weak.map(m => (
                  <div key={m.id} className="bg-white/70 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-800">{m.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        selfEval[m.id] === "L0" ? "bg-red-100 text-red-700" : "bg-orange-100 text-orange-700"
                      }`}>{SELF_LEVELS.find(l => l.id === selfEval[m.id])?.label}</span>
                    </div>
                    <p className="text-xs text-gray-500">{m.desc} · 中考占 {m.weight}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 掌握不错 */}
          {good.length > 0 && (
            <div className="bg-green-50 rounded-xl border border-green-100 p-5 mb-4">
              <h3 className="font-semibold text-green-800 mb-3">掌握不错的</h3>
              <div className="flex flex-wrap gap-2">
                {good.map(m => (
                  <span key={m.id} className="px-3 py-1.5 bg-green-100 text-green-700 rounded-full text-sm">
                    {m.name} · {SELF_LEVELS.find(l => l.id === selfEval[m.id])?.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* CTA */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <div className="flex gap-3">
              <Link href="/drill" className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700">
                去专项训练
              </Link>
              <Link href="/diagnosis" className="flex-1 text-center px-4 py-3 border-2 border-blue-300 text-blue-700 rounded-xl font-medium hover:bg-blue-50">
                看全科诊断
              </Link>
            </div>
          </div>

          <div className="text-center">
            <button onClick={() => { setSelfEvalDone(false); setSelfSaved(false); }}
              className="text-sm text-gray-400 hover:text-gray-600 underline">重新评估</button>
          </div>
        </main>
      );
    }

    // 自评表单
    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <button onClick={() => setSelectedSubject(null)} className="text-sm text-gray-400 hover:text-gray-600">&larr; 选择其他科目</button>
        </div>

        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">{selectedSubject} 模块自评</h1>
          <p className="text-sm text-gray-500">评估每个模块的掌握程度</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="space-y-5">
            {modules.map(m => (
              <div key={m.id}>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="font-medium text-gray-900">{m.name}</span>
                    <span className="text-xs text-gray-400 ml-2">{m.weight}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mb-2">{m.desc}</p>
                <div className="flex gap-2">
                  {SELF_LEVELS.map(l => (
                    <button
                      key={l.id}
                      onClick={() => setSelfEval(prev => ({ ...prev, [m.id]: l.id }))}
                      className={`flex-1 px-2 py-2 rounded-lg border text-sm transition-all ${
                        selfEval[m.id] === l.id ? l.color + " border-current font-medium" : "border-gray-200 text-gray-500 hover:border-gray-300"
                      }`}
                    >
                      <div className="text-xs">{l.label}</div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={() => setSelfEvalDone(true)}
            disabled={!allEvaluated}
            className="w-full mt-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
          >
            查看评估结果
          </button>
          <p className="text-xs text-gray-400 text-center mt-2">请为每个模块选择掌握程度</p>
        </div>
      </main>
    );
  }

  // ====== 数学：深度测评 ======

  // 介绍页
  if (stage === "intro") {
    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <button onClick={() => setSelectedSubject(null)} className="text-sm text-gray-400 hover:text-gray-600">&larr; 选择其他科目</button>
        </div>
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">📐</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">数学深度测评</h1>
          <p className="text-sm text-gray-500 mb-4">10 道精选题，精确定位 7 个模块水平</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
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
            <div className="flex items-center gap-2"><span className="text-green-500">✓</span> 每题限时 60 秒，超时自动跳过</div>
            <div className="flex items-center gap-2"><span className="text-green-500">✓</span> 不确定可以选"不会做"</div>
            <div className="flex items-center gap-2"><span className="text-green-500">✓</span> 结果可直接生成学习计划</div>
          </div>

          <button onClick={startMathTest}
            className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors">
            开始测评
          </button>
        </div>
      </main>
    );
  }

  // 测评中
  if (stage === "testing") {
    const q = QUESTION_TEXTS[currentQ];
    const diff = DIFFICULTIES[currentQ];
    const progress = (currentQ / TOTAL_QUESTIONS) * 100;
    const isUrgent = timeLeft <= 10;

    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <div className="flex justify-between text-sm text-gray-500 mb-2">
            <span>第 {currentQ + 1} / {TOTAL_QUESTIONS} 题</span>
            <span className={`font-mono font-bold ${isUrgent ? "text-red-600 animate-pulse" : "text-gray-600"}`}>{timeLeft}s</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-blue-600 h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-4">
          <div className="flex items-center gap-2 mb-4">
            <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[diff]}`}>{diff}</span>
            <span className="text-xs text-gray-400">Q{currentQ + 1}</span>
          </div>
          <h2 className="text-lg font-medium text-gray-900 mb-5 leading-relaxed">{q.question}</h2>
          <div className="space-y-3">
            {Object.entries(q.options).map(([key, text]) => (
              <button key={key} onClick={() => handleAnswer(key)}
                className={`w-full text-left px-4 py-3 rounded-lg border-2 transition-all ${
                  key === "D" ? "border-gray-200 bg-gray-50 hover:bg-gray-100 text-gray-500"
                  : "border-gray-200 bg-white hover:border-blue-400 hover:bg-blue-50 text-gray-800"
                }`}>
                <span className="font-medium text-gray-400 mr-3">{key}.</span>{text}
              </button>
            ))}
          </div>
        </div>

        <div className="w-full bg-gray-100 rounded-full h-1">
          <div className={`h-1 rounded-full transition-all duration-1000 ${isUrgent ? "bg-red-500" : "bg-blue-400"}`}
            style={{ width: `${(timeLeft / TIME_LIMIT) * 100}%` }} />
        </div>
      </main>
    );
  }

  // 数学结果页
  if (stage === "result" && assessmentResult) {
    const r = assessmentResult;
    const sortedModules = [...r.modules].sort((a, b) => {
      const order = { L0: 0, L1: 1, L2: 2, L3: 3 };
      return order[a.level] - order[b.level];
    });

    const criticalModules = sortedModules.filter(m => m.level === "L0");
    const needWorkModules = sortedModules.filter(m => m.level === "L1");
    const goodModules = sortedModules.filter(m => m.level === "L2" || m.level === "L3");

    const totalGain = [...criticalModules, ...needWorkModules].reduce((sum, m) => {
      const w = MODULE_EXAM_WEIGHT[m.moduleId];
      const g = estimateGain(m.level, w);
      return { min: sum.min + g.min, max: sum.max + g.max };
    }, { min: 0, max: 0 });

    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <button onClick={() => { setSelectedSubject(null); setStage("intro"); setAssessmentResult(null); }}
            className="text-sm text-gray-400 hover:text-gray-600">&larr; 选择其他科目</button>
        </div>

        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">数学测评结果</h1>
          <p className="text-sm text-gray-500">
            答对 {r.totalCorrect}/{r.totalQuestions} 题 · 预估 {r.estimatedScore} 分
          </p>
          {saved && <p className="text-xs text-green-600 mt-1">✓ 已自动保存到画像</p>}
          {!saved && token && <p className="text-xs text-gray-400 mt-1">正在保存...</p>}
          {!token && <p className="text-xs text-gray-400 mt-1"><Link href="/login" className="text-blue-600 underline">登录</Link> 后自动保存</p>}
        </div>

        {criticalModules.length > 0 && (
          <div className="bg-red-50 rounded-xl border border-red-200 p-5 mb-4">
            <h3 className="font-semibold text-red-800 mb-3">需要重点补的</h3>
            <div className="space-y-3">
              {criticalModules.map(m => {
                const w = MODULE_EXAM_WEIGHT[m.moduleId];
                const g = estimateGain(m.level, w);
                return (
                  <div key={m.moduleId} className="bg-white/70 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-800">{m.moduleName}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">{LEVEL_LABEL[m.level]}</span>
                    </div>
                    {m.weaknesses.length > 0 && <p className="text-sm text-gray-600 mb-1">情况：{m.weaknesses[0]}</p>}
                    <div className="flex gap-4 text-xs text-gray-500">
                      <span>中考占 {w.min}-{w.max} 分</span>
                      <span className="text-green-600 font-medium">补上多拿 {g.min}-{g.max} 分</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {needWorkModules.length > 0 && (
          <div className="bg-amber-50 rounded-xl border border-amber-200 p-5 mb-4">
            <h3 className="font-semibold text-amber-800 mb-3">需要巩固的</h3>
            <div className="space-y-3">
              {needWorkModules.map(m => {
                const w = MODULE_EXAM_WEIGHT[m.moduleId];
                const g = estimateGain(m.level, w);
                return (
                  <div key={m.moduleId} className="bg-white/70 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-800">{m.moduleName}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">{LEVEL_LABEL[m.level]}</span>
                    </div>
                    {m.weaknesses.length > 0 && <p className="text-sm text-gray-600 mb-1">情况：{m.weaknesses[0]}</p>}
                    <div className="flex gap-4 text-xs text-gray-500">
                      <span>中考占 {w.min}-{w.max} 分</span>
                      {g.max > 0 && <span className="text-green-600 font-medium">巩固多拿 {g.min}-{g.max} 分</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {goodModules.length > 0 && (
          <div className="bg-green-50 rounded-xl border border-green-100 p-5 mb-4">
            <h3 className="font-semibold text-green-800 mb-3">掌握不错的</h3>
            <div className="flex flex-wrap gap-2">
              {goodModules.map(m => (
                <span key={m.moduleId} className="px-3 py-1.5 bg-green-100 text-green-700 rounded-full text-sm">
                  {m.moduleName} · {LEVEL_LABEL[m.level]}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 p-5 mb-4">
          <h3 className="font-semibold text-indigo-800 mb-2">总结</h3>
          {totalGain.max > 0 ? (
            <p className="text-sm text-gray-700">
              重点补 <span className="font-medium text-red-600">{[...criticalModules, ...needWorkModules].map(m => m.moduleName).join("、")}</span>，
              预计数学可提 {totalGain.min}-{totalGain.max} 分
            </p>
          ) : (
            <p className="text-sm text-gray-700">各模块掌握良好！建议关注压轴题训练。</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <div className="flex gap-3">
            <Link href="/drill" className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700">
              去专项训练
            </Link>
            <Link href="/diagnosis" className="flex-1 text-center px-4 py-3 border-2 border-blue-300 text-blue-700 rounded-xl font-medium hover:bg-blue-50">
              全科诊断
            </Link>
          </div>
        </div>

        <div className="text-center pb-6">
          <button onClick={() => { setStage("intro"); setAssessmentResult(null); setResults([]); }}
            className="text-sm text-gray-400 hover:text-gray-600 underline">重新测评</button>
        </div>
      </main>
    );
  }

  return null;
}
