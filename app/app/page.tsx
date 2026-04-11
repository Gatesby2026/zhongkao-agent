"use client";

import { useState } from "react";

type SelfAssessment = "很差" | "薄弱" | "还行" | "不错" | "擅长";

interface FormData {
  district: string;
  totalScore: number;
  availableHoursPerDay: number;
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

const ASSESSMENTS: SelfAssessment[] = ["很差", "薄弱", "还行", "不错", "擅长"];

const ASSESSMENT_COLORS: Record<SelfAssessment, string> = {
  "很差": "bg-red-100 text-red-700 border-red-300",
  "薄弱": "bg-orange-100 text-orange-700 border-orange-300",
  "还行": "bg-yellow-100 text-yellow-700 border-yellow-300",
  "不错": "bg-green-100 text-green-700 border-green-300",
  "擅长": "bg-emerald-100 text-emerald-700 border-emerald-300",
};

// 计算距2026年中考的天数
function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(1, Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function Home() {
  const [formData, setFormData] = useState<FormData>({
    district: "海淀区",
    totalScore: 75,
    availableHoursPerDay: 1.5,
    targetSchoolScore: "",
    daysUntilExam: daysUntilZhongkao(),
    modules: {
      numbersAndExpressions: "还行",
      equationsAndInequalities: "薄弱",
      functions: "很差",
      triangles: "还行",
      circles: "薄弱",
      statisticsAndProbability: "不错",
      geometryComprehensive: "很差",
    },
  });

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string>("");

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch("/api/generate-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          district: formData.district,
          totalScore: formData.totalScore,
          availableHoursPerDay: formData.availableHoursPerDay,
          targetSchoolScore: formData.targetSchoolScore ? parseInt(formData.targetSchoolScore) : undefined,
          daysUntilExam: formData.daysUntilExam,
          moduleAssessments: formData.modules,
        }),
      });

      const data = await res.json();
      if (data.success) {
        setResult(data);
      } else {
        setError(data.error || "生成失败，请重试");
      }
    } catch (err: any) {
      setError(err.message || "网络错误");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">中考数学·智能学习规划</h1>
        <p className="text-gray-500">基于北京中考知识库，AI 为你定制个性化提分方案</p>
      </div>

      {/* 输入表单 */}
      {!result && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          {/* 基本信息 */}
          <h2 className="text-lg font-semibold text-gray-800 mb-4">基本信息</h2>
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">所在区</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.district}
                onChange={(e) => setFormData({ ...formData, district: e.target.value })}
              >
                <option>海淀区</option>
                <option>西城区</option>
                <option>东城区</option>
                <option>朝阳区</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">最近一次数学成绩（满分100）</label>
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.totalScore}
                onChange={(e) => setFormData({ ...formData, totalScore: parseInt(e.target.value) || 0 })}
                min={0}
                max={100}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">每天可用数学学习时间</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                value={formData.availableHoursPerDay}
                onChange={(e) => setFormData({ ...formData, availableHoursPerDay: parseFloat(e.target.value) })}
              >
                <option value={0.5}>半小时</option>
                <option value={1}>1小时</option>
                <option value={1.5}>1.5小时</option>
                <option value={2}>2小时</option>
                <option value={2.5}>2.5小时</option>
                <option value={3}>3小时</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">目标分数（可不填）</label>
              <input
                type="number"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800"
                placeholder="如：85"
                value={formData.targetSchoolScore}
                onChange={(e) => setFormData({ ...formData, targetSchoolScore: e.target.value })}
                min={0}
                max={100}
              />
            </div>
          </div>

          {/* 各模块自评 */}
          <h2 className="text-lg font-semibold text-gray-800 mb-4">各模块自评</h2>
          <p className="text-sm text-gray-500 mb-4">根据你的真实感受选择，越准确规划越精准</p>

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
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  AI 正在生成学习规划...（约30秒）
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
        </div>
      )}

      {/* 结果展示 */}
      {result && (
        <div>
          {/* 诊断概览 */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">诊断概览</h2>
            <div className="grid grid-cols-4 gap-4 mb-4 text-center">
              <div className="bg-blue-50 rounded-lg p-3">
                <div className="text-2xl font-bold text-blue-700">{result.diagnosis.totalScore}</div>
                <div className="text-xs text-blue-500">当前成绩</div>
              </div>
              <div className="bg-green-50 rounded-lg p-3">
                <div className="text-2xl font-bold text-green-700">+{result.diagnosis.potentialGain}</div>
                <div className="text-xs text-green-500">预计可提分</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-3">
                <div className="text-2xl font-bold text-purple-700">{result.diagnosis.weeksUntilExam}周</div>
                <div className="text-xs text-purple-500">距中考</div>
              </div>
              <div className="bg-orange-50 rounded-lg p-3">
                <div className="text-2xl font-bold text-orange-700">{result.diagnosis.totalWeeklyHours}h</div>
                <div className="text-xs text-orange-500">每周学习时间</div>
              </div>
            </div>

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
                  {result.diagnosis.modules.map((m: any) => {
                    const alloc = result.diagnosis.timeAllocation.find((t: any) => t.moduleId === m.id);
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
                        <td className="py-2 text-center text-gray-600">{m.currentEstimatedScore}分</td>
                        <td className="py-2 text-center text-green-600 font-medium">+{m.potentialGain}</td>
                        <td className="py-2 text-center text-gray-600">{alloc?.percentage || 0}%</td>
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

          {/* AI 生成的学习规划 */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">AI 学习规划</h2>
            <div
              className="prose prose-sm max-w-none text-gray-700 prose-headings:text-gray-900 prose-strong:text-gray-900 prose-h2:text-lg prose-h3:text-base"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(result.plan) }}
            />
          </div>

          {/* 重新开始按钮 */}
          <div className="text-center mb-8">
            <button
              onClick={() => setResult(null)}
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

// 简易 Markdown → HTML 转换（不引入额外依赖）
function markdownToHtml(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // 标题
    .replace(/^### (.+)$/gm, '<h3 class="font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="font-bold mt-6 mb-3 text-lg">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="font-bold mt-6 mb-3 text-xl">$1</h1>')
    // 粗体和斜体
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // 无序列表
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // 有序列表
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // 代码块
    .replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 rounded text-sm">$1</code>')
    // 分隔线
    .replace(/^---$/gm, '<hr class="my-4 border-gray-200">')
    // 段落
    .replace(/\n\n/g, '</p><p class="mb-3">')
    // 换行
    .replace(/\n/g, "<br>")
    // 包裹段落
    .replace(/^/, '<p class="mb-3">')
    .replace(/$/, "</p>");
}
