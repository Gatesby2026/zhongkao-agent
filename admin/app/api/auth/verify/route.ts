import { NextRequest, NextResponse } from "next/server";
import { verifyCodeAndLogin } from "@/lib/auth";

export async function POST(req: NextRequest) {
  try {
    const { phone, code } = await req.json();

    if (!phone || !code) {
      return NextResponse.json({ success: false, message: "请输入手机号和验证码" }, { status: 400 });
    }

    const result = verifyCodeAndLogin(phone, code);

    if (!result.success) {
      return NextResponse.json(result, { status: 401 });
    }

    return NextResponse.json(result);
  } catch (error: any) {
    console.error("verify error:", error);
    return NextResponse.json(
      { success: false, message: "验证失败，请稍后重试" },
      { status: 500 }
    );
  }
}
