import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { updateProfile } from "@/lib/profile";

const VALID_ROLES = ["student", "parent"];

/**
 * PUT /api/auth/role — 设置用户角色
 * Body: { role: "student" | "parent" }
 */
export async function PUT(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);
    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const { role } = await req.json();
    if (!VALID_ROLES.includes(role)) {
      return NextResponse.json({ success: false, message: "无效角色" }, { status: 400 });
    }

    const db = getDb();
    db.prepare(`UPDATE users SET role = ? WHERE id = ?`).run(role, user.id);

    // 同步到 profile preferences
    updateProfile(user.id, { preferences: { role, style: "", priority: "" } });

    return NextResponse.json({ success: true, role });
  } catch (error: any) {
    console.error("set role error:", error);
    return NextResponse.json({ success: false, message: "设置失败" }, { status: 500 });
  }
}
