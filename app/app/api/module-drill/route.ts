/**
 * POST /api/module-drill
 * 模块突破模式：针对单个薄弱模块生成专项突破计划
 */
import { NextRequest, NextResponse } from "next/server";
import { loadKnowledgeBase } from "@/lib/knowledge-base";
import { buildModuleDrillPrompt, ModuleDrillInput } from "@/lib/prompt-builder";
import { callLLMStream } from "@/lib/llm";

const VALID_MODULES = [
  "numbersAndExpressions",
  "equationsAndInequalities",
  "functions",
  "triangles",
  "circles",
  "statisticsAndProbability",
  "geometryComprehensive",
];

const VALID_LEVELS = ["L0", "L1", "L2", "L3"];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // 参数校验
    if (!body.moduleId || !VALID_MODULES.includes(body.moduleId)) {
      return NextResponse.json(
        { success: false, error: `无效的模块ID，可选值：${VALID_MODULES.join(", ")}` },
        { status: 400 }
      );
    }
    if (!body.level || !VALID_LEVELS.includes(body.level)) {
      return NextResponse.json(
        { success: false, error: `无效的水平等级，可选值：${VALID_LEVELS.join(", ")}` },
        { status: 400 }
      );
    }

    const input: ModuleDrillInput = {
      moduleId: body.moduleId,
      level: body.level,
      district: body.district || "海淀区",
      hoursPerWeek: body.hoursPerWeek || 6,
      weeksUntilExam: body.weeksUntilExam || 10,
      problem: body.problem,
    };

    // 加载知识库
    const kb = loadKnowledgeBase();

    // 构建 prompt
    const { system, user } = buildModuleDrillPrompt(input, kb);

    // 调用 LLM（流式）
    const stream = callLLMStream([
      { role: "system", content: system },
      { role: "user", content: user },
    ]);

    // 先发送模块信息，再流式发送 LLM 输出
    const encoder = new TextEncoder();
    const metaEvent = encoder.encode(
      `data: ${JSON.stringify({ type: "meta", moduleId: input.moduleId, level: input.level })}\n\n`
    );

    const combinedStream = new ReadableStream({
      async start(controller) {
        controller.enqueue(metaEvent);
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
    console.error("Module drill error:", error);
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
