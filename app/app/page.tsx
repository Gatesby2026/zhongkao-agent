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

      {/* 入口卡片 */}
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

        {/* 📝 快速测评 */}
        <Link href="/assessment" className="group md:col-span-2">
          <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-xl border-2 border-purple-200 p-5 transition-all hover:border-purple-400 hover:shadow-md group-hover:scale-[1.01]">
            <div className="flex items-center gap-4">
              <div className="text-3xl">📝</div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900 mb-1">5 分钟快速测评</h2>
                <p className="text-sm text-gray-500">
                  10 道精选题，精确诊断 7 个模块水平。比自评准 10 倍，直接生成个性化学习计划。
                </p>
              </div>
              <div className="text-purple-600 font-medium text-sm group-hover:underline whitespace-nowrap">
                开始测评 &rarr;
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

      {/* 模考成绩 */}
      <Link href="/progress/exam" className="block mt-5 group">
        <div className="bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl border-2 border-orange-200 p-4 transition-all hover:border-orange-400 hover:shadow-md flex items-center gap-4">
          <div className="text-2xl">📝</div>
          <div className="flex-1">
            <h2 className="text-base font-bold text-gray-900">模考成绩录入</h2>
            <p className="text-xs text-gray-500">录入一模/二模成绩，追踪进步趋势，校准学校匹配</p>
          </div>
          <div className="text-orange-600 font-medium text-sm group-hover:underline whitespace-nowrap">
            录入 &rarr;
          </div>
        </div>
      </Link>

      {/* 全科诊断 */}
      <Link href="/diagnosis" className="block mt-5 group">
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border-2 border-green-200 p-4 transition-all hover:border-green-400 hover:shadow-md flex items-center gap-4">
          <div className="text-2xl">📋</div>
          <div className="flex-1">
            <h2 className="text-base font-bold text-gray-900">全科诊断分析</h2>
            <p className="text-xs text-gray-500">输入 6 科成绩，看看从哪里提分最有效，生成全科时间分配方案</p>
          </div>
          <div className="text-green-600 font-medium text-sm group-hover:underline whitespace-nowrap">
            开始 &rarr;
          </div>
        </div>
      </Link>

      {/* 底部说明 */}
      <div className="mt-10 text-center text-xs text-gray-400">
        <p>数据覆盖：海淀 / 西城 / 东城 / 朝阳 四区 | 2021-2025 五年真题 140 道逐题分析</p>
        <p className="mt-1">3 套各区一模试卷 | 8 模块易错点库 | 4 区高中录取分数线</p>
      </div>
    </main>
  );
}
