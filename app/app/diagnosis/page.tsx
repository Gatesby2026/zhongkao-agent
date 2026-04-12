"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  SCHOOLS_BY_DISTRICT,
  SUBJECT_MAX,
  TOTAL_MAX,
  daysUntilZhongkao,
  matchSchools,
  type School,
  type District,
} from "@/lib/schools";

// 各科提分特点
const SUBJECT_ANALYSIS: Record<string, {
  trait: string;
  strategy: string;
  stars: number; // 提分性价比 1-5
  difficulty: string;
}> = {
  数学: {
    trait: "模块化强，差距大，提分空间大",
    strategy: "有完整题库+AI诊断，模块化提分清晰",
    stars: 5,
    difficulty: "中",
  },
  英语: {
    trait: "听说 40 分有固定模式可突破",
    strategy: "听说机考模拟 + 阅读完形专项",
    stars: 4,
    difficulty: "中",
  },
  物理: {
    trait: "公式+实验，有规律可循",
    strategy: "力学+电学公式体系 + 实验操作备考",
    stars: 3,
    difficulty: "中高",
  },
  道法: {
    trait: "开卷考试，答题框架 > 死记硬背",
    strategy: "掌握材料分析答题模板",
    stars: 3,
    difficulty: "低",
  },
  语文: {
    trait: "高分段提分难，作文主观性强",
    strategy: "维持现状，作文素材积累",
    stars: 1,
    difficulty: "高",
  },
  体育: {
    trait: "过程性 20 分基本固定，现场 30 分可训练",
    strategy: "体能训练，非学科学习时间",
    stars: 2,
    difficulty: "低",
  },
};

// 提分性价比排序权重（结合科目特点和分差）
function calculateROI(subject: string, current: number, max: number): number {
  const gap = max - current;
  const ratio = gap / max;
  const baseStars = SUBJECT_ANALYSIS[subject]?.stars || 1;
  // ROI = 分差比例 * 性价比系数
  return ratio * baseStars;
}

// 预估提分（保守区间）
function estimateGain(subject: string, current: number, max: number): { min: number; max: number } {
  const gap = max - current;
  if (gap <= 0) return { min: 0, max: 0 };
  const analysis = SUBJECT_ANALYSIS[subject];
  if (!analysis) return { min: 0, max: 0 };

  // 根据性价比和难度估算可提升比例
  let ratio: number;
  if (analysis.stars >= 4) ratio = 0.5;       // 高性价比科目可提升 50% 的差距
  else if (analysis.stars >= 3) ratio = 0.4;
  else if (analysis.stars >= 2) ratio = 0.3;
  else ratio = 0.2;                            // 语文等高分段难提升

  const est = Math.round(gap * ratio);
  return { min: Math.max(1, est - 2), max: est + 2 };
}

// 建议时间占比
function suggestTimePercent(subject: string, roi: number, totalROI: number): number {
  if (subject === "体育") return 0; // 体育不占学科学习时间
  if (totalROI <= 0) return 20;
  return Math.round((roi / totalROI) * 100);
}

const SUBJECT_KEYS = ["语文", "数学", "英语", "物理", "道法", "体育"] as const;

