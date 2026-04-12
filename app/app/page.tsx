"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(1, Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));
}

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

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // 加载画像
  useEffect(() => {
    if (!token) return;
    setProfileLoading(true);
    fetch("/api/profile", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((data) => { if (data.success) setProfile(data.profile); })
      .catch(() => {})
      .finally(() => setProfileLoading(false));
  }, [token]);

  // 判断用户阶段
  const hasScore = profile && profile.currentScore > 0;
  const hasModules = profile && Object.values(profile.modules || {}).some(
    (m) => m.level && m.level !== "不确定" && m.confidence > 0
  );
  const hasTarget = profile && profile.targetSchool;

  // 薄弱模块
  const weakModules = profile
    ? Object.entries(profile.modules || {})
        .filter(([, m]) => m.level === "很差" || m.level === "薄弱")
        .map(([id]) => id)
    : [];

  const MODULE_NAMES: Record<string, string> = {
    numbersAndExpressions: "数与式",
    equationsAndInequalities: "方程与不等式",
    functions: "函数",
    triangles: "三角形",
    circles: "圆",
    statisticsAndProbability: "统计与概率",
    geometryComprehensive: "压轴题",
  };

  // ===== 未登录 / 新用户：单一引导 =====
  if (!isLoggedIn || loading) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-12">
        <Countdown days={days} weeks={weeks} />

        {/* 核心钩子 */}
        <div className="bg-white rounded-2xl border-2 border-indigo-200 shadow-sm p-8 text-center mb-6">
          <div className="text-5xl mb-4">🏫</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-3">你的分数能上什么学校？</h2>
          <p className="text-gray-500 mb-6">
            输入区和总分，3 秒看到可冲 / 稳妥 / 保底三档学校
          </p>
          <Link
            href="/score-check"
            className="inline-block px-8 py-3 bg-indigo-600 text-white rounded-xl font-medium text-lg hover:bg-indigo-700 transition-colors"
          >
            立即查看
          </Link>
        </div>

        {/* 次要入口 */}
        <div className="text-center text-sm text-gray-400 mb-6">或者</div>
        <div className="grid grid-cols-2 gap-3 mb-10">
          <Link href="/assessment" className="group">
            <div className="bg-purple-50 rounded-xl border border-purple-200 p-4 text-center transition-all hover:border-purple-400 hover:shadow-sm">
              <div className="text-2xl mb-2">📝</div>
              <div className="text-sm font-medium text-gray-900">5 分钟数学测评</div>
              <div className="text-xs text-gray-400 mt-1">精确定位薄弱模块</div>
            </div>
          </Link>
          <Link href="/diagnosis" className="group">
            <div className="bg-green-50 rounded-xl border border-green-200 p-4 text-center transition-all hover:border-green-400 hover:shadow-sm">
              <div className="text-2xl mb-2">📋</div>
              <div className="text-sm font-medium text-gray-900">全科诊断分析</div>
              <div className="text-xs text-gray-400 mt-1">6 科一起看提分效率</div>
            </div>
          </Link>
        </div>

        <TrustFooter />
      </main>
    );
  }

  // ===== 已登录但画像空：引导第一步 =====
  if (!profileLoading && !hasScore && !hasModules) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-12">
        <Countdown days={days} weeks={weeks} />

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 text-center mb-6">
          <p className="text-sm text-gray-400 mb-2">{user.nickname}，欢迎</p>
          <h2 className="text-xl font-bold text-gray-900 mb-3">
            {isParent ? "先了解孩子现在什么水平" : "先看看自己能上什么学校"}
          </h2>
          <p className="text-gray-500 text-sm mb-6">
            {isParent
              ? "完成下面任一步骤，系统就能给出针对性建议"
              : "从下面选一个开始，后续推荐会更精准"}
          </p>

          <div className="space-y-3 max-w-sm mx-auto">
            <Link href="/score-check" className="block">
              <div className="flex items-center gap-3 px-5 py-4 rounded-xl border-2 border-indigo-200 hover:border-indigo-400 hover:bg-indigo-50 transition-all">
                <span className="text-2xl">🏫</span>
                <div className="text-left flex-1">
                  <div className="font-medium text-gray-900 text-sm">输入分数查学校</div>
                  <div className="text-xs text-gray-400">最快，3 秒出结果</div>
                </div>
                <span className="text-indigo-400">&rarr;</span>
              </div>
            </Link>
            <Link href="/assessment" className="block">
              <div className="flex items-center gap-3 px-5 py-4 rounded-xl border-2 border-purple-200 hover:border-purple-400 hover:bg-purple-50 transition-all">
                <span className="text-2xl">📝</span>
                <div className="text-left flex-1">
                  <div className="font-medium text-gray-900 text-sm">做 10 道题测水平</div>
                  <div className="text-xs text-gray-400">5 分钟，精确诊断 7 个模块</div>
                </div>
                <span className="text-purple-400">&rarr;</span>
              </div>
            </Link>
            <Link href="/diagnosis" className="block">
              <div className="flex items-center gap-3 px-5 py-4 rounded-xl border-2 border-green-200 hover:border-green-400 hover:bg-green-50 transition-all">
                <span className="text-2xl">📋</span>
                <div className="text-left flex-1">
                  <div className="font-medium text-gray-900 text-sm">输入 6 科成绩全面诊断</div>
                  <div className="text-xs text-gray-400">看哪科提分效率最高</div>
                </div>
                <span className="text-green-400">&rarr;</span>
              </div>
            </Link>
          </div>
        </div>

        <TrustFooter />
      </main>
    );
  }

  // ===== 已登录有数据：仪表盘 =====
  const gap = hasTarget && hasScore ? (profile!.targetScore || 0) - profile!.currentScore : 0;

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <Countdown days={days} weeks={weeks} />

      {/* 进度卡片 */}
      {hasScore && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-800">
              {isParent ? "孩子的当前状态" : "我的当前状态"}
            </h2>
            <Link href="/profile" className="text-xs text-gray-400 hover:text-blue-600">编辑画像</Link>
          </div>

          <div className="flex items-center gap-6 mb-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-gray-900">{profile!.currentScore}</div>
              <div className="text-xs text-gray-400">当前总分</div>
            </div>
            {hasTarget && (
              <>
                <div className="text-gray-300 text-2xl">&rarr;</div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-600">{profile!.targetScore}</div>
                  <div className="text-xs text-gray-400">目标分</div>
                </div>
                <div className={`px-3 py-1 rounded-full text-sm font-medium ${gap > 0 ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"}`}>
                  {gap > 0 ? `差 ${gap} 分` : "已达标"}
                </div>
              </>
            )}
          </div>

          {/* 进度条 */}
          {hasTarget && gap > 0 && (
            <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all"
                style={{ width: `${Math.min(100, (profile!.currentScore / (profile!.targetScore || 510)) * 100)}%` }}
              />
            </div>
          )}

          {profile!.targetSchool && (
            <p className="text-xs text-gray-400 mt-2">目标：{profile!.targetSchool}</p>
          )}
        </div>
      )}

      {/* 下一步建议 — 根据画像状态推荐最该做的事 */}
      <div className="bg-blue-50 rounded-2xl border border-blue-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-blue-800 mb-3">
          {isParent ? "建议下一步" : "你现在该做什么"}
        </h2>
        <NextStepGuide
          isParent={isParent}
          hasScore={!!hasScore}
          hasModules={!!hasModules}
          hasTarget={!!hasTarget}
          weakModules={weakModules}
          moduleNames={MODULE_NAMES}
        />
      </div>

      {/* 快捷操作 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <Link href="/score-check" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center transition-all hover:border-indigo-300 hover:shadow-sm">
            <div className="text-2xl mb-1">🏫</div>
            <div className="text-xs font-medium text-gray-700">查学校</div>
          </div>
        </Link>
        <Link href="/progress/exam" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center transition-all hover:border-orange-300 hover:shadow-sm">
            <div className="text-2xl mb-1">📊</div>
            <div className="text-xs font-medium text-gray-700">录成绩</div>
          </div>
        </Link>
        <Link href="/report/weekly" className="group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center transition-all hover:border-blue-300 hover:shadow-sm">
            <div className="text-2xl mb-1">📈</div>
            <div className="text-xs font-medium text-gray-700">周报</div>
          </div>
        </Link>
      </div>

      {/* 薄弱模块快速入口 */}
      {weakModules.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">
            {isParent ? "孩子的薄弱模块" : "需要重点突破"}
          </h2>
          <div className="flex flex-wrap gap-2">
            {weakModules.map((id) => (
              <Link
                key={id}
                href={`/drill?module=${id}`}
                className="px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 hover:bg-red-100 transition-colors"
              >
                {MODULE_NAMES[id] || id} &rarr;
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 更多功能 */}
      <div className="space-y-3 mb-8">
        {!hasModules && (
          <Link href="/assessment" className="block group">
            <div className="bg-purple-50 rounded-xl border border-purple-200 p-4 transition-all hover:border-purple-400 flex items-center gap-3">
              <span className="text-xl">📝</span>
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900">数学快速测评</div>
                <div className="text-xs text-gray-500">{isParent ? "让孩子做 10 道题，精确诊断弱点" : "10 道题精确诊断 7 个模块"}</div>
              </div>
              <span className="text-purple-400 text-sm">&rarr;</span>
            </div>
          </Link>
        )}
        <Link href="/diagnosis" className="block group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 transition-all hover:border-green-300 flex items-center gap-3">
            <span className="text-xl">📋</span>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-900">全科诊断分析</div>
              <div className="text-xs text-gray-500">6 科成绩 → 各科提分效率 → 时间分配方案</div>
            </div>
            <span className="text-green-400 text-sm">&rarr;</span>
          </div>
        </Link>
        <Link href="/plan" className="block group">
          <div className="bg-white rounded-xl border border-gray-200 p-4 transition-all hover:border-blue-300 flex items-center gap-3">
            <span className="text-xl">🎯</span>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-900">数学学习规划</div>
              <div className="text-xs text-gray-500">AI 生成复习路线图 + 每周详细计划</div>
            </div>
            <span className="text-blue-400 text-sm">&rarr;</span>
          </div>
        </Link>
      </div>

      <TrustFooter />
    </main>
  );
}

// ===== 子组件 =====

function Countdown({ days, weeks }: { days: number; weeks: number }) {
  return (
    <div className="text-center mb-8">
      <p className="text-sm text-orange-600 font-medium">
        距中考还有 <span className="text-lg font-bold">{days}</span> 天（{weeks} 周）
      </p>
    </div>
  );
}

function TrustFooter() {
  return (
    <div className="text-center text-xs text-gray-400 mt-8">
      <p>海淀 / 西城 / 东城 / 朝阳四区数据 | 2021-2025 五年真题逐题分析</p>
      <p className="mt-1">各区一模试卷 | 模块易错点库 | 四区高中录取分数线</p>
    </div>
  );
}

function NextStepGuide({
  isParent, hasScore, hasModules, hasTarget, weakModules, moduleNames,
}: {
  isParent: boolean;
  hasScore: boolean;
  hasModules: boolean;
  hasTarget: boolean;
  weakModules: string[];
  moduleNames: Record<string, string>;
}) {
  // 没有模块评估 → 先测评
  if (!hasModules) {
    return (
      <Link href="/assessment" className="flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-blue-200 hover:border-blue-400 transition-all">
        <span className="text-2xl">📝</span>
        <div className="flex-1">
          <div className="font-medium text-gray-900 text-sm">
            {isParent ? "让孩子做一次数学测评" : "先做一次数学测评"}
          </div>
          <div className="text-xs text-gray-500">5 分钟精确诊断 7 个模块水平，后续推荐更精准</div>
        </div>
        <span className="text-blue-500 font-medium text-sm">去测评 &rarr;</span>
      </Link>
    );
  }

  // 有薄弱模块 → 专项突破
  if (weakModules.length > 0) {
    const names = weakModules.slice(0, 2).map((id) => moduleNames[id] || id).join("、");
    return (
      <Link href="/drill" className="flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-blue-200 hover:border-blue-400 transition-all">
        <span className="text-2xl">🎯</span>
        <div className="flex-1">
          <div className="font-medium text-gray-900 text-sm">
            重点突破：{names}
          </div>
          <div className="text-xs text-gray-500">
            {isParent ? "这两个模块是当前最大失分点" : "这是你最容易提分的方向"}
          </div>
        </div>
        <span className="text-blue-500 font-medium text-sm">开始 &rarr;</span>
      </Link>
    );
  }

  // 没设目标 → 去查学校
  if (!hasTarget) {
    return (
      <Link href="/score-check" className="flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-blue-200 hover:border-blue-400 transition-all">
        <span className="text-2xl">🏫</span>
        <div className="flex-1">
          <div className="font-medium text-gray-900 text-sm">设一个目标学校</div>
          <div className="text-xs text-gray-500">有目标才有方向，看看你的分数够哪些学校</div>
        </div>
        <span className="text-blue-500 font-medium text-sm">查学校 &rarr;</span>
      </Link>
    );
  }

  // 都有了 → 生成/更新计划
  return (
    <Link href="/plan" className="flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-blue-200 hover:border-blue-400 transition-all">
      <span className="text-2xl">📊</span>
      <div className="flex-1">
        <div className="font-medium text-gray-900 text-sm">
          {isParent ? "查看/更新学习计划" : "更新本周学习计划"}
        </div>
        <div className="text-xs text-gray-500">基于最新画像数据，生成最适合的复习安排</div>
      </div>
      <span className="text-blue-500 font-medium text-sm">查看 &rarr;</span>
    </Link>
  );
}
