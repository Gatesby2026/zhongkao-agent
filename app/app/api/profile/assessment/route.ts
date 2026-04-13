import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { updateModulesFromAssessment } from "@/lib/profile";
import { getDb } from "@/lib/db";

/**
 * POST /api/profile/assessment — 保存测评结果到画像
 * Body: { modules: Record<moduleId, { level, weaknesses }>, totalCorrect, estimatedScore }
 */
export async function POST(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);

    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const body = await req.json();
    const { modules, totalCorrect, estimatedScore, answers } = body;

    if (!modules || typeof modules !== "object") {
      return NextResponse.json({ success: false, message: "缺少 modules 数据" }, { status: 400 });
    }

    // 1. 更新画像中的模块水平
    updateModulesFromAssessment(user.id, modules);

    // 2. 记录到 assessment_records 表
    const db = getDb();
    db.prepare(
      `INSERT INTO assessment_records (user_id, answers_json, score, module_results_json, created_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    ).run(
      user.id,
      JSON.stringify(answers || []),
      estimatedScore || 0,
      JSON.stringify(modules)
    );

    return NextResponse.json({ success: true, message: "测评结果已保存到画像" });
  } catch (error: any) {
    console.error("save assessment error:", error);
    return NextResponse.json({ success: false, message: "保存失败" }, { status: 500 });
  }
}
