import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { getProfile } from "@/lib/profile";

/**
 * GET /api/report/weekly — 生成本周学习周报
 * Query: ?weeks=1 (默认本周，可看往期)
 */
export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);
    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const weeksAgo = parseInt(req.nextUrl.searchParams.get("weeks") || "0", 10);
    const db = getDb();

    // 计算本周范围（周一到周日）
    const now = new Date();
    const dayOfWeek = now.getDay() || 7; // 周日=7
    const mondayOffset = dayOfWeek - 1 + weeksAgo * 7;
    const weekStart = new Date(now);
    weekStart.setDate(now.getDate() - mondayOffset);
    weekStart.setHours(0, 0, 0, 0);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 7);

    const startStr = weekStart.toISOString().slice(0, 10);
    const endStr = weekEnd.toISOString().slice(0, 10);

    // 1. 刷题记录
    const drills = db.prepare(
      `SELECT module, correct_rate, total_questions, time_spent, created_at
       FROM drill_records WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) < ?
       ORDER BY created_at`
    ).all(user.id, startStr, endStr) as any[];

    // 2. 测评记录
    const assessments = db.prepare(
      `SELECT score, module_results_json, created_at
       FROM assessment_records WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) < ?
       ORDER BY created_at`
    ).all(user.id, startStr, endStr) as any[];

    // 3. 模考记录
    const exams = db.prepare(
      `SELECT exam_name, exam_date, scores_json, total_score, created_at
       FROM exam_records WHERE user_id = ? AND date(exam_date) >= ? AND date(exam_date) < ?
       ORDER BY exam_date`
    ).all(user.id, startStr, endStr) as any[];

    // 4. 上周数据（用于对比）
    const prevStart = new Date(weekStart);
    prevStart.setDate(weekStart.getDate() - 7);
    const prevStartStr = prevStart.toISOString().slice(0, 10);

    const prevDrills = db.prepare(
      `SELECT COUNT(*) as cnt, SUM(total_questions) as questions, AVG(correct_rate) as avgRate
       FROM drill_records WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) < ?`
    ).get(user.id, prevStartStr, startStr) as any;

    // 汇总本周
    const totalDrillSessions = drills.length;
    const totalQuestions = drills.reduce((s, d) => s + (d.total_questions || 0), 0);
    const avgCorrectRate = drills.length > 0
      ? drills.reduce((s, d) => s + d.correct_rate, 0) / drills.length
      : 0;
    const totalTimeMin = Math.round(drills.reduce((s, d) => s + (d.time_spent || 0), 0) / 60);

    // 按模块聚合
    const moduleStats: Record<string, { sessions: number; questions: number; avgRate: number; rates: number[] }> = {};
    for (const d of drills) {
      if (!moduleStats[d.module]) {
        moduleStats[d.module] = { sessions: 0, questions: 0, avgRate: 0, rates: [] };
      }
      moduleStats[d.module].sessions++;
      moduleStats[d.module].questions += d.total_questions || 0;
      moduleStats[d.module].rates.push(d.correct_rate);
    }
    for (const m of Object.values(moduleStats)) {
      m.avgRate = m.rates.reduce((a, b) => a + b, 0) / m.rates.length;
    }

    // 画像
    const profile = getProfile(user.id);

    // 解析模考
    const parsedExams = exams.map((e) => ({
      examName: e.exam_name,
      examDate: e.exam_date,
      totalScore: e.total_score,
      scores: JSON.parse(e.scores_json || "{}"),
    }));

    // 解析测评
    const parsedAssessments = assessments.map((a) => ({
      score: a.score,
      moduleResults: JSON.parse(a.module_results_json || "{}"),
      createdAt: a.created_at,
    }));

    // 对比上周
    const prevQuestions = prevDrills?.questions || 0;
    const prevAvgRate = prevDrills?.avgRate || 0;
    const questionsDelta = totalQuestions - prevQuestions;
    const rateDelta = drills.length > 0 && prevDrills?.cnt > 0
      ? avgCorrectRate - prevAvgRate
      : null;

    const report = {
      weekRange: { start: startStr, end: endStr },
      summary: {
        drillSessions: totalDrillSessions,
        totalQuestions,
        avgCorrectRate: Math.round(avgCorrectRate * 100),
        totalTimeMin,
        assessmentCount: assessments.length,
        examCount: exams.length,
      },
      comparison: {
        questionsDelta,
        rateDelta: rateDelta !== null ? Math.round(rateDelta * 100) : null,
        prevQuestions,
      },
      moduleStats: Object.entries(moduleStats).map(([id, s]) => ({
        moduleId: id,
        sessions: s.sessions,
        questions: s.questions,
        avgRate: Math.round(s.avgRate * 100),
      })),
      exams: parsedExams,
      assessments: parsedAssessments,
      profile: profile ? {
        completeness: profile.completeness,
        currentScore: profile.currentScore,
        targetSchool: profile.targetSchool,
      } : null,
      hasData: totalDrillSessions > 0 || assessments.length > 0 || exams.length > 0,
    };

    return NextResponse.json({ success: true, report });
  } catch (error: any) {
    console.error("weekly report error:", error);
    return NextResponse.json({ success: false, message: "生成周报失败" }, { status: 500 });
  }
}
