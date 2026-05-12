"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  SCHOOLS_BY_DISTRICT,
  SUBJECT_MAX,
  TOTAL_MAX,
  daysUntilZhongkao,
  type School,
  type District,
} from "@/lib/schools";

// ============================================================
// 知识库数据（来自 weight-analysis.yaml）
// ============================================================

interface KBModule {
  name: string;
  scoreRatio: string;
  typicalScore: number;
  description: string;
}

interface KBPriority {
  rank: number;
  area: string;
  potential: string; // e.g. "6-10分"
  effort: "低" | "中" | "中高" | "高" | "极高";
  timeline: string;
  reason: string;
}

interface SubjectKB {
  modules: KBModule[];
  priorities: KBPriority[];
  totalScore: number;
}

const KNOWLEDGE_BASE: Record<string, SubjectKB> = {
  语文: {
    totalScore: 100,
    modules: [
      { name: "基础·积累与运用", scoreRatio: "15%", typicalScore: 15, description: "基础分，确保全对是关键" },
      { name: "古诗文阅读", scoreRatio: "18%", typicalScore: 18, description: "积累+理解并重" },
      { name: "名著阅读", scoreRatio: "5%", typicalScore: 5, description: "必考，深度考查趋增" },
      { name: "现代文阅读", scoreRatio: "22%", typicalScore: 22, description: "区分度最高，记叙文是重点" },
      { name: "写作", scoreRatio: "40%", typicalScore: 40, description: "分值最大，决定总分" },
    ],
    priorities: [
      { rank: 1, area: "古诗文默写", potential: "4分", effort: "低", timeline: "2-4周", reason: "纯记忆分，短期见效最快" },
      { rank: 2, area: "基础·运用（字词/病句/常识）", potential: "6-8分", effort: "低", timeline: "2-4周", reason: "选择题套路固定，刷真题即可" },
      { rank: 3, area: "文言文（实词/虚词/翻译）", potential: "6-10分", effort: "中", timeline: "4-8周", reason: "课内篇目有限，系统梳理即可覆盖" },
      { rank: 4, area: "名著阅读", potential: "3-5分", effort: "中", timeline: "持续积累", reason: "12部名著范围明确" },
      { rank: 5, area: "说明文/议论文/非连续性文本", potential: "4-6分", effort: "中", timeline: "3-5周", reason: "有固定答题模板" },
      { rank: 6, area: "古诗词鉴赏", potential: "4-6分", effort: "中", timeline: "4-6周", reason: "课内篇目有限，掌握答题模式" },
      { rank: 7, area: "写作（三类→二类文）", potential: "5-8分", effort: "中", timeline: "6-10周", reason: "掌握基本结构和选材即可提档" },
      { rank: 8, area: "记叙文深层理解", potential: "5-8分", effort: "高", timeline: "长期训练", reason: "区分度最高但提升最慢" },
      { rank: 9, area: "写作冲刺高分", potential: "3-5分", effort: "极高", timeline: "长期积累", reason: "需要语言功底和思维深度" },
    ],
  },
  数学: {
    totalScore: 100,
    modules: [
      { name: "数与代数", scoreRatio: "50%", typicalScore: 50, description: "最大板块，基础分和难题兼有" },
      { name: "图形与几何", scoreRatio: "38%", typicalScore: 38, description: "第二大板块，大题常出" },
      { name: "统计与概率", scoreRatio: "12%", typicalScore: 12, description: "最小但必考，送分区" },
    ],
    priorities: [
      { rank: 1, area: "方程/不等式/实数/因式分解", potential: "12-16分", effort: "低", timeline: "2-4周", reason: "基础计算题，提分最快" },
      { rank: 2, area: "统计与概率", potential: "8-12分", effort: "低", timeline: "2-3周", reason: "题型固定，中位数/众数/频率计算" },
      { rank: 3, area: "一次函数/反比例函数", potential: "6-10分", effort: "中", timeline: "3-5周", reason: "图象+性质有固定套路" },
      { rank: 4, area: "三角形（全等/相似）", potential: "8-12分", effort: "中", timeline: "4-6周", reason: "证明题有规律可循" },
      { rank: 5, area: "二次函数（基础-中档）", potential: "6-10分", effort: "中高", timeline: "4-8周", reason: "高频大题，分层拿分" },
      { rank: 6, area: "圆+四边形", potential: "6-10分", effort: "中", timeline: "4-6周", reason: "选择/填空常考" },
      { rank: 7, area: "动态几何/压轴", potential: "3-5分", effort: "极高", timeline: "长期训练", reason: "需综合能力，冲刺95+才需要" },
    ],
  },
  英语: {
    totalScore: 100,
    modules: [
      { name: "听力口语", scoreRatio: "40%", typicalScore: 40, description: "2024年起30→40分，机考" },
      { name: "语法与词汇", scoreRatio: "12%", typicalScore: 12, description: "12道单选，语境辨析" },
      { name: "完形填空", scoreRatio: "8%", typicalScore: 8, description: "叙事文体，8道选择" },
      { name: "阅读理解", scoreRatio: "26%", typicalScore: 26, description: "3篇ABC，13题" },
      { name: "文段表达", scoreRatio: "14%", typicalScore: 14, description: "填词4分+作文10分" },
    ],
    priorities: [
      { rank: 1, area: "基础听力+朗读", potential: "10-12分", effort: "低", timeline: "2-4周", reason: "跟读模仿+选择题技巧" },
      { rank: 2, area: "语法（代词/介词/时态/从句）", potential: "8-12分", effort: "中", timeline: "3-5周", reason: "12个高频语法点覆盖80%考题" },
      { rank: 3, area: "阅读A+B篇", potential: "12-16分", effort: "低", timeline: "3-5周", reason: "细节查找+主旨归纳有固定方法" },
      { rank: 4, area: "完形填空", potential: "5-8分", effort: "中", timeline: "3-5周", reason: "高频词+上下文逻辑推断" },
      { rank: 5, area: "听力转述+复述", potential: "6-10分", effort: "中", timeline: "4-8周", reason: "录音模仿+答题模板" },
      { rank: 6, area: "书面表达", potential: "6-10分", effort: "中", timeline: "4-8周", reason: "背模板+练真题" },
      { rank: 7, area: "阅读C篇+开放题", potential: "6-10分", effort: "中高", timeline: "6-10周", reason: "推断+观点表达，需综合能力" },
      { rank: 8, area: "听力情景应答", potential: "4-8分", effort: "高", timeline: "长期训练", reason: "需要真实语感积累" },
    ],
  },
  物理: {
    totalScore: 80,
    modules: [
      { name: "力学", scoreRatio: "35%", typicalScore: 28, description: "最大板块：压强/浮力/功率" },
      { name: "电学", scoreRatio: "35%", typicalScore: 28, description: "与力学并重：实验+计算高分值" },
      { name: "热学", scoreRatio: "15%", typicalScore: 12, description: "物态变化+比热容必考" },
      { name: "光学", scoreRatio: "10%", typicalScore: 8, description: "透镜成像是重点" },
      { name: "声学", scoreRatio: "5%", typicalScore: 4, description: "最小板块，基础分" },
    ],
    priorities: [
      { rank: 1, area: "基础（声/光/物态/运动）", potential: "12-16分", effort: "低", timeline: "2-4周", reason: "概念题+选择题固定套路" },
      { rank: 2, area: "实验操作（读数/步骤）", potential: "8-10分", effort: "低", timeline: "2-4周", reason: "10个核心实验反复练" },
      { rank: 3, area: "压强+浮力基础计算", potential: "6-10分", effort: "中", timeline: "3-5周", reason: "公式不多但变化多" },
      { rank: 4, area: "电路基础+欧姆定律", potential: "6-10分", effort: "中", timeline: "3-5周", reason: "串并联+计算有固定方法" },
      { rank: 5, area: "电学实验（电表+功率）", potential: "8-12分", effort: "中高", timeline: "4-8周", reason: "实验设计+数据处理" },
      { rank: 6, area: "功率+力学综合", potential: "6-10分", effort: "中高", timeline: "4-8周", reason: "综合计算，需要力学基础" },
      { rank: 7, area: "动态电路+多选+设计", potential: "4-8分", effort: "高", timeline: "长期训练", reason: "冲刺高分才需要" },
    ],
  },
  道法: {
    totalScore: 80,
    modules: [
      { name: "法治教育", scoreRatio: "30%", typicalScore: 24, description: "宪法+公民权利，核心板块" },
      { name: "国情教育", scoreRatio: "25%", typicalScore: 20, description: "时政关联，比重上升" },
      { name: "道德教育", scoreRatio: "20%", typicalScore: 16, description: "选择+情境题常考" },
      { name: "时政热点", scoreRatio: "15%", typicalScore: 12, description: "每年内容更新" },
      { name: "心理健康", scoreRatio: "10%", typicalScore: 8, description: "主要在选择题" },
    ],
    priorities: [
      { rank: 1, area: "选择题正确率", potential: "4-8分", effort: "低", timeline: "2-3周", reason: "审题技巧+排除法" },
      { rank: 2, area: "法治板块", potential: "4-6分", effort: "中", timeline: "3-5周", reason: "宪法+权利义务框架清晰" },
      { rank: 3, area: "材料分析答题格式", potential: "6-10分", effort: "中", timeline: "3-5周", reason: "掌握「观点+分析+总结」模板" },
      { rank: 4, area: "时政热点", potential: "4-6分", effort: "中", timeline: "持续跟进", reason: "结合教材知识点分析时事" },
      { rank: 5, area: "国情制度板块", potential: "3-5分", effort: "中", timeline: "3-5周", reason: "人大制度/基本国策等" },
      { rank: 6, area: "道德与品格", potential: "2-4分", effort: "低", timeline: "2-3周", reason: "结合生活情境理解" },
      { rank: 7, area: "综合探究题", potential: "3-5分", effort: "高", timeline: "6-10周", reason: "多角度作答需综合能力" },
      { rank: 8, area: "心理健康", potential: "1-3分", effort: "低", timeline: "1-2周", reason: "分值小但容易拿" },
    ],
  },
  体育: {
    totalScore: 50,
    modules: [
      { name: "过程性考核", scoreRatio: "40%", typicalScore: 20, description: "日常体育课成绩，基本固定" },
      { name: "现场考试", scoreRatio: "60%", typicalScore: 30, description: "中长跑/引体/仰卧起坐/实心球等" },
    ],
    priorities: [
      { rank: 1, area: "过程性考核", potential: "2-4分", effort: "低", timeline: "日常积累", reason: "出勤+课堂表现，基本满分" },
      { rank: 2, area: "中长跑/跳绳", potential: "4-8分", effort: "中", timeline: "4-8周", reason: "日常训练可稳步提升" },
      { rank: 3, area: "力量项目", potential: "3-6分", effort: "中", timeline: "4-8周", reason: "引体向上/实心球需专项训练" },
    ],
  },
};

