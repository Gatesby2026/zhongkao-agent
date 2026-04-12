"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

// ============================================================
// 各科模块定义（来自知识库）
// ============================================================

interface Module {
  id: string;
  name: string;
  desc: string;
  icon: string;
}

const SUBJECT_MODULES: Record<string, Module[]> = {
  语文: [
    { id: "chinese_basics", name: "基础·运用", desc: "字音字形、词语、病句、文学常识", icon: "📝" },
    { id: "chinese_classical", name: "古诗文", desc: "文言实词虚词、翻译、默写、诗词鉴赏", icon: "📜" },
    { id: "chinese_reading", name: "现代文阅读", desc: "记叙文、说明文、非连续性文本", icon: "📖" },
    { id: "chinese_famous", name: "名著阅读", desc: "12部必读名著的人物情节主题", icon: "📚" },
    { id: "chinese_writing", name: "写作", desc: "审题立意、选材构思、语言表达", icon: "✍️" },
  ],
  数学: [
    { id: "numbersAndExpressions", name: "数与式", desc: "实数运算、因式分解、分式", icon: "🔢" },
    { id: "equationsAndInequalities", name: "方程与不等式", desc: "一元二次方程、分式方程、应用题", icon: "⚖️" },
    { id: "functions", name: "函数", desc: "一次函数、反比例函数、二次函数", icon: "📈" },
    { id: "triangles", name: "三角形", desc: "全等、相似、勾股定理", icon: "📐" },
    { id: "circles", name: "圆", desc: "垂径定理、圆周角、切线", icon: "⭕" },
    { id: "statisticsAndProbability", name: "统计与概率", desc: "平均数、方差、树状图", icon: "📊" },
    { id: "geometryComprehensive", name: "压轴题", desc: "几何综合、动态几何", icon: "💎" },
  ],
  英语: [
    { id: "english_listening", name: "听力口语", desc: "听力选择、朗读、转述、情景应答", icon: "🎧" },
    { id: "english_grammar", name: "语法词汇", desc: "时态、从句、代词、介词", icon: "📝" },
    { id: "english_cloze", name: "完形填空", desc: "上下文逻辑、高频词汇", icon: "🧩" },
    { id: "english_reading", name: "阅读理解", desc: "细节查找、主旨归纳、推断", icon: "📖" },
    { id: "english_writing", name: "书面表达", desc: "填词、话题作文、模板运用", icon: "✍️" },
  ],
  物理: [
    { id: "physics_mechanics", name: "力学", desc: "压强、浮力、功率、简单机械", icon: "⚙️" },
    { id: "physics_electricity", name: "电学", desc: "电路、欧姆定律、电功率", icon: "⚡" },
    { id: "physics_heat", name: "热学", desc: "物态变化、比热容、内能", icon: "🌡️" },
    { id: "physics_optics", name: "光学", desc: "反射折射、透镜成像", icon: "🔦" },
    { id: "physics_experiments", name: "实验专项", desc: "读数、步骤、设计、数据处理", icon: "🔬" },
  ],
  道法: [
    { id: "politics_law", name: "法治教育", desc: "宪法、公民权利义务、未成年人保护", icon: "⚖️" },
    { id: "politics_national", name: "国情教育", desc: "人大制度、基本国策、创新战略", icon: "🏛️" },
    { id: "politics_moral", name: "道德教育", desc: "诚信、友善、责任、生活情境", icon: "💝" },
    { id: "politics_current", name: "时政热点", desc: "时事分析、教材知识点关联", icon: "📰" },
    { id: "politics_analysis", name: "材料分析", desc: "答题模板、观点+分析+总结", icon: "📋" },
  ],
};

const SUBJECTS = [
  { key: "语文", icon: "📖", color: "border-amber-300 bg-amber-50 hover:border-amber-400" },
  { key: "数学", icon: "📐", color: "border-blue-300 bg-blue-50 hover:border-blue-400" },
  { key: "英语", icon: "🔤", color: "border-green-300 bg-green-50 hover:border-green-400" },
  { key: "物理", icon: "⚡", color: "border-purple-300 bg-purple-50 hover:border-purple-400" },
  { key: "道法", icon: "📜", color: "border-rose-300 bg-rose-50 hover:border-rose-400" },
];

const LEVELS = [
  { id: "L0", name: "完全不会", desc: "看到题目没思路", color: "bg-red-100 text-red-700 border-red-300" },
  { id: "L1", name: "概念模糊", desc: "知道点皮毛但做不对", color: "bg-orange-100 text-orange-700 border-orange-300" },
  { id: "L2", name: "基本会做", desc: "简单题能做，难题卡住", color: "bg-yellow-100 text-yellow-700 border-yellow-300" },
  { id: "L3", name: "很熟练", desc: "基本不丢分", color: "bg-green-100 text-green-700 border-green-300" },
];

