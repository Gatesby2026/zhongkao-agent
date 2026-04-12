import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const user = getCurrentUser(authHeader);

    if (!user) {
      return NextResponse.json({ success: false, message: "未登录" }, { status: 401 });
    }

    return NextResponse.json({ success: true, user });
  } catch (error: any) {
    console.error("me error:", error);
    return NextResponse.json({ success: false, message: "获取用户信息失败" }, { status: 500 });
  }
}