// 科目颜色配置
const SUBJECT_COLORS: Record<string, { bg: string; border: string; text: string; bar: string; light: string }> = {
  语文: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", bar: "bg-amber-500", light: "bg-amber-100" },
  数学: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", bar: "bg-blue-500", light: "bg-blue-100" },
  英语: { bg: "bg-green-50", border: "border-green-200", text: "text-green-700", bar: "bg-green-500", light: "bg-green-100" },
  物理: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700", bar: "bg-purple-500", light: "bg-purple-100" },
  道法: { bg: "bg-rose-50", border: "border-rose-200", text: "text-rose-700", bar: "bg-rose-500", light: "bg-rose-100" },
  体育: { bg: "bg-teal-50", border: "border-teal-200", text: "text-teal-700", bar: "bg-teal-500", light: "bg-teal-100" },
};

const SUBJECT_ICONS: Record<string, string> = {
  语文: "📖", 数学: "📐", 英语: "🔤", 物理: "⚡", 道法: "📜", 体育: "🏃",
};

const SUBJECT_KEYS = ["语文", "数学", "英语", "物理", "道法", "体育"] as const;

const EFFORT_LABEL: Record<string, string> = {
  "低": "短期见效",
  "中": "中期提升",
  "中高": "需持续练习",
  "高": "长期积累",
  "极高": "冲刺高分",
};