interface SubjectData {
  name: string;
  current: number;
  max: number;
  gap: number;
  roi: number;
  gain: { min: number; max: number };
  timePercent: number;
  analysis: typeof SUBJECT_ANALYSIS["数学"];
}

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

  // 从 URL 参数读取
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const subjectsJson = params.get("subjects");
    if (subjectsJson) {
      try {
        const parsed = JSON.parse(subjectsJson);
        setSubjects(parsed);
      } catch { /* ignore */ }
    }
    const d = params.get("district");
    if (d) setDistrict(d);
    const ts = params.get("targetScore");
    if (ts) setTargetScore(parseInt(ts) || 0);
    const tSchool = params.get("target");
    if (tSchool) setTargetSchool(tSchool);
    // 如果有 subjects 参数，自动显示结果
    if (subjectsJson) setShowResult(true);
    setLoaded(true);
  }, []);

  const totalScore = Object.values(subjects).reduce((a, b) => a + b, 0);
  const days = daysUntilZhongkao();
  const weeks = Math.floor(days / 7);

  // 找目标校分数线
  const schools = (SCHOOLS_BY_DISTRICT as Record<string, School[]>)[district] || [];
  const targetSchoolData = schools.find(s => s.name === targetSchool);
  const effectiveTarget = targetScore || targetSchoolData?.refScore || totalScore + 50;

  // 各科分析
  const subjectDataList: SubjectData[] = SUBJECT_KEYS.map((name) => {
    const current = subjects[name] || 0;
    const max = SUBJECT_MAX[name];
    const gap = max - current;
    const roi = calculateROI(name, current, max);
    const gain = estimateGain(name, current, max);
    const analysis = SUBJECT_ANALYSIS[name];
    return { name, current, max, gap, roi, gain, timePercent: 0, analysis };
  });

  // 计算时间分配（排除体育）
  const academicSubjects = subjectDataList.filter(s => s.name !== "体育");
  const totalROI = academicSubjects.reduce((s, d) => s + d.roi, 0);
  for (const s of subjectDataList) {
    s.timePercent = suggestTimePercent(s.name, s.roi, totalROI);
  }
  // 修正百分比为 100
  const pctSum = subjectDataList.reduce((s, d) => s + d.timePercent, 0);
  if (pctSum !== 100 && subjectDataList.length > 0) {
    const top = subjectDataList.reduce((a, b) => a.timePercent > b.timePercent ? a : b);
    top.timePercent += 100 - pctSum;
  }

  // 按性价比排序
  const sorted = [...subjectDataList].filter(s => s.name !== "体育").sort((a, b) => b.roi - a.roi);

  // 总提分预期
  const totalGainMin = subjectDataList.reduce((s, d) => s + d.gain.min, 0);
  const totalGainMax = subjectDataList.reduce((s, d) => s + d.gain.max, 0);
  const projectedScore = totalScore + Math.round((totalGainMin + totalGainMax) / 2);

  // 目标校匹配概率估算
  const currentProb = effectiveTarget <= totalScore ? 95 : Math.max(5, 95 - Math.round((effectiveTarget - totalScore) * 1.2));
  const projectedProb = effectiveTarget <= projectedScore ? 90 : Math.max(10, 90 - Math.round((effectiveTarget - projectedScore) * 1.0));

  function updateSubject(key: string, val: number) {
    setSubjects(prev => ({ ...prev, [key]: val }));
    setShowResult(false);
  }

  if (!loaded) return null;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
          &larr; 返回首页
        </Link>
      </div>
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          📊 全科诊断解读
        </h1>
        <p className="text-gray-500">输入各科成绩，看看从哪里提分最有效</p>
        <p className="text-xs text-orange-600 mt-2">
          距 2026 中考还有 {days} 天（{weeks} 周）
        </p>
      </div>

      {/* 输入区 */}
      {!showResult && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">各科最近成绩</h2>
          <div className="grid grid-cols-3 gap-3 mb-4">
            {SUBJECT_KEYS.map((sub) => (
              <div key={sub}>
                <label className="block text-xs text-gray-500 mb-1">{sub}</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                    value={subjects[sub]}
                    onChange={(e) =>
                      updateSubject(sub, Math.min(SUBJECT_MAX[sub], Math.max(0, parseInt(e.target.value) || 0)))
                    }
                    min={0}
                    max={SUBJECT_MAX[sub]}
                  />
                  <span className="text-xs text-gray-400 whitespace-nowrap">/{SUBJECT_MAX[sub]}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="text-right text-sm text-indigo-600 font-medium mb-4">
            总分：{totalScore} / {TOTAL_MAX}
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">所在区</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                value={district}
                onChange={(e) => { setDistrict(e.target.value); setTargetSchool(""); }}
              >
                <option>朝阳区</option>
                <option>海淀区</option>
                <option>西城区</option>
                <option>东城区</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">每天学习时间</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
                value={hoursPerDay}
                onChange={(e) => setHoursPerDay(parseFloat(e.target.value))}
              >
                <option value={1}>1 小时</option>
                <option value={1.5}>1.5 小时</option>
                <option value={2}>2 小时</option>
                <option value={2.5}>2.5 小时</option>
                <option value={3}>3 小时</option>
              </select>
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-xs text-gray-500 mb-1">目标学校（可选）</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-gray-800"
              value={targetSchool}
              onChange={(e) => {
                setTargetSchool(e.target.value);
                const s = schools.find(s => s.name === e.target.value);
                if (s) setTargetScore(s.refScore);
              }}
            >
              <option value="">不指定</option>
              {schools.map(s => (
                <option key={s.name} value={s.name}>{s.name}（{s.tier} · 参考线 {s.refScore}）</option>
              ))}
            </select>
          </div>

          <div className="text-center">
            <button
              onClick={() => setShowResult(true)}
              className="px-10 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-xl font-medium text-lg hover:from-indigo-700 hover:to-purple-700 transition-all shadow-md"
            >
              开始诊断分析
            </button>
          </div>
        </div>
      )}

      {/* 结果区 */}
      {showResult && (
        <div className="space-y-4 animate-in fade-in duration-300">
          {/* 总览 */}
          <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl border border-indigo-100 p-5">
            <div className="grid grid-cols-3 gap-4 text-center mb-4">
              <div>
                <div className="text-3xl font-bold text-indigo-700">{totalScore}</div>
                <div className="text-xs text-indigo-500 mt-1">当前总分</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-green-600">+{totalGainMin}-{totalGainMax}</div>
                <div className="text-xs text-green-500 mt-1">预计可提升</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-purple-600">{projectedScore}</div>
                <div className="text-xs text-purple-500 mt-1">预期总分</div>
              </div>
            </div>
            {targetSchool && (
              <div className="bg-white/60 rounded-lg p-3 text-center">
                <p className="text-sm text-gray-700">
                  目标：<span className="font-medium">{targetSchool}</span>（参考线 {effectiveTarget} 分）
                </p>
                <p className="text-sm mt-1">
                  达标概率：
                  <span className="text-gray-500">{currentProb}%（当前）</span>
                  <span className="mx-2">→</span>
                  <span className="text-green-600 font-medium">{projectedProb}%（按方案执行后）</span>
                </p>
              </div>
            )}
          </div>

          {/* 各科提分性价比 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-4">各科提分性价比分析</h3>
            <p className="text-xs text-gray-500 mb-4">
              按提分效率从高到低排列，优先投入前 2-3 科
            </p>
            <div className="space-y-4">
              {sorted.map((s, i) => (
                <div key={s.name} className={`rounded-lg p-4 ${i === 0 ? "bg-green-50 border border-green-200" : i === 1 ? "bg-blue-50 border border-blue-200" : "bg-gray-50 border border-gray-100"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-400">#{i + 1}</span>
                      <span className="font-semibold text-gray-800">{s.name}</span>
                      <span className="text-xs text-gray-400">{s.current}/{s.max}</span>
                    </div>
                    <div className="text-sm">
                      {"★".repeat(s.analysis.stars)}{"☆".repeat(5 - s.analysis.stars)}
                    </div>
                  </div>
                  <p className="text-sm text-gray-600 mb-2">{s.analysis.trait}</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    <span className="text-gray-500">差距 {s.gap} 分</span>
                    {s.gain.max > 0 && (
                      <span className="text-green-600 font-medium">预计可提 {s.gain.min}-{s.gain.max} 分</span>
                    )}
                    <span className="text-indigo-600">建议投入 {s.timePercent}% 时间（{Math.round(hoursPerDay * 60 * s.timePercent / 100)}分钟/天）</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">方案：{s.analysis.strategy}</p>
                </div>
              ))}

              {/* 体育单独说明 */}
              {(() => {
                const pe = subjectDataList.find(s => s.name === "体育");
                if (!pe) return null;
                return (
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-800">体育</span>
                      <span className="text-xs text-gray-400">{pe.current}/{pe.max}</span>
                    </div>
                    <p className="text-xs text-gray-500">
                      过程性考核 20 分基本固定，现场考试 30 分靠日常训练。建议另外安排体能训练时间，不占学科学习时间。
                      {pe.gain.max > 0 && <span className="text-green-600 ml-1">预计可提 {pe.gain.min}-{pe.gain.max} 分</span>}
                    </p>
                  </div>
                );
              })()}
            </div>
          </div>

          {/* 时间分配可视化 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-3">每日时间分配建议</h3>
            <p className="text-xs text-gray-500 mb-4">
              基于每天 {hoursPerDay} 小时学习时间
            </p>
            <div className="space-y-2">
              {sorted.filter(s => s.timePercent > 0).map((s) => {
                const minutes = Math.round(hoursPerDay * 60 * s.timePercent / 100);
                return (
                  <div key={s.name} className="flex items-center gap-3">
                    <span className="text-sm text-gray-700 w-16 shrink-0">{s.name}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                      <div
                        className={`h-5 rounded-full flex items-center px-2 text-xs text-white font-medium ${
                          s.name === "数学" ? "bg-green-500" :
                          s.name === "英语" ? "bg-blue-500" :
                          s.name === "物理" ? "bg-purple-500" :
                          s.name === "道法" ? "bg-amber-500" :
                          "bg-gray-400"
                        }`}
                        style={{ width: `${Math.max(s.timePercent, 8)}%` }}
                      >
                        {s.timePercent}%
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 w-16 text-right">{minutes} 分钟</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 阶段规划预览 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-3">阶段规划预览</h3>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="w-1 bg-green-400 rounded-full shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-800">阶段一：4月中 - 5月初（3 周）</p>
                  <p className="text-xs text-gray-500">
                    重点：{sorted[0]?.name}专项突破 + {sorted[1]?.name}基础巩固
                  </p>
                  <p className="text-xs text-green-600">里程碑：{sorted[0]?.name}薄弱模块升一级</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="w-1 bg-blue-400 rounded-full shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-800">阶段二：5月初 - 5月底（4 周）</p>
                  <p className="text-xs text-gray-500">
                    重点：{sorted[0]?.name}综合提升 + {sorted.length >= 3 ? sorted[2]?.name : sorted[1]?.name}突破
                  </p>
                  <p className="text-xs text-blue-600">里程碑：一模后重新评估，调整方案</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="w-1 bg-purple-400 rounded-full shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-800">阶段三：6月初 - 6月24日（3 周）</p>
                  <p className="text-xs text-gray-500">
                    重点：全科模考 + 查缺补漏 + 心态调整
                  </p>
                  <p className="text-xs text-purple-600">里程碑：二模后最终冲刺</p>
                </div>
              </div>
            </div>
          </div>

          {/* 结果承诺 */}
          <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border border-green-200 p-5">
            <h3 className="font-semibold text-green-800 mb-2">💡 总结</h3>
            <p className="text-sm text-gray-700 mb-3">
              核心策略：优先投入
              <span className="font-medium text-green-700">
                {sorted.slice(0, 2).map(s => s.name).join("和")}
              </span>
              ，这两科提分性价比最高。
            </p>
            <div className="bg-white/70 rounded-lg p-3">
              <p className="text-sm font-medium text-green-700">
                按方案执行到中考，总分预期达到 {totalScore + totalGainMin} - {totalScore + totalGainMax} 分
              </p>
              <p className="text-xs text-gray-500 mt-1">
                前提：每天执行 {hoursPerDay} 小时 · 基于各科成绩估算，做测评后预估更准确
              </p>
            </div>
          </div>

          {/* CTA */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-2">下一步</h3>
            <div className="flex gap-3">
              <Link
                href={`/plan?district=${encodeURIComponent(district)}&score=${subjects["数学"] || 78}&fromDiagnosis=1`}
                className="flex-1 text-center px-4 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-xl font-medium hover:from-green-700 hover:to-emerald-700 transition-colors"
              >
                生成数学详细计划
              </Link>
              <Link
                href="/assessment"
                className="flex-1 text-center px-4 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-xl font-medium hover:from-purple-700 hover:to-indigo-700 transition-colors"
              >
                先做数学测评
              </Link>
            </div>
            <p className="text-xs text-gray-400 text-center mt-3">
              做过数学测评后，数学部分的诊断和计划会更精准
            </p>
          </div>

          {/* 重新输入 */}
          <div className="text-center">
            <button
              onClick={() => setShowResult(false)}
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
