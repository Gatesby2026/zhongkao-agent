"use client";

import Link from "next/link";

function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(1, Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function Home() {
  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);

  return (
    <main className="max-w-3xl mx-auto px-4 py-12">
      {/* Header */}
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">中考智能学习规划</h1>
        <p className="text-gray-500">
          基于 2021-2025 五年真题 + 四区录取数据，AI 为你定制提分方案
        </p>
        <p className="text-sm text-orange-600 font-medium mt-3">
          距 2026 中考还有 {days} 天（{weeks} 周）
        </p>
      </div>

      {/* 四个入口 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* 🏫 快速入口（P0 核心钩子） */}
        <Link href="/score-check" className="group md:col-span-2">
          <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border-2 border-indigo-200 p-6 transition-all hover:border-indigo-400 hover:shadow-md group-hover:scale-[1.01]">
            <div className="flex items-center gap-4">
              <div className="text-4xl">🏫</div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900 mb-1">我的分数能上什么学校？</h2>
                <p className="text-sm text-gray-500">
                  输入区和分数，3 秒看到可冲 / 稳妥 / 保底三档学校匹配。家长、学生都适用。
                </p>
              </div>
              <div className="text-indigo-600 font-medium text-sm group-hover:underline whitespace-nowrap">
                立即查看 &rarr;
              </div>
            </div>
          </div>
        </Link>

        {/* 专项突破 */}
        <Link href="/drill" className="group">
          <div className="bg-white rounded-xl border-2 border-gray-200 p-6 h-full transition-all hover:border-blue-400 hover:shadow-md group-hover:scale-[1.02]">
            <div className="text-3xl mb-3">🎯</div>
            <h2 className="text-lg font-bold text-gray-900 mb-2">专项突破</h2>
            <p className="text-sm text-gray-500 mb-4">
              哪里不会练哪里。选一个薄弱模块，生成 1-2 周专项训练计划，精确到每天每道题。
            </p>
            <div className="text-xs text-gray-400 space-y-1">
              <div>- 输入简单，10 秒开始</div>
              <div>- 适合已知薄弱点的同学</div>
              <div>- 1-2 周见效</div>
            </div>
            <div className="mt-4 text-blue-600 font-medium text-sm group-hover:underline">
              开始 &rarr;
            </div>
          </div>
        </Link>

        {/* 数学全面规划 */}
        <Link href="/plan" className="group">
          <div className="bg-white rounded-xl border-2 border-gray-200 p-6 h-full transition-all hover:border-green-400 hover:shadow-md group-hover:scale-[1.02]">
            <div className="text-3xl mb-3">📊</div>
            <h2 className="text-lg font-bold text-gray-900 mb-2">数学全面规划</h2>
            <p className="text-sm text-gray-500 mb-4">
              全面诊断 7 个模块水平，生成整体路线图 + 本周详细计划，直到中考。
            </p>
            <div className="text-xs text-gray-400 space-y-1">
              <div>- 不确定水平？系统帮你推算</div>
              <div>- 目标学校 &rarr; 数学目标分</div>
              <div>- 路线图 + 每周计划</div>
            </div>
            <div className="mt-4 text-green-600 font-medium text-sm group-hover:underline">
              开始 &rarr;
            </div>
          </div>
        </Link>
      </div>

      {/* 全科规划预告 */}
      <div className="mt-5 relative">
        <div className="bg-white rounded-xl border-2 border-dashed border-gray-200 p-4 opacity-60 flex items-center gap-4">
          <div className="text-2xl">📋</div>
          <div className="flex-1">
            <h2 className="text-base font-bold text-gray-900">全科规划</h2>
            <p className="text-xs text-gray-500">6科统筹安排，跨科时间分配优化</p>
          </div>
          <div className="text-gray-400 text-xs px-2 py-1 bg-gray-100 rounded-full">Coming Soon</div>
        </div>
      </div>

      {/* 底部说明 */}
      <div className="mt-10 text-center text-xs text-gray-400">
        <p>数据覆盖：海淀 / 西城 / 东城 / 朝阳 四区 | 2021-2025 五年真题 140 道逐题分析</p>
        <p className="mt-1">3 套各区一模试卷 | 8 模块易错点库 | 4 区高中录取分数线</p>
      </div>
    </main>
  );
}
