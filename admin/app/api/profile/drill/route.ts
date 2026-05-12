import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { updateModuleFromDrill, type ModuleId } from "@/lib/profile";
import { getDb } from "@/lib/db";

const VALID_MODULES: ModuleId[] = [
  "numbersAndExpressions",
  "equationsAndInequalities",
  "functions",
  "triangles",
  "circles",
  "statisticsAndProbability",
  "geometryComprehensive",
];

/**
 * POST /api/profile/drill — 保存刷题结果到画像
 * Body: { moduleId, correctRate, questionsAttempted, timeSpent }
 */
export async function POST(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);

    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const body = await req.json();
    const { moduleId, correctRate, questionsAttempted, timeSpent } = body;

    if (!moduleId || !VALID_MODULES.includes(moduleId)) {
      return NextResponse.json({ success: false, message: "无效的 moduleId" }, { status: 400 });
    }

    if (typeof correctRate !== "number" || correctRate < 0 || correctRate > 1) {
      return NextResponse.json({ success: false, message: "correctRate 应为 0-1" }, { status: 400 });
    }

    // 1. 更新画像中的模块水平（EMA 融合）
    updateModuleFromDrill(user.id, moduleId, correctRate);

    // 2. 记录到 drill_records 表
    const db = getDb();
    db.prepare(
      `INSERT INTO drill_records (user_id, module, correct_rate, total_questions, time_spent, created_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    ).run(
      user.id,
      moduleId,
      correctRate,
      questionsAttempted || 0,
      timeSpent || 0
    );

    return NextResponse.json({ success: true, message: "刷题结果已更新画像" });
  } catch (error: any) {
    console.error("save drill error:", error);
    return NextResponse.json({ success: false, message: "保存失败" }, { status: 500 });
  }
}
