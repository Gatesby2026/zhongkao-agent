"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";
import Link from "next/link";

interface ProfileData {
  district: string;
  school: string;
  grade: string;
  currentScore: number;
  targetSchool: string;
  targetScore: number;
  hoursPerDay: number;
  modules: Record<string, { level: string; source: string; confidence: number; updatedAt: string }>;
  completeness: number;
}

const MODULE_NAMES: Record<string, string> = {
  numbersAndExpressions: "计算/数与式",
  equationsAndInequalities: "方程与不等式",
  functions: "函数",
  triangles: "三角形",
  circles: "圆",
  statisticsAndProbability: "统计与概率",
  geometryComprehensive: "压轴题",
};

const SOURCE_LABELS: Record<string, string> = {
  self: "自评",
  assessment: "测评",
  drill: "刷题",
  llm: "AI 诊断",
};

const LEVEL_COLORS: Record<string, string> = {
  "擅长": "bg-emerald-100 text-emerald-700",
  "不错": "bg-green-100 text-green-700",
  "还行": "bg-yellow-100 text-yellow-700",
  "薄弱": "bg-orange-100 text-orange-700",
  "很差": "bg-red-100 text-red-700",
  "不确定": "bg-gray-100 text-gray-500",
};

export default function ProfilePage() {
  const { user, token } = useAuth();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({ district: "", school: "", currentScore: 0, targetSchool: "", hoursPerDay: 1.5 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    fetchProfile();
  }, [token]);

  const fetchProfile = async () => {
    try {
      const res = await fetch("/api/profile", {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.success) {
        setProfile(data.profile);
        setEditData({
          district: data.profile.district || "",
          school: data.profile.school || "",
          currentScore: data.profile.currentScore || 0,
          targetSchool: data.profile.targetSchool || "",
          hoursPerDay: data.profile.hoursPerDay || 1.5,
        });
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(editData),
      });
      const data = await res.json();
      if (data.success) {
        setProfile(data.profile);
        setEditing(false);
      }
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  // 未登录
  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-4xl mb-4">🔒</div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">请先登录</h2>
        <p className="text-gray-500 mb-6">登录后可查看和管理你的学习画像</p>
        <Link href="/login" className="inline-block px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700">
          去登录
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="animate-pulse text-gray-400">加载中...</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      {/* 画像完整度 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-gray-900">我的学习画像</h2>
          <span className="text-2xl font-bold text-blue-600">{profile?.completeness || 0}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
          <div
            className="bg-gradient-to-r from-blue-500 to-blue-600 h-3 rounded-full transition-all duration-500"
            style={{ width: `${profile?.completeness || 0}%` }}
          />
        </div>
        <p className="text-xs text-gray-500">
          {(profile?.completeness || 0) < 30
            ? "画像刚开始建立，建议做一次快速测评来完善"
            : (profile?.completeness || 0) < 60
            ? "画像基本建立，多做刷题可以让评估更精准"
            : (profile?.completeness || 0) < 80
            ? "画像较为完善，持续使用会越来越准"
            : "画像已经很完善了！"}
        </p>
      </div>

      {/* 基础信息 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-gray-900">基础信息</h3>
          <button
            onClick={() => setEditing(!editing)}
            className="text-sm text-blue-600 hover:underline"
          >
            {editing ? "取消" : "编辑"}
          </button>
        </div>

        {editing ? (
          <div className="space-y-3">
            <div>
              <label className="text-sm text-gray-600">区域</label>
              <select
                value={editData.district}
                onChange={(e) => setEditData({ ...editData, district: e.target.value })}
                className="mt-1 w-full px-3 py-2 border rounded-lg text-sm"
              >
                <option value="">未设置</option>
                {["朝阳区", "海淀区", "西城区", "东城区", "丰台区", "石景山区", "通州区", "顺义区", "房山区", "大兴区", "昌平区", "密云区", "门头沟区"].map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-600">学校</label>
              <input
                type="text"
                value={editData.school}
                onChange={(e) => setEditData({ ...editData, school: e.target.value })}
                placeholder="如：陈经纶中学分校"
                className="mt-1 w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-gray-600">当前总分</label>
                <input
                  type="number"
                  value={editData.currentScore || ""}
                  onChange={(e) => setEditData({ ...editData, currentScore: parseInt(e.target.value) || 0 })}
                  className="mt-1 w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="text-sm text-gray-600">每日学习时间(h)</label>
                <input
                  type="number"
                  step="0.5"
                  value={editData.hoursPerDay}
                  onChange={(e) => setEditData({ ...editData, hoursPerDay: parseFloat(e.target.value) || 1.5 })}
                  className="mt-1 w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>
            </div>
            <div>
              <label className="text-sm text-gray-600">目标学校</label>
              <input
                type="text"
                value={editData.targetSchool}
                onChange={(e) => setEditData({ ...editData, targetSchool: e.target.value })}
                placeholder="如：八十中"
                className="mt-1 w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300"
            >
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <InfoItem label="区域" value={profile?.district || "未设置"} />
            <InfoItem label="学校" value={profile?.school || "未设置"} />
            <InfoItem label="当前总分" value={profile?.currentScore ? `${profile.currentScore} 分` : "未设置"} />
            <InfoItem label="目标学校" value={profile?.targetSchool || "未设置"} />
            <InfoItem label="每日学习" value={`${profile?.hoursPerDay || 1.5} 小时`} />
            <InfoItem label="年级" value={profile?.grade || "初三"} />
          </div>
        )}
      </div>

      {/* 模块能力 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-gray-900">各模块水平</h3>
          <Link href="/assessment" className="text-sm text-blue-600 hover:underline">
            去测评
          </Link>
        </div>

        {profile?.modules && Object.keys(profile.modules).length > 0 ? (
          <div className="space-y-3">
            {Object.entries(MODULE_NAMES).map(([key, name]) => {
              const m = profile.modules[key];
              if (!m) return (
                <div key={key} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                  <span className="text-sm text-gray-700">{name}</span>
                  <span className="text-xs text-gray-400">未评估</span>
                </div>
              );
              return (
                <div key={key} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                  <span className="text-sm text-gray-700">{name}</span>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${LEVEL_COLORS[m.level] || LEVEL_COLORS["不确定"]}`}>
                      {m.level}
                    </span>
                    <span className="text-xs text-gray-400">
                      {SOURCE_LABELS[m.source] || m.source}
                    </span>
                    {/* 置信度指示器 */}
                    <div className="flex gap-0.5" title={`置信度 ${Math.round(m.confidence * 100)}%`}>
                      {[0.25, 0.5, 0.75, 1.0].map((t, i) => (
                        <div
                          key={i}
                          className={`w-1.5 h-3 rounded-sm ${m.confidence >= t ? "bg-blue-500" : "bg-gray-200"}`}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-6">
            <p className="text-gray-400 text-sm mb-3">还没有模块评估数据</p>
            <Link
              href="/assessment"
              className="inline-block px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700"
            >
              5 分钟快速测评
            </Link>
          </div>
        )}
      </div>

      {/* 快捷操作 */}
      <div className="grid grid-cols-2 gap-3">
        <Link
          href="/assessment"
          className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:border-purple-300 transition-colors"
        >
          <div className="text-2xl mb-1">📝</div>
          <p className="text-sm font-medium text-gray-700">做测评</p>
        </Link>
        <Link
          href="/drill"
          className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:border-blue-300 transition-colors"
        >
          <div className="text-2xl mb-1">💪</div>
          <p className="text-sm font-medium text-gray-700">刷题</p>
        </Link>
        <Link
          href="/plan"
          className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:border-green-300 transition-colors"
        >
          <div className="text-2xl mb-1">📋</div>
          <p className="text-sm font-medium text-gray-700">生成计划</p>
        </Link>
        <Link
          href="/score-check"
          className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:border-orange-300 transition-colors"
        >
          <div className="text-2xl mb-1">🏫</div>
          <p className="text-sm font-medium text-gray-700">查学校</p>
        </Link>
      </div>
    </div>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-gray-500">{label}</span>
      <p className="font-medium text-gray-900 mt-0.5">{value}</p>
    </div>
  );
}
