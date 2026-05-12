/**
 * POST /api/generate-plan
 * 接收考生输入 → 诊断 → 调 LLM 流式生成学习规划
 */
import { NextRequest, NextResponse } from "next/server";
import { diagnose, StudentInput } from "@/lib/diagnosis";
import { loadKnowledgeBase } from "@/lib/knowledge-base";
import { buildPrompt } from "@/lib/prompt-builder";
import { callLLMStream } from "@/lib/llm";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const input: StudentInput = body;
    const targetSchool: string | undefined = body.targetSchool;

    // 1. 运行诊断算法
    const diagnosis = diagnose(input);

    // 2. 加载知识库
    const kb = loadKnowledgeBase();

    // 3. 构建 prompt
    const { system, user } = buildPrompt(diagnosis, kb, input.district, targetSchool);

    // 4. 调用 LLM（流式）
    const stream = callLLMStream([
      { role: "system", content: system },
      { role: "user", content: user },
    ]);

    // 先发送诊断结果作为第一个 SSE 事件，然后流式发送 LLM 输出
    const encoder = new TextEncoder();
    const diagnosisEvent = encoder.encode(
      `data: ${JSON.stringify({ type: "diagnosis", diagnosis })}\n\n`
    );

    const combinedStream = new ReadableStream({
      async start(controller) {
        // 先发诊断结果
        controller.enqueue(diagnosisEvent);

        // 再转发 LLM 流
        const reader = stream.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
        controller.close();
      },
    });

    return new Response(combinedStream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error: any) {
    console.error("Generate plan error:", error);
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
