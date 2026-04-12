"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

const MODULE_NAMES: Record<string, string> = {
  numbersAndExpressions: "数与式",
  equationsAndInequalities: "方程与不等式",
  functions: "函数",
  triangles: "三角形",
  circles: "圆",
  statisticsAndProbability: "统计与概率",
  geometryComprehensive: "压轴题",
};

interface WeeklyReport {
  weekRange: { start: string; end: string };
  summary: {
    drillSessions: number;
    totalQuestions: number;
    avgCorrectRate: number;
    totalTimeMin: number;
    assessmentCount: number;
    examCount: number;
  };
  comparison: {
    questionsDelta: number;
    rateDelta: number | null;
    prevQuestions: number;
  };
  moduleStats: { moduleId: string; sessions: number; questions: number; avgRate: number }[];
  exams: { examName: string; examDate: string; totalScore: number; scores: Record<string, number> }[];
  assessments: { score: number; moduleResults: Record<string, any>; createdAt: string }[];
  profile: { completeness: number; currentScore: number; targetSchool: string } | null;
  hasData: boolean;
}

function formatDate(d: string) {
  const [, m, day] = d.split("-");
  return `${parseInt(m)}月${parseInt(day)}日`;
}

export default function WeeklyReportPage() {
  const { token, user } = useAuth();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [weeksAgo, setWeeksAgo] = useState(0);

  const isParent = user?.role === "parent";

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    fetch(`/api/report/weekly?weeks=${weeksAgo}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => { if (data.success) setReport(data.report); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, weeksAgo]);

  if (!token) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-12 text-center">
        <p className="text-gray-500 mb-4">登录后查看学习周报</p>
        <Link href="/login" className="text-blue-600 underline">去登录</Link>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      {/* 标题 + 周切换 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isParent ? "孩子的学习周报" : "本周学习周报"}
          </h1>
          {report && (
            <p className="text-sm text-gray-500 mt-1">
              {formatDate(report.weekRange.start)} — {formatDate(report.weekRange.end)}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setWeeksAgo((w) => w + 1)}
            className="px-3 py-1 border border-gray-300 rounded text-sm text-gray-600 hover:bg-gray-100"
          >
            &larr; 上周
          </button>
          {weeksAgo > 0 && (
            <button
              onClick={() => setWeeksAgo((w) => Math.max(0, w - 1))}
              className="px-3 py-1 border border-gray-300 rounded text-sm text-gray-600 hover:bg-gray-100"
            >
              下周 &rarr;
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      )}

      {!loading && report && !report.hasData && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <div className="text-4xl mb-4">📭</div>
          <h2 className="text-lg font-bold text-gray-900 mb-2">本周暂无学习记录</h2>
          <p className="text-sm text-gray-500 mb-6">
            {isParent
              ? "孩子本周还没有做测评或刷题，提醒一下吧"
              : "做几道题或测评一下，下周就有数据了"}
          </p>
          <div className="flex justify-center gap-3">
            <Link href="/assessment" className="px-5 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700">
              去测评
            </Link>
            <Link href="/drill" className="px-5 py-2 border border-blue-300 text-blue-600 rounded-lg text-sm hover:bg-blue-50">
              去刷题
            </Link>
          </div>
        </div>
      )}

      {!loading && report && report.hasData && (
        <>
          {/* 概览卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard
              label="做题数"
              value={report.summary.totalQuestions}
              unit="道"
              delta={report.comparison.questionsDelta}
              deltaLabel="vs上周"
            />
            <StatCard
              label="正确率"
              value={report.summary.avgCorrectRate}
              unit="%"
              delta={report.comparison.rateDelta}
              deltaLabel="vs上周"
            />
            <StatCard
              label="刷题次数"
              value={report.summary.drillSessions}
              unit="次"
            />
            <StatCard
              label="测评/模考"
              value={report.summary.assessmentCount + report.summary.examCount}
              unit="次"
            />
          </div>

          {/* 模块分布 */}
          {report.moduleStats.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
              <h2 className="text-sm font-semibold text-gray-800 mb-4">各模块练习情况</h2>
              <div className="space-y-3">
                {report.moduleStats
                  .sort((a, b) => b.questions - a.questions)
                  .map((m) => (
                    <div key={m.moduleId} className="flex items-center gap-3">
                      <span className="text-sm text-gray-700 w-24 shrink-0">
                        {MODULE_NAMES[m.moduleId] || m.moduleId}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${m.avgRate >= 80 ? "bg-green-400" : m.avgRate >= 60 ? "bg-yellow-400" : "bg-red-400"}`}
                          style={{ width: `${Math.max(8, m.avgRate)}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-gray-700 w-12 text-right">{m.avgRate}%</span>
                      <span className="text-xs text-gray-400 w-16 text-right">{m.questions}题</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* 模考成绩 */}
          {report.exams.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
              <h2 className="text-sm font-semibold text-gray-800 mb-4">本周模考成绩</h2>
              {report.exams.map((e, i) => (
                <div key={i} className="border border-gray-100 rounded-lg p-4 mb-2 last:mb-0">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-gray-900 text-sm">{e.examName}</span>
                    <span className="text-lg font-bold text-gray-900">{e.totalScore}<span className="text-sm text-gray-400 font-normal">/510</span></span>
                  </div>
                  <div className="flex gap-3 flex-wrap">
                    {Object.entries(e.scores).map(([subj, score]) => (
                      <span key={subj} className="text-xs text-gray-500">
                        {subj} <span className="font-medium text-gray-700">{score}</span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 建议 */}
          <div className="bg-blue-50 rounded-xl border border-blue-200 p-6 mb-6">
            <h2 className="text-sm font-semibold text-blue-800 mb-3">
              {isParent ? "本周建议" : "下周重点"}
            </h2>
            <WeeklySuggestions report={report} isParent={isParent} />
          </div>

          {/* 画像进度 */}
          {report.profile && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-gray-800">学习画像完整度</h2>
                  <p className="text-xs text-gray-400 mt-1">越完整，AI 规划越精准</p>
                </div>
                <div className="text-2xl font-bold text-blue-600">{report.profile.completeness}%</div>
              </div>
              <div className="mt-3 bg-gray-100 rounded-full h-2 overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${report.profile.completeness}%` }} />
              </div>
            </div>
          )}

          {/* 操作 */}
          <div className="flex justify-center gap-4 mb-8">
            <Link href="/drill" className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
              继续刷题
            </Link>
            <Link href="/plan" className="px-5 py-2 border border-green-300 text-green-600 rounded-lg text-sm hover:bg-green-50">
              更新学习计划
            </Link>
          </div>
        </>
      )}
    </main>
  );
}