// ============================================================
// 计算逻辑
// ============================================================

// 提分性价比（基于知识库优先级+分差）
function calculateROI(subject: string, current: number, max: number): number {
  const gap = max - current;
  if (gap <= 0) return 0;
  const kb = KNOWLEDGE_BASE[subject];
  if (!kb) return 0;
  // 汇总低/中 effort 的 potential 分值
  const easyGain = kb.priorities
    .filter(p => p.effort === "低" || p.effort === "中")
    .reduce((sum, p) => {
      const match = p.potential.match(/(\d+)-(\d+)/);
      if (match) return sum + (parseInt(match[1]) + parseInt(match[2])) / 2;
      const single = p.potential.match(/(\d+)/);
      if (single) return sum + parseInt(single[1]);
      return sum;
    }, 0);
  // ROI = 可提分空间 / 总分 * 实际gap比
  return (easyGain / max) * (gap / max) * 100;
}

// 预估提分区间（基于知识库 priority potential）
function estimateGain(subject: string, current: number, max: number): { min: number; max: number } {
  const gap = max - current;
  if (gap <= 0) return { min: 0, max: 0 };
  const kb = KNOWLEDGE_BASE[subject];
  if (!kb) return { min: 0, max: 0 };

  let totalMin = 0, totalMax = 0;
  for (const p of kb.priorities) {
    const match = p.potential.match(/(\d+)-(\d+)/);
    if (match) {
      totalMin += parseInt(match[1]);
      totalMax += parseInt(match[2]);
    } else {
      const single = p.potential.match(/(\d+)/);
      if (single) {
        totalMin += parseInt(single[1]);
        totalMax += parseInt(single[1]);
      }
    }
  }
  // 实际可提分不超过差距，取 30%-60% 的理论上限（考虑执行折扣）
  const ratio = gap / max;
  const adjMin = Math.min(gap, Math.round(totalMin * ratio * 0.6));
  const adjMax = Math.min(gap, Math.round(totalMax * ratio * 0.6));
  return { min: Math.max(1, adjMin), max: Math.max(2, adjMax) };
}

