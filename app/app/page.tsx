"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import {
  DISTRICTS,
  SUBJECT_MAX,
  TOTAL_MAX,
  daysUntilZhongkao,
  matchSchools,
  type SchoolMatch,
} from "@/lib/schools";

const SUBJECT_KEYS = ["语文", "数学", "英语", "物理", "道法", "体育"] as const;

interface ProfileData {
  currentScore: number;
  targetSchool: string;
  targetScore: number;
  completeness: number;
  modules: Record<string, { level: string; source: string; confidence: number }>;
}

export default function Home() {
  const { user, token, loading } = useAuth();
  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);
  const isParent = user?.role === "parent";
  const isLoggedIn = !!user;

  // 画像
  const [profile, setProfile] = useState<ProfileData | null>(null);
  useEffect(() => {
    if (!token) return;
    fetch("/api/profile", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((data) => { if (data.success) setProfile(data.profile); })
      .catch(() => {});
  }, [token]);

  const hasScore = profile && profile.currentScore > 0;
  const hasTarget = profile && profile.targetSchool;

  // === 首页分两种状态 ===
  // 1. 未登录 / 画像空：score-check 直接嵌入首页
  // 2. 已登录有数据：进度仪表盘

  if (isLoggedIn && !loading && hasScore) {
    return <Dashboard user={user!} profile={profile!} isParent={isParent} days={days} weeks={weeks} />;
  }

  return <LandingWithScoreCheck days={days} weeks={weeks} isLoggedIn={isLoggedIn} isParent={isParent} profile={profile} />;
}

// ============================================================
// Landing：分数输入直接嵌入首页
// ============================================================

