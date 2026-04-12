"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  SUBJECT_MAX,
  TOTAL_MAX,
  daysUntilZhongkao,
} from "@/lib/schools";

// ============================================================
// 知识库：各科模块 + 提分优先级（与 diagnosis 同源）
// ============================================================

interface KBPriority {
  area: string;
  potential: string;
  effort: "低" | "中" | "中高" | "高" | "极高";
  timeline: string;
  tasks: string[]; // 本周具体任务
}

interface SubjectPlan {
  priorities: KBPriority[];
}

const PLAN_KB: Record<string, SubjectPlan> = {
  语文: {
    priorities: [
      { area: "古诗文默写", potential: "4分", effort: "低", timeline: "2-4周",
        tasks: ["每天默写 2 首古诗词，逐字校对", "重点背诵《岳阳楼记》《出师表》《水调歌头》", "理解性默写专项练习 10 题"] },
      { area: "基础·运用", potential: "6-8分", effort: "低", timeline: "2-4周",
        tasks: ["刷 3 套字音字形选择题", "病句辨析专项 20 题", "文学常识卡片复习（作者-作品-朝代）"] },
      { area: "文言文阅读", potential: "6-10分", effort: "中", timeline: "4-8周",
        tasks: ["梳理 10 个高频文言实词", "完成 2 篇课内文言文精读", "翻译练习 5 题"] },
      { area: "名著阅读", potential: "3-5分", effort: "中", timeline: "持续",
        tasks: ["本周读完 1 部名著的核心章节", "整理人物关系图", "练习 2 道名著简答题"] },
      { area: "现代文阅读", potential: "4-6分", effort: "中", timeline: "3-5周",
        tasks: ["完成 1 篇记叙文阅读真题", "整理答题模板（词句赏析/手法分析）", "练习信息筛选题 3 道"] },
      { area: "写作", potential: "5-8分", effort: "中", timeline: "6-10周",
        tasks: ["审题训练：分析 3 个历年作文题", "积累 2 个新素材（非老师/妈妈/考试）", "写 1 篇完整作文并自评"] },
    ],
  },
  数学: {
    priorities: [
      { area: "方程/不等式/实数", potential: "12-16分", effort: "低", timeline: "2-4周",
        tasks: ["实数运算专项 15 题", "一元二次方程解法练习 10 题", "因式分解 10 题限时训练"] },
      { area: "统计与概率", potential: "8-12分", effort: "低", timeline: "2-3周",
        tasks: ["中位数/众数/平均数辨析 8 题", "频率直方图读图练习 5 题", "树状图/列表法求概率 5 题"] },
      { area: "一次/反比例函数", potential: "6-10分", effort: "中", timeline: "3-5周",
        tasks: ["一次函数图象性质归纳", "反比例函数 k 值判断专项", "函数与几何结合 3 题"] },
      { area: "三角形", potential: "8-12分", effort: "中", timeline: "4-6周",
        tasks: ["全等三角形证明 5 题", "相似三角形比例计算 5 题", "勾股定理应用 3 题"] },
      { area: "二次函数", potential: "6-10分", effort: "中高", timeline: "4-8周",
        tasks: ["顶点式/一般式/交点式转换练习", "二次函数图象与性质 5 题", "简单应用题 2 道"] },
      { area: "圆+四边形", potential: "6-10分", effort: "中", timeline: "4-6周",
        tasks: ["圆的基本性质选择题 8 题", "四边形判定与性质 5 题", "垂径定理应用 3 题"] },
    ],
  },
  英语: {
    priorities: [
      { area: "基础听力+朗读", potential: "10-12分", effort: "低", timeline: "2-4周",
        tasks: ["每天跟读 1 篇课文录音（15分钟）", "听力选择题专项 10 题", "朗读评分自测 2 篇"] },
      { area: "语法核心", potential: "8-12分", effort: "中", timeline: "3-5周",
        tasks: ["时态辨析专项 10 题（一般/进行/完成）", "代词/介词用法 8 题", "宾语从句/定语从句 5 题"] },
      { area: "阅读A+B篇", potential: "12-16分", effort: "低", timeline: "3-5周",
        tasks: ["限时完成 2 篇阅读理解", "细节查找题技巧总结", "主旨归纳题模板练习"] },
      { area: "完形填空", potential: "5-8分", effort: "中", timeline: "3-5周",
        tasks: ["完成 2 篇完形真题", "高频词汇复习 30 个", "上下文逻辑推断练习"] },
      { area: "书面表达", potential: "6-10分", effort: "中", timeline: "4-8周",
        tasks: ["背诵 2 个万能开头/结尾模板", "话题作文框架练习 1 篇", "常用连接词整理并造句"] },
      { area: "听力转述", potential: "6-10分", effort: "中", timeline: "4-8周",
        tasks: ["转述练习 3 篇（听后复述要点）", "关键信息速记技巧练习", "录音对比纠正发音"] },
    ],
  },
  物理: {
    priorities: [
      { area: "基础概念", potential: "12-16分", effort: "低", timeline: "2-4周",
        tasks: ["声光热基础选择题 15 题", "物态变化图象辨析 5 题", "运动学基本概念 8 题"] },
      { area: "实验操作", potential: "8-10分", effort: "低", timeline: "2-4周",
        tasks: ["10 个核心实验步骤梳理", "读数练习（天平/量筒/电表）10 题", "实验设计题 3 道"] },
      { area: "压强+浮力", potential: "6-10分", effort: "中", timeline: "3-5周",
        tasks: ["压强公式应用 5 题", "浮力三种计算方法各练 3 题", "液体压强计算 5 题"] },
      { area: "电路+欧姆定律", potential: "6-10分", effort: "中", timeline: "3-5周",
        tasks: ["串并联电路识别 8 题", "欧姆定律计算 5 题", "电路图画图练习 3 题"] },
      { area: "电学实验", potential: "8-12分", effort: "中高", timeline: "4-8周",
        tasks: ["伏安法测电阻实验步骤", "电功率测量实验 2 题", "实验数据处理练习"] },
      { area: "力学综合", potential: "6-10分", effort: "中高", timeline: "4-8周",
        tasks: ["功/功率计算 5 题", "简单机械效率 3 题", "力学综合题 2 道"] },
    ],
  },
  道法: {
    priorities: [
      { area: "选择题技巧", potential: "4-8分", effort: "低", timeline: "2-3周",
        tasks: ["审题技巧专项：关键词圈画练习 10 题", "排除法应用 8 题", "易混知识点辨析卡片"] },
      { area: "法治板块", potential: "4-6分", effort: "中", timeline: "3-5周",
        tasks: ["宪法核心知识框架整理", "公民权利与义务对比表", "未成年人保护法要点 5 条"] },
      { area: "材料分析模板", potential: "6-10分", effort: "中", timeline: "3-5周",
        tasks: ["「观点+分析+总结」模板背诵", "完成 2 道材料分析真题", "评分标准对照自评"] },
      { area: "时政热点", potential: "4-6分", effort: "中", timeline: "持续",
        tasks: ["整理本月 3 个重要时政", "时政与教材知识点关联练习", "1 道时政分析题"] },
      { area: "国情制度", potential: "3-5分", effort: "中", timeline: "3-5周",
        tasks: ["人大制度/政协制度框架图", "基本国策知识卡片", "1 道综合探究题"] },
      { area: "道德品格", potential: "2-4分", effort: "低", timeline: "2-3周",
        tasks: ["诚信/友善/责任情境题 5 题", "生活化案例分析 3 道"] },
    ],
  },
  体育: {
    priorities: [
      { area: "中长跑/跳绳", potential: "4-8分", effort: "中", timeline: "4-8周",
        tasks: ["每天慢跑 15 分钟（逐步加速）", "跳绳计时训练 3 组", "记录成绩对比进步"] },
      { area: "力量项目", potential: "3-6分", effort: "中", timeline: "4-8周",
        tasks: ["引体向上/仰卧起坐每天 3 组", "实心球投掷技巧练习", "核心力量训练 10 分钟"] },
    ],
  },
};