const HOURS_OPTIONS = [
  { value: 3, label: "3小时/周" },
  { value: 6, label: "6小时/周" },
  { value: 9, label: "9小时/周" },
  { value: 12, label: "12小时/周" },
];

function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(1, Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function DrillPage() {
  const { token } = useAuth();
  const [step, setStep] = useState(0); // 0=选科目, 1=选模块, 2=选水平, 3=时间, 4=问题, 5=结果
  const [subject, setSubject] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [level, setLevel] = useState("");
  const [hoursPerWeek, setHoursPerWeek] = useState(6);
  const [district, setDistrict] = useState("海淀区");
  const [problem, setProblem] = useState("");

  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState("");
  const [error, setError] = useState("");
  const planRef = useRef<HTMLDivElement>(null);

  const [correctRate, setCorrectRate] = useState<number | null>(null);
  const [questionsAttempted, setQuestionsAttempted] = useState(10);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const modules = SUBJECT_MODULES[subject] || [];
  const selectedModule = modules.find(m => m.id === moduleId);
  const selectedLevel = LEVELS.find(l => l.id === level);
  const weeksUntilExam = Math.floor(daysUntilZhongkao() / 7);

  const handleSubmit = async () => {
    if (!moduleId || !level) return;
    setLoading(true);
    setError("");
    setPlan("");
    setStep(5);

    try {
      const res = await fetch("/api/module-drill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          moduleId,
          level,
          district,
          hoursPerWeek,
          weeksUntilExam,
          subject,
          problem: problem || undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "生成失败");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("无法读取响应流");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const data = trimmed.slice(6);
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.content) {
              setPlan(prev => prev + parsed.content);
            } else if (parsed.error) {
              setError(parsed.error);
            }
          } catch { /* */ }
        }
      }
    } catch (err: any) {
      setError(err.message || "网络错误");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveFeedback = async () => {
    if (correctRate === null || !token) return;
    setSaving(true);
    try {
      await fetch("/api/profile/drill", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          moduleId,
          correctRate: correctRate / 100,
          questionsAttempted,
          timeSpent: 0,
        }),
      });
      setSaved(true);
    } catch { /* */ }
    finally { setSaving(false); }
  };

  useEffect(() => {
    if (planRef.current && plan) {
      planRef.current.scrollTop = planRef.current.scrollHeight;
    }
  }, [plan]);

  const resetAll = () => {
    setStep(0);
    setSubject("");
    setModuleId("");
    setLevel("");
    setProblem("");
    setPlan("");
    setError("");
    setSaved(false);
    setCorrectRate(null);
  };

  // ====== 结果页 ======
  if (step === 5) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 flex items-center gap-3">
          <span className="text-3xl">{selectedModule?.icon}</span>
          <div>
            <h1 className="text-lg font-bold text-gray-900">
              {subject} · {selectedModule?.name} · 专项突破
            </h1>
            <p className="text-sm text-gray-500">
              当前 {selectedLevel?.name}（{level}）→ 目标升一级 | 每周 {hoursPerWeek} 小时
            </p>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
            <p className="text-red-700">{error}</p>
            <button className="mt-2 text-sm text-red-500 underline" onClick={() => { setStep(1); setError(""); setPlan(""); }}>重试</button>
          </div>
        )}

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-4">
          {!plan && !error && (
            <div className="flex items-center gap-2 text-gray-400">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              AI 正在生成专项突破计划...
            </div>
          )}
          {plan && (
            <div
              ref={planRef}
              className="prose prose-sm max-w-none text-gray-700 prose-headings:text-gray-900 prose-strong:text-gray-900 max-h-[70vh] overflow-y-auto"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(plan) }}
            />
          )}
        </div>

        {/* 练习反馈 */}
        {plan && !loading && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">练完了？记录效果</h3>
            {saved ? (
              <p className="text-sm text-green-600">✓ 已保存到学习画像</p>
            ) : (
              <>
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-sm text-gray-500">做了几道：</span>
                  <div className="flex gap-2">
                    {[5, 10, 15, 20].map(n => (
                      <button key={n} onClick={() => setQuestionsAttempted(n)}
                        className={`px-3 py-1 rounded border text-sm ${questionsAttempted === n ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-500"}`}>
                        {n}题
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-4 mb-4">
                  <span className="text-sm text-gray-500">正确率：</span>
                  <div className="flex gap-2">
                    {[20, 40, 60, 80, 100].map(r => (
                      <button key={r} onClick={() => setCorrectRate(r)}
                        className={`px-3 py-1 rounded border text-sm ${correctRate === r ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-500"}`}>
                        {r}%
                      </button>
                    ))}
                  </div>
                </div>
                {token ? (
                  <button onClick={handleSaveFeedback} disabled={correctRate === null || saving}
                    className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:bg-gray-300">
                    {saving ? "保存中..." : "保存练习记录"}
                  </button>
                ) : (
                  <p className="text-xs text-gray-400">登录后可保存记录</p>
                )}
              </>
            )}
          </div>
        )}

        <div className="flex justify-center gap-4 pb-6">
          <button onClick={resetAll} className="px-6 py-2 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-100">
            换个模块练
          </button>
          <Link href="/plan" className="px-6 py-2 border border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50">
            看学习计划
          </Link>
        </div>
      </main>
    );
  }

  // ====== 输入表单 ======
  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <div className="mb-4">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">专项突破</h1>
        <p className="text-sm text-gray-500">选科目 → 选模块 → 生成针对性训练计划</p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        {/* 第0步：选科目 */}
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">
            <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">1</span>
            选择科目
          </h2>
          <div className="grid grid-cols-5 gap-2">
            {SUBJECTS.map(s => (
              <button
                key={s.key}
                onClick={() => { setSubject(s.key); setModuleId(""); setLevel(""); if (step < 1) setStep(1); }}
                className={`text-center px-3 py-3 rounded-xl border-2 transition-all ${
                  subject === s.key ? s.color + " font-medium border-2" : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="text-2xl mb-1">{s.icon}</div>
                <div className="text-sm text-gray-800">{s.key}</div>
              </button>
            ))}
          </div>
        </div>

        {/* 第1步：选模块 */}
        {step >= 1 && subject && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">2</span>
              {subject}的哪个模块需要突破？
            </h2>
            <div className="grid grid-cols-2 gap-2">
              {modules.map(m => (
                <button
                  key={m.id}
                  onClick={() => { setModuleId(m.id); if (step < 2) setStep(2); }}
                  className={`text-left px-4 py-3 rounded-lg border-2 transition-all ${
                    moduleId === m.id ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{m.icon}</span>
                    <span className="font-medium text-gray-900 text-sm">{m.name}</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 ml-7">{m.desc}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 第2步：选水平 */}
        {step >= 2 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">3</span>
              你觉得{selectedModule?.name}现在什么水平？
            </h2>
            <div className="grid grid-cols-2 gap-2">
              {LEVELS.map(l => (
                <button
                  key={l.id}
                  onClick={() => { setLevel(l.id); if (step < 3) setStep(3); }}
                  className={`text-left px-4 py-3 rounded-lg border-2 transition-all ${
                    level === l.id ? l.color + " border-current" : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="font-medium text-sm">{l.name}（{l.id}）</div>
                  <p className="text-xs opacity-70 mt-0.5">{l.desc}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 第3步：时间和问题 */}
        {step >= 3 && (
          <>
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-3">
                <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">4</span>
                每周能花多少时间？
              </h2>
              <div className="flex gap-2 mb-3">
                {HOURS_OPTIONS.map(h => (
                  <button
                    key={h.value}
                    onClick={() => setHoursPerWeek(h.value)}
                    className={`flex-1 px-3 py-2 rounded-lg border-2 text-sm transition-all ${
                      hoursPerWeek === h.value ? "border-blue-500 bg-blue-50 text-blue-700 font-medium" : "border-gray-200 text-gray-600"
                    }`}
                  >
                    {h.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">所在区：</span>
                <select className="border border-gray-300 rounded px-2 py-1 text-sm text-gray-700" value={district}
                  onChange={e => setDistrict(e.target.value)}>
                  <option>海淀区</option><option>朝阳区</option><option>西城区</option><option>东城区</option>
                </select>
              </div>
            </div>

            <div className="mb-6">
              <label className="text-xs text-gray-500">具体卡在哪？<span className="text-gray-400">（选填）</span></label>
              <input
                type="text"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 mt-1 placeholder:text-gray-300"
                placeholder="如：压强浮力综合题不会分析、完形填空正确率低..."
                value={problem}
                onChange={e => setProblem(e.target.value)}
              />
            </div>

            <div className="text-center">
              <button
                onClick={handleSubmit}
                disabled={!moduleId || !level || loading}
                className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
              >
                {loading ? "生成中..." : "生成突破计划"}
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function markdownToHtml(md: string): string {
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h3 class="font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="font-bold mt-6 mb-3 text-lg">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="font-bold mt-6 mb-3 text-xl">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    .replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 rounded text-sm">$1</code>')
    .replace(/^---$/gm, '<hr class="my-4 border-gray-200">')
    .replace(/\n\n/g, '</p><p class="mb-3">')
    .replace(/\n/g, "<br>")
    .replace(/^/, '<p class="mb-3">')
    .replace(/$/, "</p>");
}
