"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";

const MODULES = [
  { id: "numbersAndExpressions", name: "数与式", desc: "实数运算、因式分解、分式", icon: "🔢" },
  { id: "equationsAndInequalities", name: "方程与不等式", desc: "一元二次方程、分式方程、应用题", icon: "⚖️" },
  { id: "functions", name: "函数", desc: "一次函数、反比例函数、二次函数", icon: "📈" },
  { id: "triangles", name: "三角形", desc: "全等、相似、勾股定理、三角函数", icon: "📐" },
  { id: "circles", name: "圆", desc: "垂径定理、圆周角、切线", icon: "⭕" },
  { id: "statisticsAndProbability", name: "统计与概率", desc: "平均数、方差、树状图", icon: "📊" },
  { id: "geometryComprehensive", name: "压轴题", desc: "几何综合、动态几何、代几综合", icon: "💎" },
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
  const [step, setStep] = useState(1);
  const [moduleId, setModuleId] = useState("");
  const [level, setLevel] = useState("");
  const [hoursPerWeek, setHoursPerWeek] = useState(6);
  const [district, setDistrict] = useState("海淀区");
  const [problem, setProblem] = useState("");

  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState("");
  const [error, setError] = useState("");
  const planRef = useRef<HTMLDivElement>(null);

  const selectedModule = MODULES.find((m) => m.id === moduleId);
  const selectedLevel = LEVELS.find((l) => l.id === level);
  const weeksUntilExam = Math.floor(daysUntilZhongkao() / 7);

  const canSubmit = moduleId && level;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    setPlan("");
    setStep(5); // 显示结果

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
              setPlan((prev) => prev + parsed.content);
            } else if (parsed.error) {
              setError(parsed.error);
            }
          } catch {
            // ignore
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "网络错误");
    } finally {
      setLoading(false);
    }
  };

  // 自动滚动
  useEffect(() => {
    if (planRef.current && plan) {
      planRef.current.scrollTop = planRef.current.scrollHeight;
    }
  }, [plan]);

  // 结果页
  if (step === 5) {
    return (
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
        </div>

        {/* 顶部摘要 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex items-center gap-4">
          <span className="text-3xl">{selectedModule?.icon}</span>
          <div>
            <h1 className="text-lg font-bold text-gray-900">
              {selectedModule?.name} · 专项突破计划
            </h1>
            <p className="text-sm text-gray-500">
              当前 {selectedLevel?.name}（{level}）→ 目标升一级 | 每周 {hoursPerWeek} 小时 | 距中考 {weeksUntilExam} 周
            </p>
          </div>
        </div>

        {/* 错误 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
            <p className="text-red-700">{error}</p>
            <button className="mt-2 text-sm text-red-500 underline" onClick={() => { setStep(1); setError(""); setPlan(""); }}>
              重试
            </button>
          </div>
        )}

        {/* 计划内容 */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
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
              className="prose prose-sm max-w-none text-gray-700 prose-headings:text-gray-900 prose-strong:text-gray-900 prose-h2:text-lg prose-h3:text-base max-h-[70vh] overflow-y-auto"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(plan) }}
            />
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex justify-center gap-4 mb-8">
          <button
            onClick={() => { setStep(1); setPlan(""); setError(""); }}
            className="px-6 py-2 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-100"
          >
            换个模块练
          </button>
          <Link
            href="/plan"
            className="px-6 py-2 border border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50"
          >
            做全面规划
          </Link>
        </div>
      </main>
    );
  }

  // 输入表单（步骤式）
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">🎯 专项突破</h1>
        <p className="text-gray-500">选一个薄弱模块，生成针对性训练计划</p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        {/* 第1步：选模块 */}
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">
            <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">1</span>
            选一个你想突破的模块
          </h2>
          <div className="grid grid-cols-2 gap-2">
            {MODULES.map((m) => (
              <button
                key={m.id}
                onClick={() => { setModuleId(m.id); if (step < 2) setStep(2); }}
                className={`text-left px-4 py-3 rounded-lg border-2 transition-all ${
                  moduleId === m.id
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
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

        {/* 第2步：选水平 */}
        {step >= 2 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">2</span>
              你觉得自己{selectedModule?.name}现在什么水平？
            </h2>
            <div className="grid grid-cols-2 gap-2">
              {LEVELS.map((l) => (
                <button
                  key={l.id}
                  onClick={() => { setLevel(l.id); if (step < 3) setStep(3); }}
                  className={`text-left px-4 py-3 rounded-lg border-2 transition-all ${
                    level === l.id
                      ? l.color + " border-current"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="font-medium text-sm">{l.name}（{l.id}）</div>
                  <p className="text-xs opacity-70 mt-0.5">{l.desc}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 第3步：时间和区 */}
        {step >= 3 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              <span className="inline-flex items-center justify-center w-5 h-5 bg-blue-600 text-white text-xs rounded-full mr-2">3</span>
              每周能花多少时间在{selectedModule?.name}上？
            </h2>
            <div className="flex gap-2 mb-3">
              {HOURS_OPTIONS.map((h) => (
                <button
                  key={h.value}
                  onClick={() => { setHoursPerWeek(h.value); if (step < 4) setStep(4); }}
                  className={`flex-1 px-3 py-2 rounded-lg border-2 text-sm transition-all ${
                    hoursPerWeek === h.value
                      ? "border-blue-500 bg-blue-50 text-blue-700 font-medium"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  {h.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">所在区：</span>
              <select
                className="border border-gray-300 rounded px-2 py-1 text-sm text-gray-700"
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
              >
                <option>海淀区</option>
                <option>朝阳区</option>
                <option>西城区</option>
                <option>东城区</option>
              </select>
            </div>
          </div>
        )}

        {/* 第4步：具体问题（可选） */}
        {step >= 4 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              <span className="inline-flex items-center justify-center w-5 h-5 bg-gray-400 text-white text-xs rounded-full mr-2">4</span>
              具体卡在哪？
              <span className="text-xs text-gray-400 font-normal ml-2">（选填，填了计划更精准）</span>
            </h2>
            <input
              type="text"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 placeholder:text-gray-300"
              placeholder="如：配方法总出错、看图判断abc不行、应用题不会列式..."
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
            />
          </div>
        )}

        {/* 提交 */}
        {step >= 3 && (
          <div className="text-center pt-2">
            <button
              onClick={handleSubmit}
              disabled={!canSubmit || loading}
              className="px-8 py-3 bg-blue-600 text-white rounded-xl font-medium text-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "生成中..." : "生成突破计划"}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

// Markdown → HTML（和 plan 页面共用）
function markdownToHtml(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
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