const SUBJECT_KEYS = ["语文", "数学", "英语", "物理", "道法", "体育"] as const;
const SUBJECT_ICONS: Record<string, string> = { 语文: "📖", 数学: "📐", 英语: "🔤", 物理: "⚡", 道法: "📜", 体育: "🏃" };
const SUBJECT_COLORS: Record<string, { bar: string; bg: string; border: string; text: string }> = {
  语文: { bar: "bg-amber-500", bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700" },
  数学: { bar: "bg-blue-500", bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700" },
  英语: { bar: "bg-green-500", bg: "bg-green-50", border: "border-green-200", text: "text-green-700" },
  物理: { bar: "bg-purple-500", bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700" },
  道法: { bar: "bg-rose-500", bg: "bg-rose-50", border: "border-rose-200", text: "text-rose-700" },
  体育: { bar: "bg-teal-500", bg: "bg-teal-50", border: "border-teal-200", text: "text-teal-700" },
};

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] as const;

// 计算时间分配
function calcTimeAlloc(subjects: Record<string, number>): Record<string, number> {
  const gaps: { name: string; gap: number }[] = [];
  let totalGap = 0;
  for (const name of SUBJECT_KEYS) {
    if (name === "体育") continue;
    const gap = SUBJECT_MAX[name] - (subjects[name] || 0);
    gaps.push({ name, gap: Math.max(0, gap) });
    totalGap += Math.max(0, gap);
  }
  const result: Record<string, number> = {};
  for (const g of gaps) {
    result[g.name] = totalGap > 0 ? Math.round((g.gap / totalGap) * 100) : 20;
  }
  result["体育"] = 0;
  // Fix sum to 100
  const sum = Object.values(result).reduce((a, b) => a + b, 0);
  if (sum !== 100) {
    const top = gaps.reduce((a, b) => a.gap > b.gap ? a : b);
    result[top.name] += 100 - sum;
  }
  return result;
}

// 生成每日课表
function generateSchedule(
  timeAlloc: Record<string, number>,
  hoursPerDay: number,
  sorted: string[]
): { day: string; blocks: { subject: string; minutes: number; task: string }[] }[] {
  const totalMinutes = hoursPerDay * 60;
  // 工作日主攻前2科，周末全面复习
  return WEEKDAYS.map((day, i) => {
    const isWeekend = i >= 5;
    const blocks: { subject: string; minutes: number; task: string }[] = [];

    if (isWeekend) {
      // 周末分配给所有科目
      const academic = sorted.filter(s => s !== "体育");
      for (const sub of academic) {
        const pct = timeAlloc[sub] || 0;
        const mins = Math.round(totalMinutes * pct / 100);
        if (mins < 10) continue;
        const kb = PLAN_KB[sub];
        const task = kb?.priorities[0]?.tasks[Math.min(i % 3, (kb?.priorities[0]?.tasks.length || 1) - 1)] || "复习巩固";
        blocks.push({ subject: sub, minutes: mins, task });
      }
      // 周末加体育
      blocks.push({ subject: "体育", minutes: 30, task: "体能训练" });
    } else {
      // 工作日：2 科交替 + 1 科补充
      const dayIndex = i % sorted.length;
      const primary = sorted[dayIndex % Math.min(sorted.length, 2)];
      const secondary = sorted[(dayIndex + 1) % Math.min(sorted.length, 3)];

      const primaryMins = Math.round(totalMinutes * 0.6);
      const secondaryMins = totalMinutes - primaryMins;

      const kb1 = PLAN_KB[primary];
      const kb2 = PLAN_KB[secondary];
      const taskIdx = Math.floor(i / 2);

      blocks.push({
        subject: primary,
        minutes: primaryMins,
        task: kb1?.priorities[0]?.tasks[taskIdx % (kb1?.priorities[0]?.tasks.length || 1)] || "专项练习",
      });
      if (secondary !== primary) {
        blocks.push({
          subject: secondary,
          minutes: secondaryMins,
          task: kb2?.priorities[0]?.tasks[taskIdx % (kb2?.priorities[0]?.tasks.length || 1)] || "基础巩固",
        });
      }
    }
    return { day, blocks };
  });
}

export default function PlanPage() {
  const [subjects, setSubjects] = useState<Record<string, number>>({
    语文: 82, 数学: 78, 英语: 75, 物理: 55, 道法: 65, 体育: 40,
  });
  const [hoursPerDay, setHoursPerDay] = useState(2);
  const [showPlan, setShowPlan] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [expandedSubject, setExpandedSubject] = useState<string | null>(null);
  const [currentWeek, setCurrentWeek] = useState(1);

  // URL 参数
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const subjectsJson = params.get("subjects");
    if (subjectsJson) {
      try { setSubjects(JSON.parse(subjectsJson)); } catch { /* */ }
    }
    const h = params.get("hours");
    if (h) setHoursPerDay(parseFloat(h) || 2);
    if (subjectsJson) setShowPlan(true);
    setLoaded(true);
  }, []);

  const totalScore = Object.values(subjects).reduce((a, b) => a + b, 0);
  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);
  const timeAlloc = calcTimeAlloc(subjects);

  // 按分差排序（体育除外）
  const sorted = [...SUBJECT_KEYS]
    .filter(s => s !== "体育")
    .sort((a, b) => {
      const gapA = SUBJECT_MAX[a] - (subjects[a] || 0);
      const gapB = SUBJECT_MAX[b] - (subjects[b] || 0);
      return gapB - gapA;
    });

  const schedule = generateSchedule(timeAlloc, hoursPerDay, sorted);

  // 当前阶段（基于周数）
  const phase = currentWeek <= 4 ? 1 : currentWeek <= 8 ? 2 : 3;
  const phaseLabel = phase === 1 ? "基础突破期" : phase === 2 ? "强化提升期" : "冲刺巩固期";

  if (!loaded) return null;

  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <div className="mb-4">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">学习计划</h1>
        <p className="text-sm text-gray-500">基于诊断结果生成个性化周计划</p>
        <p className="text-xs text-orange-600 mt-1.5">距中考 {days} 天（{weeks} 周）</p>
      </div>

      {/* 输入区 */}
      {!showPlan && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6">
          <h2 className="text-base font-semibold text-gray-800 mb-3">各科成绩</h2>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {SUBJECT_KEYS.map(sub => (
              <div key={sub}>
                <label className="block text-xs text-gray-500 mb-1">{SUBJECT_ICONS[sub]} {sub}</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                    value={subjects[sub]}
                    onChange={e => { setSubjects(prev => ({ ...prev, [sub]: Math.min(SUBJECT_MAX[sub], Math.max(0, parseInt(e.target.value) || 0)) })); }}
                    min={0} max={SUBJECT_MAX[sub]}
                  />
                  <span className="text-xs text-gray-400 whitespace-nowrap">/{SUBJECT_MAX[sub]}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="text-right text-sm text-indigo-600 font-medium mb-3">总分：{totalScore} / {TOTAL_MAX}</div>

          <div className="mb-4">
            <label className="block text-xs text-gray-500 mb-1">每天学习时间</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
              value={hoursPerDay}
              onChange={e => setHoursPerDay(parseFloat(e.target.value))}
            >
              <option value={1}>1 小时</option>
              <option value={1.5}>1.5 小时</option>
              <option value={2}>2 小时</option>
              <option value={2.5}>2.5 小时</option>
              <option value={3}>3 小时</option>
            </select>
          </div>

          <button
            onClick={() => setShowPlan(true)}
            className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
          >
            生成学习计划
          </button>

          <p className="text-xs text-gray-400 text-center mt-3">
            建议先做 <Link href="/diagnosis" className="text-blue-500 underline">全科诊断</Link>，诊断结果会自动带入
          </p>
        </div>
      )}

      {/* 计划结果 */}
      {showPlan && (
        <div className="space-y-4">

          {/* 阶段 + 周切换 */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-green-600 to-emerald-600 px-5 py-4 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm opacity-80">当前阶段</div>
                  <div className="text-xl font-bold">{phaseLabel}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm opacity-80">计划周次</div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setCurrentWeek(Math.max(1, currentWeek - 1))}
                      disabled={currentWeek <= 1}
                      className="px-2 py-1 rounded bg-white/20 hover:bg-white/30 disabled:opacity-30 text-sm"
                    >←</button>
                    <span className="text-xl font-bold">第 {currentWeek} 周</span>
                    <button
                      onClick={() => setCurrentWeek(Math.min(weeks, currentWeek + 1))}
                      disabled={currentWeek >= weeks}
                      className="px-2 py-1 rounded bg-white/20 hover:bg-white/30 disabled:opacity-30 text-sm"
                    >→</button>
                  </div>
                </div>
              </div>
            </div>
            {/* 时间分配摘要 */}
            <div className="px-5 py-3 bg-green-50 flex items-center gap-2 flex-wrap">
              <span className="text-xs text-green-600 font-medium">本周重点：</span>
              {sorted.slice(0, 3).map(sub => (
                <span key={sub} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${SUBJECT_COLORS[sub].bg} ${SUBJECT_COLORS[sub].text}`}>
                  {SUBJECT_ICONS[sub]} {sub} {timeAlloc[sub]}%
                </span>
              ))}
            </div>
          </div>

          {/* 每日课表 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-800 mb-3">每日安排</h2>
            <p className="text-xs text-gray-500 mb-4">每天 {hoursPerDay} 小时 · 工作日主攻重点科 · 周末全面复习</p>
            <div className="space-y-3">
              {schedule.map(({ day, blocks }) => (
                <div key={day} className="flex gap-3">
                  <div className="w-10 shrink-0 text-center">
                    <div className={`text-sm font-medium ${day.includes("六") || day.includes("日") ? "text-green-600" : "text-gray-700"}`}>{day}</div>
                  </div>
                  <div className="flex-1 flex gap-1.5 flex-wrap">
                    {blocks.map((b, i) => {
                      const colors = SUBJECT_COLORS[b.subject];
                      return (
                        <div
                          key={i}
                          className={`px-3 py-2 rounded-lg text-xs ${colors.bg} ${colors.border} border flex-1 min-w-[120px]`}
                        >
                          <div className="flex items-center justify-between mb-0.5">
                            <span className={`font-medium ${colors.text}`}>{SUBJECT_ICONS[b.subject]} {b.subject}</span>
                            <span className="text-gray-400">{b.minutes}min</span>
                          </div>
                          <p className="text-gray-600 truncate">{b.task}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 各科本周任务 */}
          <div>
            <h2 className="text-base font-semibold text-gray-800 mb-3">各科本周任务</h2>
            <div className="space-y-3">
              {sorted.map(sub => {
                const colors = SUBJECT_COLORS[sub];
                const kb = PLAN_KB[sub];
                const isExpanded = expandedSubject === sub;
                // 根据阶段选不同优先级的任务
                const priorityIdx = phase === 1 ? 0 : phase === 2 ? Math.min(2, (kb?.priorities.length || 1) - 1) : Math.min(4, (kb?.priorities.length || 1) - 1);
                const mainPriority = kb?.priorities[Math.min(priorityIdx, (kb?.priorities.length || 1) - 1)];
                const secondPriority = kb?.priorities[Math.min(priorityIdx + 1, (kb?.priorities.length || 1) - 1)];

                return (
                  <div key={sub} className={`bg-white rounded-xl border ${colors.border} overflow-hidden`}>
                    <button
                      onClick={() => setExpandedSubject(isExpanded ? null : sub)}
                      className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-gray-50 transition-colors"
                    >
                      <span className="text-2xl">{SUBJECT_ICONS[sub]}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-gray-900">{sub}</span>
                          <span className="text-xs text-gray-400">{timeAlloc[sub]}% 时间</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${colors.bg} ${colors.text}`}>
                            {mainPriority?.area}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5 truncate">
                          {mainPriority?.tasks[0]}
                        </p>
                      </div>
                      <span className="text-xs text-gray-400">{isExpanded ? "收起 ▲" : "展开 ▼"}</span>
                    </button>

                    {isExpanded && kb && (
                      <div className={`border-t ${colors.border} px-4 py-3`}>
                        {/* 主要任务 */}
                        <div className="mb-3">
                          <h4 className="text-xs font-medium text-gray-500 mb-2">
                            重点：{mainPriority?.area}（{mainPriority?.potential}）
                          </h4>
                          <div className="space-y-1.5">
                            {mainPriority?.tasks.map((task, i) => (
                              <div key={i} className="flex items-start gap-2">
                                <span className="w-4 h-4 rounded border border-gray-300 shrink-0 mt-0.5" />
                                <span className="text-sm text-gray-700">{task}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                        {/* 次要任务 */}
                        {secondPriority && secondPriority !== mainPriority && (
                          <div>
                            <h4 className="text-xs font-medium text-gray-500 mb-2">
                              辅助：{secondPriority.area}（{secondPriority.potential}）
                            </h4>
                            <div className="space-y-1.5">
                              {secondPriority.tasks.slice(0, 2).map((task, i) => (
                                <div key={i} className="flex items-start gap-2">
                                  <span className="w-4 h-4 rounded border border-gray-300 shrink-0 mt-0.5" />
                                  <span className="text-sm text-gray-700">{task}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* 全部优先级列表 */}
                        <div className="mt-3 pt-3 border-t border-gray-100">
                          <h4 className="text-xs font-medium text-gray-400 mb-1.5">全阶段提分路径</h4>
                          <div className="flex flex-wrap gap-1.5">
                            {kb.priorities.map((p, i) => (
                              <span key={i} className={`text-xs px-2 py-0.5 rounded-full ${
                                i <= priorityIdx ? `${colors.bg} ${colors.text}` : "bg-gray-100 text-gray-400"
                              }`}>
                                {i + 1}. {p.area}（{p.potential}）
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* 体育 */}
              <div className={`bg-white rounded-xl border ${SUBJECT_COLORS["体育"].border} px-4 py-3`}>
                <div className="flex items-center gap-3">
                  <span className="text-2xl">🏃</span>
                  <div>
                    <span className="font-semibold text-gray-900">体育</span>
                    <span className="text-xs text-gray-400 ml-2">另安排 · 不占学科时间</span>
                    <p className="text-xs text-gray-500 mt-0.5">
                      每天 30 分钟体能训练：中长跑/跳绳 + 力量项目
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 阶段里程碑 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-800 mb-3">阶段里程碑</h2>
            <div className="space-y-3">
              <div className={`flex gap-3 ${phase === 1 ? "opacity-100" : "opacity-50"}`}>
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full ${phase >= 1 ? "bg-green-500" : "bg-gray-300"}`} />
                  <div className="w-0.5 flex-1 bg-gray-200" />
                </div>
                <div className="pb-3">
                  <p className="text-sm font-medium text-gray-800">第 1-4 周：基础突破</p>
                  <p className="text-xs text-gray-500">主攻 {sorted[0]} 和 {sorted[1]} 基础模块，每周完成任务清单</p>
                  {phase === 1 && <span className="text-xs text-green-600 font-medium">← 当前阶段</span>}
                </div>
              </div>
              <div className={`flex gap-3 ${phase === 2 ? "opacity-100" : "opacity-50"}`}>
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full ${phase >= 2 ? "bg-blue-500" : "bg-gray-300"}`} />
                  <div className="w-0.5 flex-1 bg-gray-200" />
                </div>
                <div className="pb-3">
                  <p className="text-sm font-medium text-gray-800">第 5-8 周：强化提升</p>
                  <p className="text-xs text-gray-500">中档题型专项突破，一模后调整方案</p>
                  {phase === 2 && <span className="text-xs text-blue-600 font-medium">← 当前阶段</span>}
                </div>
              </div>
              <div className={`flex gap-3 ${phase === 3 ? "opacity-100" : "opacity-50"}`}>
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full ${phase >= 3 ? "bg-purple-500" : "bg-gray-300"}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-800">第 9 周 - 中考：冲刺巩固</p>
                  <p className="text-xs text-gray-500">全科模考 + 查缺补漏 + 心态调整</p>
                  {phase === 3 && <span className="text-xs text-purple-600 font-medium">← 当前阶段</span>}
                </div>
              </div>
            </div>
          </div>

          {/* 底部操作 */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-5">
            <h3 className="font-semibold text-blue-800 mb-2">执行建议</h3>
            <div className="space-y-2 text-sm text-gray-700 mb-4">
              <p>1. 按每日课表执行，每完成一项打勾</p>
              <p>2. 每周日回顾本周任务完成情况</p>
              <p>3. 一模/二模后重新做 <Link href="/diagnosis" className="text-blue-600 underline">全科诊断</Link> 调整方案</p>
            </div>
            <div className="flex gap-3">
              <Link
                href="/drill"
                className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
              >
                开始专项训练
              </Link>
              <Link
                href="/diagnosis"
                className="flex-1 text-center px-4 py-3 border-2 border-blue-300 text-blue-700 rounded-xl font-medium hover:bg-blue-50 transition-colors"
              >
                重新诊断
              </Link>
            </div>
          </div>

          <div className="text-center pb-6">
            <button
              onClick={() => { setShowPlan(false); setExpandedSubject(null); setCurrentWeek(1); }}
              className="text-sm text-gray-400 hover:text-gray-600 underline"
            >
              重新填写成绩
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
