import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getProfile, updateProfile } from "@/lib/profile";

/**
 * GET /api/profile — 获取当前用户画像
 */
export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);

    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const profile = getProfile(user.id);
    return NextResponse.json({ success: true, profile });
  } catch (error: any) {
    console.error("get profile error:", error);
    return NextResponse.json({ success: false, message: "获取画像失败" }, { status: 500 });
  }
}

/**
 * PUT /api/profile — 更新用户画像（部分更新）
 */
export async function PUT(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);

    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    const updates = await req.json();
    const profile = updateProfile(user.id, updates);

    if (!profile) {
      return NextResponse.json({ success: false, message: "画像不存在" }, { status: 404 });
    }

    return NextResponse.json({ success: true, profile });
  } catch (error: any) {
    console.error("update profile error:", error);
    return NextResponse.json({ success: false, message: "更新画像失败" }, { status: 500 });
  }
}
