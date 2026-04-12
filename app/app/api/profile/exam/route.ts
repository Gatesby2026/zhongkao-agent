import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";

const SUBJECT_MAX: Record<string, number> = {
  语文: 100, 数学: 100, 英语: 100, 物理: 80, 道法: 80, 体育: 50,
};

/**
 * POST /api/profile/exam — 保存模考成绩
 * Body: { examName, examDate, district, scores: Record<string, number> }
 */
export async function POST(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);
    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const body = await req.json();
    const { examName, examDate, district, scores } = body;

    if (!examName || !examDate || !scores || typeof scores !== "object") {
      return NextResponse.json({ success: false, message: "缺少必填字段" }, { status: 400 });
    }

    // 校验分数
    let total = 0;
    for (const [subj, max] of Object.entries(SUBJECT_MAX)) {
      const s = scores[subj];
      if (s === undefined || s === null) continue;
      if (typeof s !== "number" || s < 0 || s > max) {
        return NextResponse.json({ success: false, message: `${subj}分数无效（0-${max}）` }, { status: 400 });
      }
      total += s;
    }

    const db = getDb();
    db.prepare(
      `INSERT INTO exam_records (user_id, exam_name, exam_date, district, scores_json, total_score, created_at)
       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`
    ).run(user.id, examName, examDate, district || "", JSON.stringify(scores), total);

    // 更新 profile 的 current_score
    db.prepare(
      `UPDATE profiles SET current_score = ?, updated_at = datetime('now') WHERE user_id = ?`
    ).run(total, user.id);

    return NextResponse.json({ success: true, totalScore: total });
  } catch (error: any) {
    console.error("save exam error:", error);
    return NextResponse.json({ success: false, message: "保存失败" }, { status: 500 });
  }
}

/**
 * GET /api/profile/exam — 获取模考历史
 */
export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);
    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const db = getDb();
    const records = db.prepare(
      `SELECT id, exam_name, exam_date, district, scores_json, total_score, created_at
       FROM exam_records WHERE user_id = ? ORDER BY exam_date DESC, created_at DESC`
    ).all(user.id) as any[];

    const parsed = records.map((r) => ({
      id: r.id,
      examName: r.exam_name,
      examDate: r.exam_date,
      district: r.district,
      scores: JSON.parse(r.scores_json),
      totalScore: r.total_score,
      createdAt: r.created_at,
    }));

    return NextResponse.json({ success: true, records: parsed });
  } catch (error: any) {
    console.error("get exam records error:", error);
    return NextResponse.json({ success: false, message: "获取失败" }, { status: 500 });
  }
}
