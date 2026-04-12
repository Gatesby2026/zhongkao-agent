"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

const SUBJECTS = [
  { name: "语文", max: 100 },
  { name: "数学", max: 100 },
  { name: "英语", max: 100 },
  { name: "物理", max: 80 },
  { name: "道法", max: 80 },
  { name: "体育", max: 50 },
];

const EXAM_TYPES = [
  { id: "一模", name: "一模" },
  { id: "二模", name: "二模" },
  { id: "期中", name: "期中考试" },
  { id: "期末", name: "期末考试" },
  { id: "月考", name: "月考" },
];

const DISTRICTS = ["海淀区", "朝阳区", "西城区", "东城区"];

interface ExamRecord {
  id: number;
  examName: string;
  examDate: string;
  district: string;
  scores: Record<string, number>;
  totalScore: number;
  createdAt: string;
}

export default function ExamPage() {
  const { token } = useAuth();

  // 输入状态
  const [examName, setExamName] = useState("一模");
  const [examDate, setExamDate] = useState(() => {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  });
  const [district, setDistrict] = useState("海淀区");
  const [scores, setScores] = useState<Record<string, string>>({});

  // 历史记录
  const [records, setRecords] = useState<ExamRecord[]>([]);
  const [loadingRecords, setLoadingRecords] = useState(false);

  // 提交状态
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  // 加载历史记录
  useEffect(() => {
    if (!token) return;
    setLoadingRecords(true);
    fetch("/api/profile/exam", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success) setRecords(data.records);
      })
      .catch(() => {})
      .finally(() => setLoadingRecords(false));
  }, [token, saved]);

  const totalScore = SUBJECTS.reduce((sum, s) => {
    const v = parseInt(scores[s.name] || "0", 10);
    return sum + (isNaN(v) ? 0 : v);
  }, 0);

  const filledCount = SUBJECTS.filter((s) => scores[s.name] && scores[s.name] !== "").length;

  const handleSubmit = async () => {
    if (!token) return;
    if (filledCount === 0) {
      setError("请至少填一科成绩");
      return;
    }

    // 构造数字分数
    const numScores: Record<string, number> = {};
    for (const s of SUBJECTS) {
      const v = parseInt(scores[s.name] || "", 10);
      if (!isNaN(v)) {
        if (v < 0 || v > s.max) {
          setError(`${s.name}分数应在 0-${s.max} 之间`);
          return;
        }
        numScores[s.name] = v;
      }
    }

    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/profile/exam", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ examName, examDate, district, scores: numScores }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.message);
      setSaved(true);
      setScores({});
    } catch (err: any) {
      setError(err.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  // 计算趋势
  const sortedRecords = [...records].sort((a, b) => a.examDate.localeCompare(b.examDate));
  const latestRecord = sortedRecords[sortedRecords.length - 1];
  const prevRecord = sortedRecords.length >= 2 ? sortedRecords[sortedRecords.length - 2] : null;
  const scoreDelta = latestRecord && prevRecord ? latestRecord.totalScore - prevRecord.totalScore : null;

  if (!token) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-12 text-center">
        <p className="text-gray-500 mb-4">登录后才能录入模考成绩</p>
        <Link href="/login" className="text-blue-600 underline">去登录</Link>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">&larr; 返回首页</Link>
      </div>

      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">模考成绩录入</h1>
        <p className="text-gray-500 text-sm">录入一模/二模/月考成绩，追踪进步趋势，校准学校匹配</p>
      </div>

      {/* 录入表单 */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">录入成绩</h2>

        {/* 考试类型 + 日期 + 区 */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs text-gray-400 mb-1 block">考试类型</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700"
              value={examName}
              onChange={(e) => setExamName(e.target.value)}
            >
              {EXAM_TYPES.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs text-gray-400 mb-1 block">考试日期</label>
            <input
              type="date"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
            />
          </div>
          <div className="flex-1 min-w-[120px]">
            <label className="text-xs text-gray-400 mb-1 block">所在区</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700"
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
            >
              {DISTRICTS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 6科分数 */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          {SUBJECTS.map((s) => (
            <div key={s.name}>
              <label className="text-xs text-gray-500 mb-1 block">
                {s.name}
                <span className="text-gray-300 ml-1">（满分{s.max}）</span>
              </label>
              <input
                type="number"
                min={0}
                max={s.max}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder:text-gray-300"
                placeholder={`0-${s.max}`}
                value={scores[s.name] || ""}
                onChange={(e) => setScores((prev) => ({ ...prev, [s.name]: e.target.value }))}
              />
            </div>
          ))}
        </div>

        {/* 总分预览 */}
        {filledCount > 0 && (
          <div className="bg-gray-50 rounded-lg px-4 py-3 mb-4 flex items-center justify-between">
            <span className="text-sm text-gray-500">合计（已填 {filledCount} 科）</span>
            <span className="text-xl font-bold text-gray-900">{totalScore}<span className="text-sm text-gray-400 font-normal"> / 510</span></span>
          </div>
        )}

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        {saved && <p className="text-sm text-green-600 mb-3">✓ 成绩已保存</p>}

        <button
          onClick={handleSubmit}
          disabled={saving || filledCount === 0}
          className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? "保存中..." : "保存成绩"}
        </button>
      </div>

      {/* 历史记录 */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">历史成绩</h2>

        {loadingRecords && <p className="text-sm text-gray-400">加载中...</p>}

        {!loadingRecords && records.length === 0 && (
          <p className="text-sm text-gray-400">暂无记录，录入第一次考试成绩吧</p>
        )}

        {records.length > 0 && (
          <>
            {/* 趋势摘要 */}
            {scoreDelta !== null && (
              <div className={`rounded-lg px-4 py-3 mb-4 ${scoreDelta >= 0 ? "bg-green-50" : "bg-red-50"}`}>
                <p className="text-sm">
                  <span className="font-medium text-gray-700">最近趋势：</span>
                  <span className={`font-bold ${scoreDelta >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {scoreDelta >= 0 ? "+" : ""}{scoreDelta} 分
                  </span>
                  <span className="text-gray-400 ml-2">
                    （{prevRecord!.examName} {prevRecord!.totalScore} → {latestRecord!.examName} {latestRecord!.totalScore}）
                  </span>
                </p>
              </div>
            )}

            {/* 记录列表 */}
            <div className="space-y-3">
              {sortedRecords.map((r, i) => {
                const prev = i > 0 ? sortedRecords[i - 1] : null;
                const delta = prev ? r.totalScore - prev.totalScore : null;
                return (
                  <div key={r.id} className="border border-gray-100 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <span className="font-medium text-gray-900 text-sm">{r.examName}</span>
                        <span className="text-xs text-gray-400 ml-2">{r.examDate}</span>
                        {r.district && <span className="text-xs text-gray-400 ml-2">{r.district}</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-bold text-gray-900">{r.totalScore}</span>
                        {delta !== null && (
                          <span className={`text-xs font-medium ${delta >= 0 ? "text-green-600" : "text-red-600"}`}>
                            {delta >= 0 ? "+" : ""}{delta}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-3 flex-wrap">
                      {SUBJECTS.map((s) => (
                        r.scores[s.name] !== undefined && (
                          <div key={s.name} className="text-xs text-gray-500">
                            {s.name} <span className="font-medium text-gray-700">{r.scores[s.name]}</span>
                            <span className="text-gray-300">/{s.max}</span>
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* 操作 */}
      <div className="flex justify-center gap-4 mb-8">
        <Link href="/score-check" className="px-5 py-2 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-100 text-sm">
          用最新成绩匹配学校
        </Link>
        <Link href="/diagnosis" className="px-5 py-2 border border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50 text-sm">
          全科诊断分析
        </Link>
      </div>
    </main>
  );
}
