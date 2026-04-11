/**
 * LLM 调用模块
 * 封装 MiniMax API 调用（OpenAI 兼容格式）
 * 支持普通调用和流式调用
 */

interface Message {
  role: "system" | "user" | "assistant";
  content: string;
}

interface LLMResponse {
  content: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

function getConfig() {
  const apiKey = process.env.MINIMAX_API_KEY;
  const model = process.env.MINIMAX_MODEL || "MiniMax-M2.7";
  const baseUrl = process.env.MINIMAX_BASE_URL || "https://api.minimax.chat/v1";
  if (!apiKey) throw new Error("MINIMAX_API_KEY not configured");
  return { apiKey, model, baseUrl };
}

/** 普通（非流式）调用 */
export async function callLLM(messages: Message[]): Promise<LLMResponse> {
  const { apiKey, model, baseUrl } = getConfig();

  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages,
      temperature: 0.7,
      max_tokens: 4096,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`LLM API error: ${response.status} ${error}`);
  }

  const data = await response.json();
  let content = data.choices?.[0]?.message?.content || "";
  content = content.replace(/<think>[\s\S]*?<\/think>\s*/g, "").trim();

  return { content, usage: data.usage };
}

/** 流式调用 — 返回 ReadableStream */
export function callLLMStream(messages: Message[]): ReadableStream {
  const { apiKey, model, baseUrl } = getConfig();

  return new ReadableStream({
    async start(controller) {
      try {
        const response = await fetch(`${baseUrl}/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model,
            messages,
            temperature: 0.7,
            max_tokens: 4096,
            stream: true,
          }),
        });

        if (!response.ok) {
          const error = await response.text();
          controller.enqueue(
            new TextEncoder().encode(`data: ${JSON.stringify({ error: `LLM API error: ${response.status}` })}\n\n`)
          );
          controller.close();
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";
        let inThinkBlock = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);
            if (data === "[DONE]") continue;

            try {
              const parsed = JSON.parse(data);
              let delta = parsed.choices?.[0]?.delta?.content || "";
              if (!delta) continue;

              // 过滤 <think>...</think> 块
              if (delta.includes("<think>")) {
                inThinkBlock = true;
                delta = delta.replace(/<think>[\s\S]*/g, "");
              }
              if (inThinkBlock) {
                if (delta.includes("</think>")) {
                  inThinkBlock = false;
                  delta = delta.replace(/[\s\S]*<\/think>\s*/g, "");
                } else {
                  continue; // 跳过思维链内容
                }
              }

              if (delta) {
                controller.enqueue(
                  new TextEncoder().encode(`data: ${JSON.stringify({ content: delta })}\n\n`)
                );
              }
            } catch {
              // 忽略解析错误
            }
          }
        }

        controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
        controller.close();
      } catch (err: any) {
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify({ error: err.message })}\n\n`)
        );
        controller.close();
      }
    },
  });
}
