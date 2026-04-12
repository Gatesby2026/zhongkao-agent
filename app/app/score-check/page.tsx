"use client";

import { useState } from "react";
import Link from "next/link";

// 各区学校列表（与 plan 页面一致）
const SCHOOLS_BY_DISTRICT: Record<
  string,
  { name: string; tier: string; refScore: number }[]
> = {
  朝阳区: [
    { name: "八十中（创新班）", tier: "顶尖", refScore: 95 },
    { name: "北京中学", tier: "顶尖", refScore: 93 },
    { name: "八十中（普通班）", tier: "顶尖", refScore: 90 },
    { name: "人大附中朝阳学校", tier: "重点", refScore: 88 },
    { name: "清华附中朝阳学校", tier: "重点", refScore: 87 },
    { name: "陈经纶中学", tier: "重点", refScore: 85 },
    { name: "朝阳外国语学校", tier: "重点", refScore: 85 },
    { name: "工大附中", tier: "普通", refScore: 78 },
    { name: "日坛中学", tier: "普通", refScore: 75 },
    { name: "和平街一中", tier: "普通", refScore: 73 },
    { name: "三里屯一中", tier: "保底", refScore: 65 },
  ],
  海淀区: [
    { name: "十一学校（科实班）", tier: "顶尖", refScore: 97 },
    { name: "人大附中", tier: "顶尖", refScore: 95 },
    { name: "101中学", tier: "顶尖", refScore: 93 },
    { name: "清华附中", tier: "顶尖", refScore: 92 },
    { name: "首师大附中", tier: "顶尖", refScore: 92 },
    { name: "北大附中", tier: "重点", refScore: 90 },
    { name: "十一学校（普通班）", tier: "重点", refScore: 90 },
    { name: "育英学校", tier: "重点", refScore: 85 },
    { name: "五十七中", tier: "普通", refScore: 78 },
  ],
  西城区: [
    { name: "北师大实验中学", tier: "顶尖", refScore: 95 },
    { name: "北京四中", tier: "顶尖", refScore: 93 },
    { name: "北京八中", tier: "顶尖", refScore: 92 },
    { name: "北师大附中", tier: "重点", refScore: 90 },
    { name: "北师大二附中", tier: "重点", refScore: 90 },
    { name: "161中学", tier: "重点", refScore: 85 },
    { name: "三十五中", tier: "普通", refScore: 82 },
    { name: "十三中", tier: "普通", refScore: 82 },
  ],
  东城区: [
    { name: "北京二中", tier: "顶尖", refScore: 93 },
    { name: "171中学", tier: "顶尖", refScore: 90 },
    { name: "北京五中", tier: "重点", refScore: 88 },
    { name: "汇文中学", tier: "重点", refScore: 86 },
    { name: "广渠门中学", tier: "重点", refScore: 85 },
    { name: "东直门中学", tier: "重点", refScore: 83 },
    { name: "景山学校", tier: "普通", refScore: 80 },
    { name: "166中学", tier: "普通", refScore: 78 },
  ],
};

const TIER_CONFIG: Record<string, { color: string; bg: string; border: string; label: string }> = {
  可冲: { color: "text-red-600", bg: "bg-red-50", border: "border-red-200", label: "努力冲刺" },
  稳妥: { color: "text-green-600", bg: "bg-green-50", border: "border-green-200", label: "稳妥选择" },
  保底: { color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200", label: "安全保底" },
};

function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(
    1,
    Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
  );
}

interface SchoolMatch {
  name: string;
  tier: string;
  refScore: number;
  category: "可冲" | "稳妥" | "保底";
  gap: number; // 正数=需要提分，负数=已超过
}

function matchSchools(
  district: string,
  score: number
): SchoolMatch[] {
  const schools = SCHOOLS_BY_DISTRICT[district] || [];
  return schools
    .map((s) => {
      const gap = s.refScore - score;
      let category: "可冲" | "稳妥" | "保底";
      if (gap > 10) category = "可冲";
      else if (gap > 0) category = "稳妥";
      else category = "保底";
      return { ...s, category, gap };
    })
    .sort((a, b) => b.refScore - a.refScore);
}

