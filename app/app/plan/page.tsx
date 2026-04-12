"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";

type SelfAssessment = "很差" | "薄弱" | "还行" | "不错" | "擅长" | "不确定";

interface FormData {
  district: string;
  totalScore: number;
  availableHoursPerDay: number;
  targetSchool: string;
  targetSchoolScore: string;
  daysUntilExam: number;
  modules: {
    numbersAndExpressions: SelfAssessment;
    equationsAndInequalities: SelfAssessment;
    functions: SelfAssessment;
    triangles: SelfAssessment;
    circles: SelfAssessment;
    statisticsAndProbability: SelfAssessment;
    geometryComprehensive: SelfAssessment;
  };
}

const MODULE_NAMES: Record<string, string> = {
  numbersAndExpressions: "计算/数与式（实数运算、因式分解、分式）",
  equationsAndInequalities: "方程与不等式（一元二次方程、分式方程、应用题）",
  functions: "函数（一次函数、反比例函数、二次函数）",
  triangles: "三角形（全等、相似、勾股定理、三角函数）",
  circles: "圆（垂径定理、圆周角、切线）",
  statisticsAndProbability: "统计与概率（平均数、方差、树状图）",
  geometryComprehensive: "压轴题（几何综合、动态几何、代几综合）",
};

const ASSESSMENTS: SelfAssessment[] = ["不确定", "很差", "薄弱", "还行", "不错", "擅长"];

const ASSESSMENT_COLORS: Record<SelfAssessment, string> = {
  "不确定": "bg-gray-100 text-gray-600 border-gray-300",
  "很差": "bg-red-100 text-red-700 border-red-300",
  "薄弱": "bg-orange-100 text-orange-700 border-orange-300",
  "还行": "bg-yellow-100 text-yellow-700 border-yellow-300",
  "不错": "bg-green-100 text-green-700 border-green-300",
  "擅长": "bg-emerald-100 text-emerald-700 border-emerald-300",
};