function StatCard({ label, value, unit, delta, deltaLabel }: {
  label: string; value: number; unit: string; delta?: number | null; deltaLabel?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-900">
        {value}<span className="text-sm text-gray-400 font-normal">{unit}</span>
      </div>
      {delta !== undefined && delta !== null && (
        <div className={`text-xs mt-1 ${delta >= 0 ? "text-green-600" : "text-red-500"}`}>
          {delta >= 0 ? "+" : ""}{delta}{unit} {deltaLabel}
        </div>
      )}
    </div>
  );
}

function WeeklySuggestions({ report, isParent }: { report: WeeklyReport; isParent: boolean }) {
  const suggestions: string[] = [];

  // 做题量建议
  if (report.summary.totalQuestions === 0) {
    suggestions.push(isParent ? "本周没有做题记录，建议提醒孩子每天至少做 5 道题" : "本周还没做题，每天 5 道就能保持手感");
  } else if (report.summary.totalQuestions < 20) {
    suggestions.push(isParent ? "做题量偏少，建议增加到每周 30 题以上" : "做题量可以再加一点，目标每周 30 题");
  } else {
    suggestions.push(isParent ? "做题量不错，保持节奏" : "做题节奏很好，继续保持");
  }

  // 正确率建议
  if (report.summary.avgCorrectRate > 0 && report.summary.avgCorrectRate < 60) {
    suggestions.push(isParent ? "正确率偏低，可能题目难度太高，建议先巩固基础" : "正确率不高，先把基础题吃透再挑战难题");
  } else if (report.summary.avgCorrectRate >= 80) {
    suggestions.push(isParent ? "正确率很高，可以适当提升难度" : "正确率不错，试试挑战更难的题型");
  }

  // 薄弱模块
  const weakModules = report.moduleStats.filter((m) => m.avgRate < 60);
  if (weakModules.length > 0) {
    const names = weakModules.map((m) => MODULE_NAMES[m.moduleId] || m.moduleId).join("、");
    suggestions.push(isParent
      ? `${names} 正确率较低，建议重点突破`
      : `${names} 还需要多练，去专项突破试试`);
  }

  // 对比上周
  if (report.comparison.rateDelta !== null) {
    if (report.comparison.rateDelta > 5) {
      suggestions.push(isParent ? "正确率比上周提升了，值得表扬" : "比上周进步了，继续加油");
    } else if (report.comparison.rateDelta < -10) {
      suggestions.push(isParent ? "正确率比上周下降了，关注一下状态" : "比上周有些下滑，调整一下状态");
    }
  }

  if (suggestions.length === 0) {
    suggestions.push("保持当前节奏，稳步提升");
  }

  return (
    <ul className="space-y-2">
      {suggestions.map((s, i) => (
        <li key={i} className="text-sm text-blue-700 flex items-start gap-2">
          <span className="mt-0.5 shrink-0">•</span>
          <span>{s}</span>
        </li>
      ))}
    </ul>
  );
}
