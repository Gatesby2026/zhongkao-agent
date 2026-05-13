"""LLM 调用 - DashScope OpenAI 兼容接口（qwen-max）。

设计为 thin 层：不引入 LangChain 等框架。
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr)
    sys.exit(1)


_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)


def _client():
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "缺少 DASHSCOPE_API_KEY 环境变量。\n"
            "可从 ~/.claude/projects/-Users-jiakui-projects-zhongkao-agent/memory/api-keys.md 找。"
        )
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def chat_json(
    *,
    system: str,
    user: str,
    model: str = "qwen-max",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    cache_key: str | None = None,
) -> dict:
    """调用 LLM，要求返回 JSON 对象。

    Args:
        cache_key: 若提供则按 key 缓存结果（生产场景关闭，开发反复跑节省 token）
    """
    if cache_key:
        cached = _CACHE_DIR / f"{cache_key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))

    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    obj = json.loads(content)

    if cache_key:
        cached = _CACHE_DIR / f"{cache_key}.json"
        cached.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return obj


def chat_text(
    *,
    system: str,
    user: str,
    model: str = "qwen-max",
    temperature: float = 0.4,
    max_tokens: int = 2048,
    cache_key: str | None = None,
) -> str:
    """调用 LLM，返回纯文本。"""
    if cache_key:
        cached = _CACHE_DIR / f"{cache_key}.txt"
        if cached.exists():
            return cached.read_text(encoding="utf-8")

    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content

    if cache_key:
        cached = _CACHE_DIR / f"{cache_key}.txt"
        cached.write_text(text, encoding="utf-8")
    return text
