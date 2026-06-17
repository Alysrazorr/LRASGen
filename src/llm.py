"""
LLM communication layer — GPT-5.4-mini / DeepSeek V4 Flash / Gemini 3.1 Flash Lite.

API keys via environment variables: OPENROUTER_API_KEY, DEEPSEEK_API_KEY.

Usage:
    result = chat([{"role": "user", "content": "..."}], provider="deepseek")
"""

import json
import os
import time
import uuid
from datetime import datetime

import logger

_SYSTEM_PROMPT = [{"role": "system", "content": "You are a well-skilled RESTful API backend developer."}]


# ---- GPT-5.4-mini (via OpenRouter) ----
def _send_gpt(messages, temperature=0.2):
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    return client.chat.completions.create(
        model="openai/gpt-5.4-mini",
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=16384,
        timeout=120,
        response_format={"type": "json_object"},
    )


# ---- DeepSeek V4 (official API) ----
def _send_deepseek(messages, temperature=0.2):
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url="https://api.deepseek.com",
    )
    return client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=16384,
        timeout=120,
        response_format={"type": "json_object"},
    )


# ---- Gemini 3.1 Flash Lite (via OpenRouter) ----
def _send_gemini(messages, temperature=0.2):
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    return client.chat.completions.create(
        model="google/gemini-3.1-flash-lite",
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=16384,
        timeout=120,
        response_format={"type": "json_object"},
    )


# ---- Token usage accumulator ----
_usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def get_usage():
    return dict(_usage_total)


def reset_usage():
    for k in _usage_total:
        _usage_total[k] = 0


_PROVIDERS = {
    "gpt":      _send_gpt,
    "deepseek": _send_deepseek,
    "gemini":   _send_gemini,
}


def chat(messages, provider="deepseek", temperature=0.2, max_retries=1):
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose: {list(_PROVIDERS.keys())}")

    fn = _PROVIDERS[provider]
    last_error = None

    for attempt in range(max_retries):
        uid = uuid.uuid4()
        marker = f"(retry {attempt+1}/{max_retries})" if attempt > 0 else ""
        logger.info(f"[{provider}] {uid} sending... {marker}")
        begin = datetime.now()

        try:
            raw = fn(messages, temperature)
        except Exception as e:
            last_error = e
            logger.warn(f"[{provider}] {uid} API error (attempt {attempt+1}): {str(e)[:200]}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

        if hasattr(raw, "usage") and raw.usage:
            _usage_total["prompt_tokens"] += raw.usage.prompt_tokens or 0
            _usage_total["completion_tokens"] += raw.usage.completion_tokens or 0
            _usage_total["total_tokens"] += raw.usage.total_tokens or 0

        elapsed = (datetime.now() - begin).total_seconds()

        if hasattr(raw, "choices") and raw.choices:
            text = raw.choices[0].message.content
        elif hasattr(raw, "text"):
            text = raw.text
        else:
            text = str(raw)

        if not text:
            last_error = ValueError(f"Empty response from {provider}")
            logger.warn(f"[{provider}] {uid} empty response (attempt {attempt+1})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise last_error

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            result = json.loads(text)
            logger.info(f"[{provider}] {uid} done ({elapsed:.1f}s){' [retry succeeded]' if attempt > 0 else ''}")
            return result
        except json.JSONDecodeError as e:
            last_error = ValueError(f"JSON parse error from {provider}: {str(e)[:200]} | text[:500]={text[:500]}")
            logger.warn(f"[{provider}] {uid} JSON parse error (attempt {attempt+1})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue

    raise last_error


_CROSS_VALIDATE_PROVIDERS = ("deepseek", "gpt", "gemini")


def cross_validate(messages, temperature=0.2, max_rounds=3):
    providers = list(_CROSS_VALIDATE_PROVIDERS)

    for round_idx in range(max_rounds):
        results = []
        for p in providers:
            try:
                r = chat(messages, provider=p, temperature=temperature)
                results.append({"provider": p, "result": r, "error": None})
            except Exception as e:
                results.append({"provider": p, "result": None, "error": str(e)})

        successes = [r for r in results if r["result"] is not None]
        if len(successes) < 2:
            if round_idx < max_rounds - 1:
                logger.warn(f"cross-validate: {len(successes)}/3 succeeded, retrying...")
                time.sleep(2 ** round_idx)
                continue
            if successes:
                return successes[0]["result"], {"provider": successes[0]["provider"], "consensus": "single_fallback"}
            raise RuntimeError(f"All 3 providers failed in cross-validation: {[r['error'] for r in results]}")

        if len(successes) == 3:
            j0 = _normalize_json(successes[0]["result"])
            j1 = _normalize_json(successes[1]["result"])
            j2 = _normalize_json(successes[2]["result"])
            if j0 == j1 == j2:
                logger.info(f"cross-validate: 3/3 consensus, using {successes[0]['provider']}")
                return successes[0]["result"], {"provider": successes[0]["provider"], "consensus": "3of3"}

        for i in range(len(successes)):
            for j in range(i + 1, len(successes)):
                if _normalize_json(successes[i]["result"]) == _normalize_json(successes[j]["result"]):
                    logger.info(f"cross-validate: 2/3 consensus ({successes[i]['provider']}+{successes[j]['provider']})")
                    return successes[i]["result"], {"provider": successes[i]["provider"], "consensus": "2of3"}

        if round_idx < max_rounds - 1:
            logger.warn(f"cross-validate: no consensus (round {round_idx+1}), retrying...")
            time.sleep(2 ** round_idx)
        else:
            for r in results:
                if r["provider"] == "deepseek" and r["result"]:
                    logger.warn(f"cross-validate: no consensus after {max_rounds} rounds, fallback to deepseek")
                    return r["result"], {"provider": "deepseek", "consensus": "fallback"}
            logger.warn("cross-validate: no consensus, using first success")
            return successes[0]["result"], {"provider": successes[0]["provider"], "consensus": "fallback"}

    raise RuntimeError("Cross-validation failed")


def _normalize_json(obj):
    if isinstance(obj, dict):
        return {k: _normalize_json(v) for k, v in sorted(obj.items())
                if k != "description" and k != "summary" and k != "evidence"}
    elif isinstance(obj, list):
        return [_normalize_json(item) for item in obj]
    return obj