export default function ScoreCheckPage() {
  const [district, setDistrict] = useState("朝阳区");
  const [score, setScore] = useState(75);
  const [showResult, setShowResult] = useState(false);

  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);

  const matches = matchSchools(district, score);
  const canChong = matches.filter((m) => m.category === "可冲");
  const stable = matches.filter((m) => m.category === "稳妥");
  const safe = matches.filter((m) => m.category === "保底");

  const bestReachable = stable[0] || safe[0];
  const topChong = canChong[0];
  const maxGain = topChong ? topChong.gap : 0;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-gray-400 hover:text-gray-600"
        >
          &larr; 返回首页
        </Link>
      </div>
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          🏫 分数 → 目标校匹配
        </h1>
        <p className="text-gray-500">
          输入你的数学成绩，3秒看到能上什么学校
        </p>
        <p className="text-xs text-orange-600 mt-2">
          距 2026 中考还有 {days} 天（{weeks} 周）
        </p>
      </div>

      {/* 输入区 — 极简 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
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
              <option>朝阳区</option>
              <option>海淀区</option>
              <option>西城区</option>
              <option>东城区</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              最近数学成绩
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-3 text-gray-800 text-lg"
                value={score}
                onChange={(e) => {
                  setScore(parseInt(e.target.value) || 0);
                  setShowResult(false);
                }}
                min={0}
                max={100}
              />
              <span className="text-gray-400 text-sm whitespace-nowrap">/ 100</span>
            </div>
          </div>
        </div>
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
                <div className="text-3xl font-bold text-indigo-700">{score}</div>
                <div className="text-xs text-indigo-500 mt-1">当前成绩</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-green-600">
                  {bestReachable ? bestReachable.name.length > 4 ? bestReachable.name.slice(0, 4) + "..." : bestReachable.name : "-"}
                </div>
                <div className="text-xs text-green-500 mt-1">最稳学校</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-orange-600">
                  {maxGain > 0 ? `+${maxGain}` : "0"}
                </div>
                <div className="text-xs text-orange-500 mt-1">冲刺需提分</div>
              </div>
            </div>
          </div>

          {/* 三档学校列表 */}
          {[
            { key: "可冲" as const, schools: canChong, emoji: "🚀" },
            { key: "稳妥" as const, schools: stable, emoji: "✅" },
            { key: "保底" as const, schools: safe, emoji: "🛡️" },
          ].map(({ key, schools, emoji }) => {
            if (schools.length === 0) return null;
            const cfg = TIER_CONFIG[key];
            return (
              <div
                key={key}
                className={`${cfg.bg} rounded-xl border ${cfg.border} p-4`}
              >
                <h3 className={`font-semibold ${cfg.color} mb-3 flex items-center gap-2`}>
                  <span>{emoji}</span>
                  {key} — {cfg.label}
                  <span className="text-xs font-normal text-gray-400 ml-auto">
                    {key === "可冲" && "需努力提分"}
                    {key === "稳妥" && "差距10分以内"}
                    {key === "保底" && "当前已达标"}
                  </span>
                </h3>
                <div className="space-y-2">
                  {schools.map((s) => (
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
                          数学需 {s.refScore}+
                        </span>
                        {s.gap > 0 ? (
                          <span className="ml-2 text-sm font-medium text-red-500">
                            差{s.gap}分
                          </span>
                        ) : (
                          <span className="ml-2 text-sm font-medium text-green-500">
                            已超{-s.gap}分
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {/* CTA 区域 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-1">想进一步提分？</h3>
            <p className="text-sm text-gray-500 mb-4">
              AI 根据五年真题数据，为你制定精确到每天每道题的提分计划
            </p>
            <div className="flex gap-3">
              <Link
                href={`/plan?district=${encodeURIComponent(district)}&score=${score}`}
                className="flex-1 text-center px-4 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 transition-colors"
              >
                📊 全面规划
              </Link>
              <Link
                href="/drill"
                className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
              >
                🎯 专项突破
              </Link>
            </div>
          </div>

          {/* 数据说明 */}
          <p className="text-xs text-gray-400 text-center">
            参考分数基于 2024-2025 年{district}各校录取数据，仅供参考
          </p>
        </div>
      )}
    </main>
  );
}
