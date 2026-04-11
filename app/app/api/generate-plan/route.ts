/**
 * POST /api/generate-plan
 * 接收考生输入 → 诊断 → 调 LLM 生成学习规划
 */
import { NextRequest, NextResponse } from "next/server";
import { diagnose, StudentInput } from "@/lib/diagnosis";
import { loadKnowledgeBase } from "@/lib/knowledge-base";
import { buildPrompt } from "@/lib/prompt-builder";
import { callLLM } from "@/lib/llm";

export async function POST(req: NextRequest) {
  try {
    const input: StudentInput = await req.json();

    // 1. 运行诊断算法
    const diagnosis = diagnose(input);

    // 2. 加载知识库
    const kb = loadKnowledgeBase();

    // 3. 构建 prompt
    const { system, user } = buildPrompt(diagnosis, kb, input.district);

    // 4. 调用 LLM
    const llmResponse = await callLLM([
      { role: "system", content: system },
      { role: "user", content: user },
    ]);

    return NextResponse.json({
      success: true,
      diagnosis,
      plan: llmResponse.content,
      usage: llmResponse.usage,
    });
  } catch (error: any) {
    console.error("Generate plan error:", error);
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