// 各区学校列表（按层级排列）
const SCHOOLS_BY_DISTRICT: Record<string, { name: string; tier: string; refScore: number }[]> = {
  "朝阳区": [
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
  "海淀区": [
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
  "西城区": [
    { name: "北师大实验中学", tier: "顶尖", refScore: 95 },
    { name: "北京四中", tier: "顶尖", refScore: 93 },
    { name: "北京八中", tier: "顶尖", refScore: 92 },
    { name: "北师大附中", tier: "重点", refScore: 90 },
    { name: "北师大二附中", tier: "重点", refScore: 90 },
    { name: "161中学", tier: "重点", refScore: 85 },
    { name: "三十五中", tier: "普通", refScore: 82 },
    { name: "十三中", tier: "普通", refScore: 82 },
  ],
  "东城区": [
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

const TIER_COLORS: Record<string, string> = {
  "顶尖": "text-red-600",
  "重点": "text-blue-600",
  "普通": "text-gray-600",
  "保底": "text-gray-400",
};

function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(1, Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function Home() {
  // 支持从 /score-check 跳转时通过 URL 参数预填
  const searchParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const urlDistrict = searchParams?.get("district") || "朝阳区";
  const urlScore = parseInt(searchParams?.get("score") || "75") || 75;

  const [formData, setFormData] = useState<FormData>({
    district: urlDistrict,
    totalScore: urlScore,
    availableHoursPerDay: 1.5,
    targetSchool: "",
    targetSchoolScore: "",
    daysUntilExam: daysUntilZhongkao(),
    modules: {
      numbersAndExpressions: "不确定",
      equationsAndInequalities: "不确定",
      functions: "不确定",
      triangles: "不确定",
      circles: "不确定",
      statisticsAndProbability: "不确定",
      geometryComprehensive: "不确定",
    },
  });

  const [loading, setLoading] = useState(false);
  const [diagnosis, setDiagnosis] = useState<any>(null);
  const [plan, setPlan] = useState("");
  const [error, setError] = useState("");
  const planRef = useRef<HTMLDivElement>(null);

  // 选择学校时自动设置目标分数
  const handleSchoolChange = (schoolName: string) => {
    setFormData((prev) => {
      const schools = SCHOOLS_BY_DISTRICT[prev.district] || [];
      const school = schools.find((s) => s.name === schoolName);
      return {
        ...prev,
        targetSchool: schoolName,
        targetSchoolScore: school ? String(school.refScore) : prev.targetSchoolScore,
      };
    });
  };

  // 切换区时清空学校选择
  const handleDistrictChange = (district: string) => {
    setFormData((prev) => ({
      ...prev,
      district,
      targetSchool: "",
      targetSchoolScore: "",
    }));
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    setDiagnosis(null);
    setPlan("");

    try {
      const res = await fetch("/api/generate-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          district: formData.district,
          totalScore: formData.totalScore,
          availableHoursPerDay: formData.availableHoursPerDay,
          targetSchoolScore: formData.targetSchoolScore ? parseInt(formData.targetSchoolScore) : undefined,
          targetSchool: formData.targetSchool || undefined,
          daysUntilExam: formData.daysUntilExam,
          moduleAssessments: formData.modules,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "生成失败");
      }

      // SSE 流式读取
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
            if (parsed.type === "diagnosis") {
              setDiagnosis(parsed.diagnosis);
              setLoading(false); // 收到诊断结果就可以展示了
            } else if (parsed.content) {
              setPlan((prev) => prev + parsed.content);
            } else if (parsed.error) {
              setError(parsed.error);
            }
          } catch {
            // 忽略
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "网络错误");
      setLoading(false);
    }
  };

  // 自动滚动到底部
  useEffect(() => {
    if (planRef.current && plan) {
      planRef.current.scrollTop = planRef.current.scrollHeight;
    }
  }, [plan]);

  const schools = SCHOOLS_BY_DISTRICT[formData.district] || [];
  const showResults = diagnosis || plan;

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">📊 数学全面规划</h1>
        <p className="text-gray-500">
          全面诊断 7 个模块，生成整体路线图 + 本周详细计划
        </p>
        <p className="text-xs text-gray-400 mt-1">
          距 2026 中考还有 {formData.daysUntilExam} 天（{Math.floor(formData.daysUntilExam / 7)} 周）
        </p>
      </div>

      {/* 输入表单 */}
      {!showResults && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">基本信息</h2>
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">所在区</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.district}
                onChange={(e) => handleDistrictChange(e.target.value)}
              >
                <option>朝阳区</option>
                <option>海淀区</option>
                <option>西城区</option>
                <option>东城区</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">
                最近一次数学成绩（满分100）
              </label>
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.totalScore}
                onChange={(e) =>
                  setFormData({ ...formData, totalScore: parseInt(e.target.value) || 0 })
                }
                min={0}
                max={100}
              />
            </div>

            {/* 目标学校选择器 */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-600 mb-1">
                目标学校（选一个你最想上的）
              </label>
              <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-3">
                {schools.map((s) => (
                  <button
                    key={s.name}
                    onClick={() => handleSchoolChange(s.name)}
                    className={`text-left px-3 py-2 rounded-lg text-sm transition-all ${
                      formData.targetSchool === s.name
                        ? "bg-blue-50 border-blue-400 border-2 font-medium"
                        : "border border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <span className={TIER_COLORS[s.tier]}>{s.name}</span>
                    <span className="block text-xs text-gray-400 mt-0.5">
                      数学参考 {s.refScore}+ · {s.tier}
                    </span>
                  </button>
                ))}
              </div>
              {formData.targetSchool && (
                <p className="text-sm text-blue-600 mt-2">
                  已选择：{formData.targetSchool}（数学目标 {formData.targetSchoolScore} 分）
                  <button
                    className="ml-2 text-gray-400 hover:text-gray-600"
                    onClick={() => setFormData({ ...formData, targetSchool: "", targetSchoolScore: "" })}
                  >
                    清除
                  </button>
                </p>
              )}
              {!formData.targetSchool && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-xs text-gray-400">或直接填目标分数：</span>
                  <input
                    type="number"
                    className="w-20 border border-gray-300 rounded px-2 py-1 text-sm text-gray-800"
                    placeholder="如 85"
                    value={formData.targetSchoolScore}
                    onChange={(e) => setFormData({ ...formData, targetSchoolScore: e.target.value })}
                    min={0}
                    max={100}
                  />
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">
                每天可用数学学习时间
              </label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.availableHoursPerDay}
                onChange={(e) =>
                  setFormData({ ...formData, availableHoursPerDay: parseFloat(e.target.value) })
                }
              >
                <option value={0.5}>半小时</option>
                <option value={1}>1小时</option>
                <option value={1.5}>1.5小时</option>
                <option value={2}>2小时</option>
                <option value={2.5}>2.5小时</option>
                <option value={3}>3小时</option>
              </select>
            </div>
          </div>

          {/* 各模块自评 */}
          <h2 className="text-lg font-semibold text-gray-800 mb-4">各模块自评（可选）</h2>
          <p className="text-sm text-gray-500 mb-4">
            不确定的模块可以不改，系统会根据你的总分自动推算。知道的越多，规划越精准。
          </p>

          <div className="space-y-3">
            {Object.entries(MODULE_NAMES).map(([key, name]) => (
              <div key={key} className="flex items-center gap-3">
                <span className="text-sm text-gray-700 w-80 shrink-0">{name}</span>
                <div className="flex gap-2">
                  {ASSESSMENTS.map((a) => (
                    <button
                      key={a}
                      className={`px-3 py-1 text-sm rounded-full border transition-all ${
                        formData.modules[key as keyof typeof formData.modules] === a
                          ? ASSESSMENT_COLORS[a] + " font-medium"
                          : "bg-gray-50 text-gray-400 border-gray-200 hover:bg-gray-100"
                      }`}
                      onClick={() =>
                        setFormData({
                          ...formData,
                          modules: { ...formData.modules, [key]: a },
                        })
                      }
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* 提交按钮 */}
          <div className="mt-8 text-center">
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="px-8 py-3 bg-blue-600 text-white rounded-xl font-medium text-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  正在诊断...
                </span>
              ) : (
                "生成我的学习规划"
              )}
            </button>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <p className="text-red-700">{error}</p>
          <button
            className="mt-2 text-sm text-red-500 underline"
            onClick={() => {
              setError("");
              setDiagnosis(null);
              setPlan("");
            }}
          >
            重试
          </button>
        </div>
      )}

      {/* 结果展示 */}
      {showResults && (
        <div>
          {/* 诊断概览 */}
          {diagnosis && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">诊断概览</h2>
              <div className="grid grid-cols-4 gap-4 mb-4 text-center">
                <div className="bg-blue-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-blue-700">{diagnosis.totalScore}</div>
                  <div className="text-xs text-blue-500">当前成绩</div>
                </div>
                <div className="bg-green-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-green-700">
                    {diagnosis.targetScore}
                  </div>
                  <div className="text-xs text-green-500">目标分数</div>
                </div>
                <div className="bg-purple-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-purple-700">
                    {diagnosis.weeksUntilExam}周
                  </div>
                  <div className="text-xs text-purple-500">距中考</div>
                </div>
                <div className="bg-orange-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-orange-700">
                    +{diagnosis.potentialGain}
                  </div>
                  <div className="text-xs text-orange-500">预计可提分</div>
                </div>
              </div>

              {formData.targetSchool && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-center">
                  <span className="text-blue-800 font-medium">
                    目标：{formData.targetSchool}
                  </span>
                  <span className="text-blue-600 text-sm ml-2">
                    数学需要 {formData.targetSchoolScore}+ 分
                  </span>
                </div>
              )}

              {/* 模块水平表格 */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 text-gray-500 font-medium">模块</th>
                      <th className="text-center py-2 text-gray-500 font-medium">水平</th>
                      <th className="text-center py-2 text-gray-500 font-medium">预估分</th>
                      <th className="text-center py-2 text-gray-500 font-medium">可提分</th>
                      <th className="text-center py-2 text-gray-500 font-medium">时间占比</th>
                      <th className="text-center py-2 text-gray-500 font-medium">优先级</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diagnosis.modules.map((m: any) => {
                      const alloc = diagnosis.timeAllocation.find(
                        (t: any) => t.moduleId === m.id
                      );
                      return (
                        <tr key={m.id} className="border-b border-gray-100">
                          <td className="py-2 text-gray-800">{m.name}</td>
                          <td className="py-2 text-center">
                            <span
                              className={`px-2 py-0.5 rounded text-xs font-medium ${
                                m.level === "L0"
                                  ? "bg-red-100 text-red-700"
                                  : m.level === "L1"
                                  ? "bg-orange-100 text-orange-700"
                                  : m.level === "L2"
                                  ? "bg-green-100 text-green-700"
                                  : "bg-emerald-100 text-emerald-700"
                              }`}
                            >
                              {m.level} {m.levelName}
                            </span>
                          </td>
                          <td className="py-2 text-center text-gray-600">
                            {m.currentEstimatedScore}分
                          </td>
                          <td className="py-2 text-center text-green-600 font-medium">
                            +{m.potentialGain}
                          </td>
                          <td className="py-2 text-center text-gray-600">
                            {alloc?.percentage || 0}%
                          </td>
                          <td className="py-2 text-center">
                            {m.priority <= 3 ? (
                              <span className="text-red-600 font-bold">#{m.priority}</span>
                            ) : (
                              <span className="text-gray-400">#{m.priority}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* AI 生成的学习规划（流式） */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">
              AI 学习规划
              {plan && !plan.includes("[DONE]") && plan.length < 50 && (
                <span className="ml-2 text-sm font-normal text-gray-400 animate-pulse">
                  生成中...
                </span>
              )}
            </h2>
            {!plan && !error && (
              <div className="flex items-center gap-2 text-gray-400">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                AI 正在基于五年真题数据生成个性化规划...
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

          {/* 重新开始 */}
          <div className="text-center mb-8">
            <button
              onClick={() => {
                setDiagnosis(null);
                setPlan("");
                setError("");
              }}
              className="px-6 py-2 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
            >
              重新填写
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

// Markdown → HTML
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
