import { NextRequest, NextResponse } from "next/server";
import { sendVerificationCode } from "@/lib/auth";

export async function POST(req: NextRequest) {
  try {
    const { phone } = await req.json();

    if (!phone) {
      return NextResponse.json({ success: false, message: "请输入手机号" }, { status: 400 });
    }

    const result = sendVerificationCode(phone);
    return NextResponse.json(result);
  } catch (error: any) {
    console.error("send-code error:", error);
    return NextResponse.json(
      { success: false, message: "发送失败，请稍后重试" },
      { status: 500 }
    );
  }
}