// 时间分配
function allocateTime(subjects: { name: string; roi: number }[]): Record<string, number> {
  const academic = subjects.filter(s => s.name !== "体育");
  const totalROI = academic.reduce((s, d) => s + d.roi, 0);
  if (totalROI <= 0) {
    const pct = Math.round(100 / academic.length);
    const result: Record<string, number> = {};
    academic.forEach(s => { result[s.name] = pct; });
    result["体育"] = 0;
    return result;
  }
  const result: Record<string, number> = {};
  let sum = 0;
  for (const s of academic) {
    const pct = Math.round((s.roi / totalROI) * 100);
    result[s.name] = pct;
    sum += pct;
  }
  result["体育"] = 0;
  // 修正到 100
  if (sum !== 100) {
    const top = academic.reduce((a, b) => (result[a.name] > result[b.name] ? a : b));
    result[top.name] += 100 - sum;
  }
  return result;
}

// ============================================================
// 组件
// ============================================================

export default function DiagnosisPage() {
  const [subjects, setSubjects] = useState<Record<string, number>>({
    语文: 82, 数学: 78, 英语: 75, 物理: 55, 道法: 65, 体育: 40,
  });
  const [district, setDistrict] = useState("朝阳区");
  const [targetSchool, setTargetSchool] = useState("");
  const [targetScore, setTargetScore] = useState(0);
  const [hoursPerDay, setHoursPerDay] = useState(2);
  const [showResult, setShowResult] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [expandedSubject, setExpandedSubject] = useState<string | null>(null);

  // URL 参数
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const subjectsJson = params.get("subjects");
    if (subjectsJson) {
      try { setSubjects(JSON.parse(subjectsJson)); } catch { /* ignore */ }
    }
    const d = params.get("district");
    if (d) setDistrict(d);
    const ts = params.get("targetScore");
    if (ts) setTargetScore(parseInt(ts) || 0);
    const tSchool = params.get("target");
    if (tSchool) setTargetSchool(tSchool);
    if (subjectsJson) setShowResult(true);
    setLoaded(true);
  }, []);

  const totalScore = Object.values(subjects).reduce((a, b) => a + b, 0);
  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);

  const schools = (SCHOOLS_BY_DISTRICT as Record<string, School[]>)[district] || [];
  const targetSchoolData = schools.find(s => s.name === targetSchool);
  const effectiveTarget = targetScore || targetSchoolData?.refScore || totalScore + 50;
  const gap = effectiveTarget - totalScore;

  // 各科分析数据
  const subjectAnalysis = SUBJECT_KEYS.map(name => {
    const current = subjects[name] || 0;
    const max = SUBJECT_MAX[name];
    const subGap = max - current;
    const roi = calculateROI(name, current, max);
    const gain = estimateGain(name, current, max);
    const kb = KNOWLEDGE_BASE[name];
    return { name, current, max, gap: subGap, roi, gain, kb };
  });

  const timeAlloc = allocateTime(subjectAnalysis.map(s => ({ name: s.name, roi: s.roi })));
  const sorted = [...subjectAnalysis].filter(s => s.name !== "体育").sort((a, b) => b.roi - a.roi);
  const totalGainMin = subjectAnalysis.reduce((s, d) => s + d.gain.min, 0);
  const totalGainMax = subjectAnalysis.reduce((s, d) => s + d.gain.max, 0);
  const projectedScore = totalScore + Math.round((totalGainMin + totalGainMax) / 2);

  function updateSubject(key: string, val: number) {
    setSubjects(prev => ({ ...prev, [key]: val }));
    setShowResult(false);
  }

  if (!loaded) return null;

  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <div className="mb-4">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      {/* 页面标题 */}
      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">全科诊断报告</h1>
        <p className="text-sm text-gray-500">基于北京中考五年真题数据，分析各科提分空间</p>
        <p className="text-xs text-orange-600 mt-1.5">距 2026 中考还有 {days} 天（{weeks} 周）</p>
      </div>

      {/* ====== 输入区 ====== */}
      {!showResult && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6">
          <h2 className="text-base font-semibold text-gray-800 mb-3">各科最近成绩</h2>
          <div className="grid grid-cols-3 gap-3 mb-3">
            {SUBJECT_KEYS.map(sub => (
              <div key={sub}>
                <label className="block text-xs text-gray-500 mb-1">{SUBJECT_ICONS[sub]} {sub}</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                    value={subjects[sub]}
                    onChange={e => updateSubject(sub, Math.min(SUBJECT_MAX[sub], Math.max(0, parseInt(e.target.value) || 0)))}
                    min={0}
                    max={SUBJECT_MAX[sub]}
                  />
                  <span className="text-xs text-gray-400 whitespace-nowrap">/{SUBJECT_MAX[sub]}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="text-right text-sm text-indigo-600 font-medium mb-3">
            总分：{totalScore} / {TOTAL_MAX}
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">所在区</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                value={district}
                onChange={e => { setDistrict(e.target.value); setTargetSchool(""); }}
              >
                <option>朝阳区</option><option>海淀区</option><option>西城区</option><option>东城区</option>
              </select>
            </div>
            <div>
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
          </div>

          <div className="mb-4">
            <label className="block text-xs text-gray-500 mb-1">目标学校（可选）</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
              value={targetSchool}
              onChange={e => {
                setTargetSchool(e.target.value);
                const s = schools.find(s => s.name === e.target.value);
                if (s) setTargetScore(s.refScore);
              }}
            >
              <option value="">不指定</option>
              {schools.map(s => (
                <option key={s.name} value={s.name}>{s.name}（参考线 {s.refScore}）</option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setShowResult(true)}
            className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
          >
            开始诊断
          </button>
        </div>
      )}

      {/* ====== 诊断结果 ====== */}
      {showResult && (
        <div className="space-y-4">

          {/* ---- 第1层：总览摘要 ---- */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-4 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm opacity-80">当前总分</div>
                  <div className="text-3xl font-bold">{totalScore}<span className="text-base font-normal opacity-60">/{TOTAL_MAX}</span></div>
                </div>
                <div className="text-center">
                  <div className="text-2xl">→</div>
                </div>
                <div className="text-right">
                  <div className="text-sm opacity-80">预期可达</div>
                  <div className="text-3xl font-bold">{projectedScore}<span className="text-base font-normal opacity-60">分</span></div>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-sm opacity-90">
                <span>预计提升 +{totalGainMin}~{totalGainMax} 分</span>
                {targetSchool && <span>目标：{targetSchool}（{effectiveTarget}分{gap > 0 ? `，差${gap}分` : "，已达标"}）</span>}
              </div>
            </div>
            {/* 优先提分科目 */}
            <div className="px-5 py-3 bg-blue-50 flex items-center gap-2 flex-wrap">
              <span className="text-xs text-blue-600 font-medium">优先提分：</span>
              {sorted.slice(0, 3).map((s, i) => (
                <span key={s.name} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${
                  i === 0 ? "bg-green-100 text-green-700" : i === 1 ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"
                }`}>
                  {SUBJECT_ICONS[s.name]} {s.name}
                  <span className="opacity-70">+{s.gain.min}-{s.gain.max}</span>
                </span>
              ))}
            </div>
          </div>

          {/* ---- 第2层：6科卡片 ---- */}
          <div>
            <h2 className="text-base font-semibold text-gray-800 mb-3">各科详情</h2>
            <div className="space-y-3">
              {subjectAnalysis.map(s => {
                const colors = SUBJECT_COLORS[s.name];
                const isExpanded = expandedSubject === s.name;
                const pct = Math.round((s.current / s.max) * 100);
                const roiRank = sorted.findIndex(x => x.name === s.name) + 1;
                const quickWins = s.kb?.priorities.filter(p => p.effort === "低" || p.effort === "中").slice(0, 3) || [];

                return (
                  <div key={s.name} className={`bg-white rounded-xl border ${colors.border} overflow-hidden`}>
                    {/* 卡片头部 */}
                    <button
                      onClick={() => setExpandedSubject(isExpanded ? null : s.name)}
                      className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-gray-50 transition-colors"
                    >
                      <span className="text-2xl">{SUBJECT_ICONS[s.name]}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-gray-900">{s.name}</span>
                          <span className="text-sm text-gray-500">{s.current}/{s.max}</span>
                          {roiRank > 0 && roiRank <= 3 && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              roiRank === 1 ? "bg-green-100 text-green-700" : roiRank === 2 ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"
                            }`}>
                              提分#{roiRank}
                            </span>
                          )}
                        </div>
                        {/* 进度条 */}
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                            <div className={`h-full rounded-full ${colors.bar}`} style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        {s.gain.max > 0 && (
                          <div className="text-sm font-medium text-green-600">+{s.gain.min}-{s.gain.max}</div>
                        )}
                        <div className="text-xs text-gray-400">{isExpanded ? "收起 ▲" : "详情 ▼"}</div>
                      </div>
                    </button>

                    {/* 快速信息（始终显示） */}
                    {quickWins.length > 0 && !isExpanded && (
                      <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                        {quickWins.map(p => (
                          <span key={p.area} className={`text-xs px-2 py-0.5 rounded-full ${colors.light} ${colors.text}`}>
                            {p.area}（{p.potential}）
                          </span>
                        ))}
                      </div>
                    )}

                    {/* 展开详情 */}
                    {isExpanded && s.kb && (
                      <div className={`border-t ${colors.border}`}>
                        {/* 考试结构 */}
                        <div className="px-4 py-3 border-b border-gray-100">
                          <h4 className="text-xs font-medium text-gray-500 mb-2">考试结构</h4>
                          <div className="space-y-1.5">
                            {s.kb.modules.map(m => (
                              <div key={m.name} className="flex items-center gap-2">
                                <div className="flex-1">
                                  <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-800">{m.name}</span>
                                    <span className="text-xs text-gray-500">{m.scoreRatio}（约{m.typicalScore}分）</span>
                                  </div>
                                  <div className="bg-gray-100 rounded-full h-1.5 mt-1">
                                    <div className={`h-full rounded-full ${colors.bar} opacity-60`} style={{ width: m.scoreRatio }} />
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* 提分优先级 */}
                        <div className="px-4 py-3">
                          <h4 className="text-xs font-medium text-gray-500 mb-2">提分路径（按性价比排序）</h4>
                          <div className="space-y-2">
                            {s.kb.priorities.map(p => (
                              <div key={p.area} className="flex items-start gap-2">
                                <span className={`text-xs font-mono w-5 h-5 flex items-center justify-center rounded-full shrink-0 mt-0.5 ${
                                  p.rank <= 2 ? "bg-green-100 text-green-700" : p.rank <= 4 ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"
                                }`}>{p.rank}</span>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-sm font-medium text-gray-800">{p.area}</span>
                                    <span className="text-xs text-green-600 font-medium">{p.potential}</span>
                                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                                      p.effort === "低" ? "bg-green-50 text-green-600" :
                                      p.effort === "中" ? "bg-blue-50 text-blue-600" :
                                      p.effort === "中高" ? "bg-amber-50 text-amber-600" :
                                      "bg-red-50 text-red-600"
                                    }`}>{EFFORT_LABEL[p.effort] || p.effort}</span>
                                  </div>
                                  <p className="text-xs text-gray-500 mt-0.5">{p.reason}</p>
                                  <p className="text-xs text-gray-400">{p.timeline}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ---- 第3层：提分优先级排行 ---- */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-800 mb-1">提分优先级排行</h2>
            <p className="text-xs text-gray-500 mb-4">优先投入前 2-3 科，效率最高</p>
            <div className="space-y-3">
              {sorted.map((s, i) => {
                const colors = SUBJECT_COLORS[s.name];
                const timePct = timeAlloc[s.name] || 0;
                return (
                  <div key={s.name} className="flex items-center gap-3">
                    <span className={`text-sm font-bold w-6 text-center ${
                      i === 0 ? "text-green-600" : i === 1 ? "text-blue-600" : "text-gray-400"
                    }`}>#{i + 1}</span>
                    <span className="text-lg">{SUBJECT_ICONS[s.name]}</span>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-800">{s.name}</span>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-green-600 font-medium">+{s.gain.min}-{s.gain.max}分</span>
                          <span className="text-gray-400">{timePct}%时间</span>
                        </div>
                      </div>
                      <div className="bg-gray-100 rounded-full h-2.5 overflow-hidden">
                        <div className={`h-full rounded-full ${colors.bar}`} style={{ width: `${Math.max(timePct, 5)}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
              {/* 体育 */}
              {(() => {
                const pe = subjectAnalysis.find(s => s.name === "体育");
                return pe && pe.gap > 0 ? (
                  <div className="flex items-center gap-3 opacity-60">
                    <span className="text-sm font-bold w-6 text-center text-gray-300">—</span>
                    <span className="text-lg">🏃</span>
                    <div className="flex-1">
                      <p className="text-xs text-gray-500">体育 {pe.current}/{pe.max}：另安排体能训练时间{pe.gain.max > 0 ? `，可提${pe.gain.min}-${pe.gain.max}分` : ""}</p>
                    </div>
                  </div>
                ) : null;
              })()}
            </div>
          </div>

          {/* ---- 第4层：每日时间分配 ---- */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-800 mb-1">每日时间分配建议</h2>
            <p className="text-xs text-gray-500 mb-4">基于每天 {hoursPerDay} 小时学习时间</p>
            <div className="space-y-2.5">
              {sorted.filter(s => (timeAlloc[s.name] || 0) > 0).map(s => {
                const pct = timeAlloc[s.name] || 0;
                const minutes = Math.round(hoursPerDay * 60 * pct / 100);
                const colors = SUBJECT_COLORS[s.name];
                return (
                  <div key={s.name} className="flex items-center gap-3">
                    <span className="text-sm text-gray-700 w-10 shrink-0">{s.name}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                      <div
                        className={`h-full rounded-full flex items-center px-2 text-xs text-white font-medium ${colors.bar}`}
                        style={{ width: `${Math.max(pct, 10)}%` }}
                      >
                        {pct >= 15 ? `${pct}%` : ""}
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 w-20 text-right">{minutes} 分钟/天</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 p-3 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500">
                💡 体育建议另安排 30-40 分钟体能训练，不占学科学习时间
              </p>
            </div>
          </div>

          {/* ---- 第5层：阶段规划预览 ---- */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-800 mb-3">阶段规划预览</h2>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-3 h-3 rounded-full bg-green-500" />
                  <div className="w-0.5 flex-1 bg-green-200" />
                </div>
                <div className="pb-3">
                  <p className="text-sm font-medium text-gray-800">第一阶段：前 4 周</p>
                  <p className="text-xs text-gray-600 mt-1">
                    重点攻克 <span className="font-medium text-green-700">{sorted[0]?.name}</span> 基础模块 + <span className="font-medium text-blue-700">{sorted[1]?.name}</span> 薄弱环节
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {sorted.slice(0, 2).flatMap(s =>
                      (s.kb?.priorities.filter(p => p.effort === "低") || []).slice(0, 2).map(p =>
                        <span key={`${s.name}-${p.area}`} className="text-xs px-2 py-0.5 bg-green-50 text-green-700 rounded-full">{s.name}·{p.area}</span>
                      )
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-3 h-3 rounded-full bg-blue-500" />
                  <div className="w-0.5 flex-1 bg-blue-200" />
                </div>
                <div className="pb-3">
                  <p className="text-sm font-medium text-gray-800">第二阶段：5-8 周</p>
                  <p className="text-xs text-gray-600 mt-1">
                    {sorted[0]?.name} 进阶 + {sorted.length >= 3 ? sorted[2]?.name : sorted[1]?.name} 专项突破
                  </p>
                  <p className="text-xs text-blue-600 mt-1">一模后重新评估，调整方案</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-3 h-3 rounded-full bg-purple-500" />
                  <div className="w-0.5 flex-1 bg-transparent" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-800">第三阶段：最后 3 周</p>
                  <p className="text-xs text-gray-600 mt-1">全科模考 + 查缺补漏 + 心态调整</p>
                  <p className="text-xs text-purple-600 mt-1">二模后最终冲刺</p>
                </div>
              </div>
            </div>
          </div>

          {/* ---- 总结 + CTA ---- */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-5">
            <h3 className="font-semibold text-blue-800 mb-2">诊断结论</h3>
            <p className="text-sm text-gray-700 mb-3">
              核心策略：优先投入
              <span className="font-semibold text-blue-700"> {sorted.slice(0, 2).map(s => s.name).join(" 和 ")} </span>
              ，这两科提分性价比最高。
              按方案执行到中考，总分预期达到 <span className="font-semibold text-green-700">{totalScore + totalGainMin} - {totalScore + totalGainMax} 分</span>。
            </p>
            <p className="text-xs text-gray-500 mb-4">
              前提：每天执行 {hoursPerDay} 小时 · 基于近五年北京中考真题数据分析
            </p>
            <div className="flex gap-3">
              <Link
                href={`/plan?subjects=${encodeURIComponent(JSON.stringify(subjects))}&district=${encodeURIComponent(district)}&hours=${hoursPerDay}`}
                className="flex-1 text-center px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
              >
                生成学习计划
              </Link>
              <Link
                href="/assessment"
                className="flex-1 text-center px-4 py-3 border-2 border-blue-300 text-blue-700 rounded-xl font-medium hover:bg-blue-50 transition-colors"
              >
                做深度测评
              </Link>
            </div>
          </div>

          {/* 重新填写 */}
          <div className="text-center pb-6">
            <button
              onClick={() => { setShowResult(false); setExpandedSubject(null); }}
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
