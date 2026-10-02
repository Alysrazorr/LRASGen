
import json
import os
import threading
import time
import uuid
from datetime import datetime

import config
import logger
from config import (
    PROVIDERS,
    TEMPERATURE,
    MAX_TOKENS,
    REQUEST_TIMEOUT_S,
    CHAT_MAX_RETRIES,
    CROSS_VALIDATE_MAX_ROUNDS,
    CROSS_VALIDATE_MIN_VOTES,
    RETRY_BACKOFF_BASE_S,
    ERROR_MESSAGE_MAX_CHARS,
    RESPONSE_SNIPPET_MAX_CHARS,
)

_SYSTEM_PROMPT = [{"role": "system", "content": "You are a well-skilled RESTful API backend developer."}]

# The models to call, in the order cross-validation polls them. A model is still
# called a provider in the output, where it labels the usage report, and
# config.PRIMARY_MODEL is the first of them, so that vocabulary stays.
_MODEL_NAMES = [spec["name"] for spec in PROVIDERS]


def _spec(name):
    """The configuration entry for a model name."""
    for spec in PROVIDERS:
        if spec["name"] == name:
            return spec
    raise ValueError(f"Unknown provider '{name}'. Configured: {_MODEL_NAMES}")


def _client(spec):
    """An OpenAI-compatible client for a provider entry.

    The endpoint and the credential both come from the entry, so an endpoint
    that serves several models is described once in config rather than in every
    sender that reaches it.
    """
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ.get(spec["api_key_env"], spec["api_key_default"]),
        base_url=spec["base_url"],
    )


# One sender per model, found by name in _sender(). Two models that share a
# provider and a request shape still get a sender each, because the model names
# the function: either of them can change its request without moving the other,
# even though both read alike today.
def _send_deepseek(spec, messages, temperature=TEMPERATURE):
    return _client(spec).chat.completions.create(
        model=spec["model"],
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_S,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )


def _send_gpt(spec, messages, temperature=TEMPERATURE):
    return _client(spec).chat.completions.create(
        model=spec["model"],
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_S,
        response_format={"type": "json_object"},
    )


def _send_gemini(spec, messages, temperature=TEMPERATURE):
    return _client(spec).chat.completions.create(
        model=spec["model"],
        messages=_SYSTEM_PROMPT + messages,
        stream=False,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_S,
        response_format={"type": "json_object"},
    )


def _zero_usage():
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "calls": 0, "elapsed_s": 0.0}


_usage_by_model = {name: _zero_usage() for name in _MODEL_NAMES}

_usage_lock = threading.Lock()


def _record_usage(name, prompt=0, completion=0, total=0, calls=0, elapsed=0.0):
    with _usage_lock:
        u = _usage_by_model[name]
        u["prompt_tokens"] += prompt
        u["completion_tokens"] += completion
        u["total_tokens"] += total
        u["calls"] += calls
        u["elapsed_s"] += elapsed


def _cost_usd(name, u):
    price = next((s["price"] for s in PROVIDERS if s["name"] == name), None)
    if not price:
        return {"prompt_cost_usd": 0.0, "completion_cost_usd": 0.0, "total_cost_usd": 0.0}
    prompt_cost = u["prompt_tokens"] / 1_000_000 * price[0]
    completion_cost = u["completion_tokens"] / 1_000_000 * price[1]
    return {
        "prompt_cost_usd": round(prompt_cost, 6),
        "completion_cost_usd": round(completion_cost, 6),
        "total_cost_usd": round(prompt_cost + completion_cost, 6),
    }


def get_usage():
    total = _zero_usage()
    for u in _usage_by_model.values():
        for k in total:
            total[k] += u[k]

    # One record per configured model, each naming the provider it is called on.
    # A model that was not called stays in at zero, so a step file records which
    # models the run could have used and not only the ones that answered.
    by_model = [
        {
            "name": spec["name"],
            "model": spec["model"],
            "provider": spec["provider"],
            **_usage_by_model[spec["name"]],
            **_cost_usd(spec["name"], _usage_by_model[spec["name"]]),
        }
        for spec in PROVIDERS
    ]

    prompt_cost = round(sum(m["prompt_cost_usd"] for m in by_model), 6)
    completion_cost = round(sum(m["completion_cost_usd"] for m in by_model), 6)

    return {
        "prompt_tokens": total["prompt_tokens"],
        "completion_tokens": total["completion_tokens"],
        "total_tokens": total["total_tokens"],
        "calls": total["calls"],
        "elapsed_s": round(total["elapsed_s"], 3),
        "prompt_cost_usd": prompt_cost,
        "completion_cost_usd": completion_cost,
        "total_cost_usd": round(prompt_cost + completion_cost, 6),
        "by_model": by_model,
    }