function LandingWithScoreCheck({
  days, weeks, isLoggedIn, isParent, profile,
}: {
  days: number; weeks: number; isLoggedIn: boolean; isParent: boolean; profile: ProfileData | null;
}) {
  const [district, setDistrict] = useState("海淀区");
  const [totalScore, setTotalScore] = useState(395);
  const [showDetail, setShowDetail] = useState(false);
  const [subjects, setSubjects] = useState<Record<string, number>>({
    语文: 82, 数学: 78, 英语: 75, 物理: 55, 道法: 65, 体育: 40,
  });
  const [showResult, setShowResult] = useState(false);

  const detailTotal = Object.values(subjects).reduce((a, b) => a + b, 0);
  const effectiveScore = showDetail ? detailTotal : totalScore;

  const matches = matchSchools(district, effectiveScore);
  const chongci = matches.filter((m) => m.category === "冲刺");
  const stable = matches.filter((m) => m.category === "稳妥");
  const safe = matches.filter((m) => m.category === "保底");
  const topTarget = chongci[0];
  const bestStable = stable[0] || safe[0];

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      {/* 倒计时 */}
      <div className="text-center mb-6">
        <p className="text-sm text-orange-600 font-medium">
          距中考还有 <span className="text-xl font-bold">{days}</span> 天（{weeks} 周）
        </p>
      </div>

      {/* 主输入区 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 mb-6">
        <h1 className="text-2xl font-bold text-gray-900 text-center mb-1">
          {isParent ? "孩子的分数能上什么学校？" : "你的分数能上什么学校？"}
        </h1>
        <p className="text-sm text-gray-400 text-center mb-6">输入分数，3 秒匹配冲刺 / 稳妥 / 保底三档学校</p>

        {/* 区 + 总分 */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">所在区</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-3 text-gray-800"
              value={district}
              onChange={(e) => { setDistrict(e.target.value); setShowResult(false); }}
            >
              {DISTRICTS.map((d) => <option key={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">当前总分</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-3 text-gray-800"
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
              <span className="text-gray-400 text-xs whitespace-nowrap">/ {TOTAL_MAX}</span>
            </div>
          </div>
        </div>

        {/* 展开各科 */}
        <button
          className="text-xs text-indigo-600 hover:text-indigo-800 mb-4"
          onClick={() => { setShowDetail(!showDetail); setShowResult(false); }}
        >
          {showDetail ? "▲ 收起各科成绩" : "▼ 我知道各科成绩（更精确）"}
        </button>

        {showDetail && (
          <div className="grid grid-cols-3 gap-3 mb-4">
            {SUBJECT_KEYS.map((sub) => (
              <div key={sub}>
                <label className="block text-xs text-gray-500 mb-1">{sub}<span className="text-gray-300 ml-1">/{SUBJECT_MAX[sub]}</span></label>
                <input
                  type="number"
                  className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800 text-sm"
                  value={subjects[sub]}
                  onChange={(e) => {
                    setSubjects((prev) => ({ ...prev, [sub]: Math.min(SUBJECT_MAX[sub], Math.max(0, parseInt(e.target.value) || 0)) }));
                    setShowResult(false);
                  }}
                  min={0}
                  max={SUBJECT_MAX[sub]}
                />
              </div>
            ))}
          </div>
        )}

        {/* 查询按钮 */}
        <button
          onClick={() => setShowResult(true)}
          className="w-full py-3 bg-indigo-600 text-white rounded-xl font-medium text-lg hover:bg-indigo-700 transition-colors"
        >
          查看匹配学校
        </button>
      </div>

      {/* === 结果区（展开，不跳页）=== */}
      {showResult && (
        <div className="space-y-4">
          {/* 总览 */}
          <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 p-5">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-3xl font-bold text-indigo-700">{effectiveScore}</div>
                <div className="text-xs text-indigo-500 mt-1">当前总分</div>
              </div>
              <div>
                <div className="text-lg font-bold text-green-600 leading-tight">{bestStable ? bestStable.name : "-"}</div>
                <div className="text-xs text-green-500 mt-1">最稳学校</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-orange-600">{topTarget && topTarget.gap > 0 ? topTarget.gap : 0}</div>
                <div className="text-xs text-orange-500 mt-1">{topTarget ? `冲${topTarget.name.slice(0, 5)}需提` : "冲刺需提分"}</div>
              </div>
            </div>
          </div>

          {/* 三档学校 */}
          {([
            { key: "冲刺" as const, schools: chongci, emoji: "🎯", color: "text-red-600", bg: "bg-red-50", border: "border-red-200" },
            { key: "稳妥" as const, schools: stable, emoji: "✅", color: "text-green-600", bg: "bg-green-50", border: "border-green-200" },
            { key: "保底" as const, schools: safe, emoji: "🛡️", color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200" },
          ]).map(({ key, schools, emoji, color, bg, border }) => {
            if (schools.length === 0) return null;
            return (
              <div key={key} className={`${bg} rounded-xl border ${border} p-4`}>
                <h3 className={`font-semibold ${color} mb-3 flex items-center gap-2`}>
                  <span>{emoji}</span>{key}
                  <span className="text-xs font-normal text-gray-400 ml-auto">{schools.length} 所</span>
                </h3>
                <div className="space-y-2">
                  {schools.map((s: SchoolMatch) => (
                    <div key={s.name} className="flex items-center justify-between bg-white/70 rounded-lg px-4 py-2.5">
                      <div>
                        <span className="font-medium text-gray-800 text-sm">{s.name}</span>
                        <span className="text-xs text-gray-400 ml-2">{s.tier}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-gray-500">参考线 {s.refScore}</span>
                        {s.gap > 0
                          ? <span className="ml-2 text-xs font-medium text-red-500">差{s.gap}分</span>
                          : <span className="ml-2 text-xs font-medium text-green-500">高{-s.gap}分</span>
                        }
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {/* 核心引导：去诊断报告 */}
          <div className="bg-white rounded-xl border-2 border-blue-200 p-6 text-center">
            <h3 className="font-bold text-gray-900 mb-2">
              {topTarget && topTarget.gap > 0
                ? `距${topTarget.name}差 ${topTarget.gap} 分，怎么追？`
                : "看看从哪科提分最快"}
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              全科诊断分析各科提分空间，给出优先级排序和时间分配建议
            </p>
            <Link
              href={showDetail
                ? `/diagnosis?district=${encodeURIComponent(district)}&subjects=${encodeURIComponent(JSON.stringify(subjects))}${topTarget ? "&target=" + encodeURIComponent(topTarget.name) + "&targetScore=" + topTarget.refScore : ""}`
                : `/diagnosis?district=${encodeURIComponent(district)}&totalScore=${effectiveScore}${topTarget ? "&target=" + encodeURIComponent(topTarget.name) + "&targetScore=" + topTarget.refScore : ""}`
              }
              className="inline-block px-8 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
            >
              查看提分方案
            </Link>
          </div>

          <p className="text-xs text-gray-400 text-center">
            参考分数基于 2024-2025 年各校录取数据（总分 510 制），仅供参考
          </p>
        </div>
      )}

      {/* 底部信任 */}
      {!showResult && (
        <div className="text-center text-xs text-gray-400 mt-8">
          <p>海淀 / 西城 / 东城 / 朝阳四区数据 | 2021-2025 五年真题逐题分析</p>
          <p className="mt-1">各区一模二模试卷 | 6 科知识点库 | 四区高中录取分数线</p>
        </div>
      )}
    </main>
  );
}

// ============================================================
// Dashboard：已登录有数据的仪表盘
// ============================================================

function Dashboard({
  user, profile, isParent, days, weeks,
}: {
  user: { nickname: string; role: string };
  profile: ProfileData;
  isParent: boolean;
  days: number;
  weeks: number;
}) {
  const gap = profile.targetScore ? profile.targetScore - profile.currentScore : 0;

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      {/* 倒计时 */}
      <div className="text-center mb-6">
        <p className="text-sm text-orange-600 font-medium">
          距中考还有 <span className="text-xl font-bold">{days}</span> 天（{weeks} 周）
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {user.nickname}，{isParent ? "关注孩子每一步进步" : "今天也要加油"}
        </p>
      </div>

      {/* 进度卡片 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-800">
            {isParent ? "孩子的当前状态" : "我的当前状态"}
          </h2>
          <Link href="/profile" className="text-xs text-gray-400 hover:text-blue-600">编辑</Link>
        </div>

        <div className="flex items-center gap-6 mb-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-gray-900">{profile.currentScore}</div>
            <div className="text-xs text-gray-400">当前总分</div>
          </div>
          {profile.targetScore > 0 && (
            <>
              <div className="text-gray-300 text-2xl">&rarr;</div>
              <div className="text-center">
                <div className="text-3xl font-bold text-blue-600">{profile.targetScore}</div>
                <div className="text-xs text-gray-400">目标分</div>
              </div>
              <div className={`px-3 py-1 rounded-full text-sm font-medium ${gap > 0 ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"}`}>
                {gap > 0 ? `差 ${gap} 分` : "已达标"}
              </div>
            </>
          )}
        </div>

        {profile.targetScore > 0 && gap > 0 && (
          <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full"
              style={{ width: `${Math.min(100, (profile.currentScore / profile.targetScore) * 100)}%` }}
            />
          </div>
        )}
        {profile.targetSchool && (
          <p className="text-xs text-gray-400 mt-2">目标：{profile.targetSchool}</p>
        )}
      </div>

      {/* 快捷操作 */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <Link href="/diagnosis" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-3 text-center transition-all hover:border-blue-300 hover:shadow-sm">
            <div className="text-xl mb-1">📋</div>
            <div className="text-xs text-gray-600">诊断报告</div>
          </div>
        </Link>
        <Link href="/plan" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-3 text-center transition-all hover:border-green-300 hover:shadow-sm">
            <div className="text-xl mb-1">📊</div>
            <div className="text-xs text-gray-600">学习计划</div>
          </div>
        </Link>
        <Link href="/progress/exam" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-3 text-center transition-all hover:border-orange-300 hover:shadow-sm">
            <div className="text-xl mb-1">📝</div>
            <div className="text-xs text-gray-600">录成绩</div>
          </div>
        </Link>
        <Link href="/report/weekly" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-3 text-center transition-all hover:border-purple-300 hover:shadow-sm">
            <div className="text-xl mb-1">📈</div>
            <div className="text-xs text-gray-600">周报</div>
          </div>
        </Link>
      </div>

      {/* 下一步建议 */}
      <NextStepCard profile={profile} isParent={isParent} />

      {/* 更多入口 */}
      <div className="space-y-3 mt-6 mb-8">
        <Link href="/score-check" className="block group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 transition-all hover:border-indigo-300 flex items-center gap-3">
            <span className="text-xl">🏫</span>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-900">重新匹配学校</div>
              <div className="text-xs text-gray-500">分数变了？重新看看能上哪些学校</div>
            </div>
            <span className="text-gray-300 text-sm">&rarr;</span>
          </div>
        </Link>
        <Link href="/drill" className="block group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 transition-all hover:border-blue-300 flex items-center gap-3">
            <span className="text-xl">🎯</span>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-900">专项突破</div>
              <div className="text-xs text-gray-500">针对薄弱模块集中训练</div>
            </div>
            <span className="text-gray-300 text-sm">&rarr;</span>
          </div>
        </Link>
        <Link href="/assessment" className="block group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 transition-all hover:border-purple-300 flex items-center gap-3">
            <span className="text-xl">📝</span>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-900">深度测评</div>
              <div className="text-xs text-gray-500">10 道题精确诊断数学各模块水平</div>
            </div>
            <span className="text-gray-300 text-sm">&rarr;</span>
          </div>
        </Link>
      </div>

      {/* 底部 */}
      <div className="text-center text-xs text-gray-400">
        <p>海淀 / 西城 / 东城 / 朝阳四区 | 6 科知识库 | 五年真题逐题分析</p>
      </div>
    </main>
  );
}

// ============================================================
// 下一步建议卡片
// ============================================================

function NextStepCard({ profile, isParent }: { profile: ProfileData; isParent: boolean }) {
  const hasModules = Object.values(profile.modules || {}).some(
    (m) => m.level && m.level !== "不确定" && m.confidence > 0
  );

  // 没做过诊断 → 先去诊断
  if (!hasModules) {
    return (
      <Link href="/diagnosis" className="block">
        <div className="bg-blue-50 rounded-xl border border-blue-200 p-5 hover:border-blue-400 transition-all">
          <h3 className="font-semibold text-blue-800 text-sm mb-1">建议下一步</h3>
          <p className="text-sm text-blue-700">
            {isParent ? "做一次全科诊断，看看孩子哪科提分空间最大" : "做一次全科诊断，看看哪科最容易提分"}
          </p>
          <span className="text-blue-500 text-sm font-medium mt-2 inline-block">去诊断 &rarr;</span>
        </div>
      </Link>
    );
  }

  // 没有目标学校 → 设目标
  if (!profile.targetSchool) {
    return (
      <Link href="/score-check" className="block">
        <div className="bg-blue-50 rounded-xl border border-blue-200 p-5 hover:border-blue-400 transition-all">
          <h3 className="font-semibold text-blue-800 text-sm mb-1">建议下一步</h3>
          <p className="text-sm text-blue-700">设一个目标学校，有目标才有方向</p>
          <span className="text-blue-500 text-sm font-medium mt-2 inline-block">查学校 &rarr;</span>
        </div>
      </Link>
    );
  }

  // 都有了 → 看计划
  return (
    <Link href="/plan" className="block">
      <div className="bg-blue-50 rounded-xl border border-blue-200 p-5 hover:border-blue-400 transition-all">
        <h3 className="font-semibold text-blue-800 text-sm mb-1">建议下一步</h3>
        <p className="text-sm text-blue-700">
          {isParent ? "查看/更新学习计划" : "看看本周该做什么"}
        </p>
        <span className="text-blue-500 text-sm font-medium mt-2 inline-block">查看计划 &rarr;</span>
      </div>
    </Link>
  );
}
