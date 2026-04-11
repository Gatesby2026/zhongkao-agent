/**
 * LLM 调用模块
 * 封装 MiniMax API 调用（OpenAI 兼容格式）
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

export async function callLLM(messages: Message[]): Promise<LLMResponse> {
  const apiKey = process.env.MINIMAX_API_KEY;
  const model = process.env.MINIMAX_MODEL || "MiniMax-M2.7";
  const baseUrl = process.env.MINIMAX_BASE_URL || "https://api.minimax.chat/v1";

  if (!apiKey) {
    throw new Error("MINIMAX_API_KEY not configured");
  }

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

  // MiniMax M2.7 会返回 <think>...</think> 思维链，需要去除
  content = content.replace(/<think>[\s\S]*?<\/think>\s*/g, "").trim();

  return {
    content,
    usage: data.usage,
  };
}