def reset_usage():
    with _usage_lock:
        for u in _usage_by_model.values():
            for k in u:
                u[k] = 0


def _sender(spec):
    """The _send_* function that serves a model.

    The model name names the function, so a configured model and its sender
    cannot drift apart: the model named "gpt" is served by _send_gpt. Adding a
    model means adding an entry to config.MODEL_CONFIG and a function of that
    name here, with no mapping in between to update.
    """
    name = spec["name"]
    fn_name = f"_send_{name.replace('-', '_')}"
    fn = globals().get(fn_name)
    if not callable(fn):
        raise ValueError(
            f"No sender for provider '{name}': llm.py has no {fn_name} "
            f"function. Configured providers: {_MODEL_NAMES}")
    return fn


def _check_senders():
    """Fail at import when a configured model has no sender.

    A missing sender is a typo in config.MODEL_CONFIG. Resolving every model
    here names it before the run starts, instead of part way through the first
    API that happens to use it.
    """
    for spec in PROVIDERS:
        _sender(spec)


_check_senders()


def _balanced_end(text, start):
    """The index just past the value opening at start, or None if it never closes."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _loose_json(text):
    """Parse a reply, including one that carries more than the object asked for.

    A reply sometimes opens with the schema it was shown and then continues with
    the answer, so the text holds two values in a row and parses as neither. The
    second is the answer: it is read as the body of the object and returned.
    Trailing prose after a single well formed value is dropped the same way.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        raise ValueError("no JSON value in the reply")

    end = _balanced_end(text, start)
    if end is not None:
        head, rest = text[start:end], text[end:].strip()
        if rest.startswith(","):
            rest = rest[1:].lstrip()
        if rest and not rest.startswith("}"):
            # The value that follows is the answer; the one before it is the
            # format. Wrapping the remainder rebuilds the object it meant.
            for candidate in ("{" + rest + "}", "{" + rest,
                              "{" + rest[:rest.rfind("}") + 1]):
                try:
                    return json.loads(candidate)
                except (json.JSONDecodeError, ValueError):
                    continue
        try:
            return json.loads(head)
        except json.JSONDecodeError:
            pass

    # Nothing balanced at the front: the last value in the text is the one the
    # model finished with, so it is the one to try.
    last = text.rfind("{")
    if last > start:
        try:
            return json.loads(text[last:])
        except json.JSONDecodeError:
            pass
    raise ValueError("the reply does not hold a JSON object")


