"use client";

import { useState } from "react";
import Link from "next/link";
import {
  DISTRICTS,
  SUBJECT_MAX,
  TOTAL_MAX,
  daysUntilZhongkao,
  matchSchools,
  type SchoolMatch,
} from "@/lib/schools";

const CATEGORY_CONFIG = {
  冲刺: {
    emoji: "🎯",
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    desc: "需提升 30 分以上",
  },
  稳妥: {
    emoji: "✅",
    color: "text-green-600",
    bg: "bg-green-50",
    border: "border-green-200",
    desc: "差距 30 分以内",
  },
  保底: {
    emoji: "🛡️",
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-200",
    desc: "当前已达标",
  },
};

const SUBJECT_KEYS = ["语文", "数学", "英语", "物理", "道法", "体育"] as const;

export default function ScoreCheckPage() {
  const [district, setDistrict] = useState("朝阳区");
  // 快速模式：直接输入总分
  const [totalScore, setTotalScore] = useState(395);
  // 详细模式：各科分数
  const [showDetail, setShowDetail] = useState(false);
  const [subjects, setSubjects] = useState<Record<string, number>>({
    语文: 82,
    数学: 78,
    英语: 75,
    物理: 55,
    道法: 65,
    体育: 40,
  });
  const [showResult, setShowResult] = useState(false);

  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);

  // 详细模式下自动算总分
  const detailTotal = Object.values(subjects).reduce((a, b) => a + b, 0);
  const effectiveScore = showDetail ? detailTotal : totalScore;

  const matches = matchSchools(district, effectiveScore);
  const chongci = matches.filter((m) => m.category === "冲刺");
  const stable = matches.filter((m) => m.category === "稳妥");
  const safe = matches.filter((m) => m.category === "保底");

  const bestStable = stable[0] || safe[0];
  const topTarget = chongci[0];

  function updateSubject(key: string, val: number) {
    setSubjects((prev) => ({ ...prev, [key]: val }));
    setShowResult(false);
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
          &larr; 返回首页
        </Link>
      </div>
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          🏫 我的分数能上什么学校？
        </h1>
        <p className="text-gray-500">输入总分，3 秒匹配三档目标校</p>
        <p className="text-xs text-orange-600 mt-2">
          距 2026 中考还有 {days} 天（{weeks} 周）
        </p>
      </div>

      {/* 输入区 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        {/* 区 + 总分 */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              所在区
            </label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-3 text-gray-800 text-lg"
              value={district}
              onChange={(e) => {
                setDistrict(e.target.value);
                setShowResult(false);
              }}
            >
              {DISTRICTS.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              当前总分
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-3 text-gray-800 text-lg"
                value={showDetail ? detailTotal : totalScore}
                readOnly={showDetail}
                onChange={(e) => {
                  if (!showDetail) {
                    setTotalScore(Math.min(TOTAL_MAX, Math.max(0, parseInt(e.target.value) || 0)));
                    setShowResult(false);
                  }
                }}
                min={0}
                max={TOTAL_MAX}
              />
              <span className="text-gray-400 text-sm whitespace-nowrap">
                / {TOTAL_MAX}
              </span>
            </div>
          </div>
        </div>

        {/* 展开/收起各科 */}
        <button
          className="mt-4 text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          onClick={() => {
            setShowDetail(!showDetail);
            setShowResult(false);
          }}
        >
          {showDetail ? "▲ 收起各科成绩" : "▼ 我知道各科成绩，展开填写（更精确）"}
        </button>

        {/* 各科详细输入 */}
        {showDetail && (
          <div className="mt-4 grid grid-cols-3 gap-3">
            {SUBJECT_KEYS.map((sub) => (
              <div key={sub}>
                <label className="block text-xs text-gray-500 mb-1">
                  {sub}
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                    value={subjects[sub]}
                    onChange={(e) =>
                      updateSubject(
                        sub,
                        Math.min(
                          SUBJECT_MAX[sub],
                          Math.max(0, parseInt(e.target.value) || 0)
                        )
                      )
                    }
                    min={0}
                    max={SUBJECT_MAX[sub]}
                  />
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    /{SUBJECT_MAX[sub]}
                  </span>
                </div>
              </div>
            ))}
            <div className="col-span-3 text-right text-sm text-indigo-600 font-medium">
              总分：{detailTotal} / {TOTAL_MAX}
            </div>
          </div>
        )}

        {/* 查询按钮 */}
        <div className="mt-5 text-center">
          <button
            onClick={() => setShowResult(true)}
            className="px-10 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-medium text-lg hover:from-blue-700 hover:to-indigo-700 transition-all shadow-md hover:shadow-lg"
          >
            查看目标校匹配
          </button>
        </div>
      </div>

      {/* 结果区 */}
      {showResult && (
        <div className="space-y-4 animate-in fade-in duration-300">
          {/* 总览卡片 */}
          <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 p-5">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-3xl font-bold text-indigo-700">
                  {effectiveScore}
                </div>
                <div className="text-xs text-indigo-500 mt-1">
                  当前总分 / {TOTAL_MAX}
                </div>
              </div>
              <div>
                <div className="text-lg font-bold text-green-600 leading-tight">
                  {bestStable ? bestStable.name : "-"}
                </div>
                <div className="text-xs text-green-500 mt-1">最稳学校</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-orange-600">
                  {topTarget && topTarget.gap > 0 ? `${topTarget.gap}` : "0"}
                </div>
                <div className="text-xs text-orange-500 mt-1">
                  {topTarget ? `冲${topTarget.name.length > 4 ? topTarget.name.slice(0, 4) + "…" : topTarget.name}需提` : "冲刺需提分"}
                </div>
              </div>
            </div>
          </div>

          {/* 三档学校列表 */}
          {(
            [
              { key: "冲刺" as const, schools: chongci },
              { key: "稳妥" as const, schools: stable },
              { key: "保底" as const, schools: safe },
            ] as const
          ).map(({ key, schools }) => {
            if (schools.length === 0) return null;
            const cfg = CATEGORY_CONFIG[key];
            return (
              <div
                key={key}
                className={`${cfg.bg} rounded-xl border ${cfg.border} p-4`}
              >
                <h3
                  className={`font-semibold ${cfg.color} mb-3 flex items-center gap-2`}
                >
                  <span>{cfg.emoji}</span>
                  {key}
                  <span className="text-xs font-normal text-gray-400 ml-auto">
                    {cfg.desc}
                  </span>
                </h3>
                <div className="space-y-2">
                  {schools.map((s: SchoolMatch) => (
                    <div
                      key={s.name}
                      className="flex items-center justify-between bg-white/70 rounded-lg px-4 py-2.5"
                    >
                      <div>
                        <span className="font-medium text-gray-800">
                          {s.name}
                        </span>
                        <span className="text-xs text-gray-400 ml-2">
                          {s.tier}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm text-gray-500">
                          参考线 {s.refScore}
                        </span>
                        {s.gap > 0 ? (
                          <span className="ml-2 text-sm font-medium text-red-500">
                            差{s.gap}分
                          </span>
                        ) : (
                          <span className="ml-2 text-sm font-medium text-green-500">
                            高{-s.gap}分
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {/* 引导区：做测评 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-1">
              💡 想知道哪里提分最快？
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              {bestStable && topTarget && topTarget.gap > 0
                ? `想冲${topTarget.name}？差 ${topTarget.gap} 分。做个快速测评，3 分钟看看从哪里补最有效。`
                : "做个快速测评，3 分钟精准诊断薄弱点，生成专属提分方案。"}
            </p>
            <div className="flex gap-3">
              <Link
                href="/assessment"
                className="flex-1 text-center px-4 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-xl font-medium hover:from-purple-700 hover:to-indigo-700 transition-colors"
              >
                📝 3 分钟快速测评
              </Link>
              <Link
                href={`/plan?district=${encodeURIComponent(district)}&score=${effectiveScore}${showDetail ? "&subjects=" + encodeURIComponent(JSON.stringify(subjects)) : ""}`}
                className="flex-1 text-center px-4 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 transition-colors"
              >
                📊 直接做规划
              </Link>
            </div>
          </div>

          {/* 数据说明 */}
          <p className="text-xs text-gray-400 text-center">
            参考分数基于 2024-2025 年{district}各校录取数据（总分 510 制），仅供参考
          </p>
        </div>
      )}
    </main>
  );
}