def chat(messages, provider="deepseek", temperature=TEMPERATURE, max_retries=CHAT_MAX_RETRIES):
    spec = _spec(provider)
    fn = _sender(spec)
    last_error = None

    for attempt in range(max_retries):
        uid = uuid.uuid4()
        marker = f"(retry {attempt+1}/{max_retries})" if attempt > 0 else ""
        logger.info(f"[{provider}] {uid} sending... {marker}")
        begin = datetime.now()

        try:
            raw = fn(spec, messages, temperature)
        except Exception as e:
            _record_usage(provider, elapsed=(datetime.now() - begin).total_seconds())
            last_error = e
            logger.warn(f"[{provider}] {uid} API error (attempt {attempt+1}): "
                        f"{str(e)[:ERROR_MESSAGE_MAX_CHARS]}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_BACKOFF_BASE_S ** attempt)
                continue
            raise

        if hasattr(raw, "usage") and raw.usage:
            _record_usage(provider,
                          prompt=raw.usage.prompt_tokens or 0,
                          completion=raw.usage.completion_tokens or 0,
                          total=raw.usage.total_tokens or 0,
                          calls=1)

        elapsed = (datetime.now() - begin).total_seconds()
        _record_usage(provider, elapsed=elapsed)

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
                time.sleep(RETRY_BACKOFF_BASE_S ** attempt)
                continue
            raise last_error

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            result = _loose_json(text)
            logger.info(f"[{provider}] {uid} done ({elapsed:.1f}s){' [retry succeeded]' if attempt > 0 else ''}")
            return result
        except (json.JSONDecodeError, ValueError) as e:
            last_error = ValueError(
                f"JSON parse error from {provider}: {str(e)[:ERROR_MESSAGE_MAX_CHARS]} | "
                f"text[:{RESPONSE_SNIPPET_MAX_CHARS}]={text[:RESPONSE_SNIPPET_MAX_CHARS]}")
            logger.warn(f"[{provider}] {uid} JSON parse error (attempt {attempt+1})")
            if attempt < max_retries - 1:
                time.sleep(RETRY_BACKOFF_BASE_S ** attempt)
                continue

    raise last_error


def cross_validate(messages, temperature=TEMPERATURE, max_rounds=CROSS_VALIDATE_MAX_ROUNDS,
                   extract=None, rebuild=None):
    if extract is None or rebuild is None:
        raise ValueError("cross_validate needs extract and rebuild; see normalize.py")

    providers = list(_MODEL_NAMES)

    for round_idx in range(max_rounds):
        results = []
        for p in providers:
            try:
                r = chat(messages, provider=p, temperature=temperature)
                results.append({"provider": p, "result": r, "error": None, "entities": extract(r)})
            except Exception as e:
                results.append({"provider": p, "result": None, "error": str(e), "entities": {}})

        successes = [r for r in results if r["result"] is not None]
        if not successes:
            if round_idx < max_rounds - 1:
                logger.warn(f"cross-validate: 0/{len(providers)} succeeded, retrying...")
                time.sleep(RETRY_BACKOFF_BASE_S ** round_idx)
                continue
            raise RuntimeError(
                f"All {len(providers)} providers failed in cross-validation: "
                f"{[r['error'] for r in results]}")

        if len(successes) == 1:
            logger.info(f"cross-validate: 1/{len(providers)} answered, "
                        f"using {successes[0]['provider']}")
            return successes[0]["result"], {
                "provider": successes[0]["provider"], "consensus": "single_fallback",
                "succeeded": 1, "accepted": len(successes[0]["entities"]), "dropped": 0}

        # Half of the configured models, so a claim is kept only when more than
        # half of them make it. The comparison is strict: at half the list the
        # count has to exceed it, which for three models means two and for two
        # means both.
        threshold = CROSS_VALIDATE_MIN_VOTES
        votes = {}
        for r in successes:
            for key, payload in r["entities"].items():
                votes.setdefault(key, []).append(payload)

        accepted = [payloads[0] for payloads in votes.values() if len(payloads) > threshold]
        dropped = len(votes) - len(accepted)

        if accepted or not votes:
            agreed = [r["provider"] for r in successes]
            logger.info(f"cross-validate: {len(successes)}/{len(providers)} answered, "
                        f"{len(accepted)} entities agreed by > {threshold}, {dropped} dropped")
            return rebuild(accepted), {
                "provider": agreed[0], "consensus": f"majority_of_{len(successes)}",
                "slots": agreed, "succeeded": len(successes), "threshold": threshold,
                "accepted": len(accepted), "dropped": dropped}

        if round_idx < max_rounds - 1:
            logger.warn(f"cross-validate: no majority (round {round_idx+1}), retrying...")
            time.sleep(RETRY_BACKOFF_BASE_S ** round_idx)
        else:
            detail = "; ".join(
                f"{r['provider']}=" + json.dumps([str(k) for k in list(r["entities"])[:8]],
                                                 ensure_ascii=False)[:200]
                for r in successes)
            logger.warn(f"cross-validate: no entity reached a majority after "
                        f"{max_rounds} rounds, discarding result")
            raise RuntimeError(
                "cross-validate: no entity was listed by a majority of the "
                f"providers that answered ({[r['provider'] for r in successes]}); "
                f"result discarded | {detail}")

    raise RuntimeError("Cross-validation failed")


def ask(messages, temperature=TEMPERATURE, extract=None, rebuild=None):
    if config.ENABLE_CROSS_VALIDATION:
        return cross_validate(messages, temperature=temperature,
                              extract=extract, rebuild=rebuild)
    # One model configured, so there is nothing to cross-validate against and
    # the first model in MODEL_CONFIG answers alone.
    provider = config.PRIMARY_MODEL
    result = chat(messages, provider=provider, temperature=temperature,
                  max_retries=CHAT_MAX_RETRIES)
    return result, {"provider": provider, "consensus": "single"}


