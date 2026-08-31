"""LLM gateway: Groq -> Ollama -> extractive fallback. Never raises to the caller."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LlmEmptyResponse(RuntimeError):
    """A provider replied successfully but with no usable text."""


settings = get_settings()

_TIMEOUT = 30.0
# The local tier is a 7B model on the demo machine's own CPU/GPU. A clinical
# brief is a long generation and routinely takes over a minute there; timing it
# out at the hosted provider's budget threw away the one tier that still works
# when the hosted free-tier quota is spent.
_OLLAMA_TIMEOUT = 180.0
# Past this, waiting is worse than answering from the next tier: the caller is
# a doctor with a patient in front of them, not a batch job.
_MAX_RATE_LIMIT_WAIT = 20.0
ModelT = TypeVar("ModelT", bound=BaseModel)

# One pooled client per (event loop, timeout) instead of a fresh one per call.
# Opening a client per request threw away the connection after every completion,
# so each call paid a fresh DNS lookup and TLS handshake to the provider -- on
# the order of a couple of hundred milliseconds, on top of an already slow
# generation, repeated for every turn of a triage conversation.
#
# The loop is part of the key because a client binds to the loop that created
# it: the test suite runs cases on separate loops, and reusing a client across
# them fails on the transport rather than merely performing badly.
_clients: dict[tuple[int, float], httpx.AsyncClient] = {}
_POOL_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _client(timeout: float) -> httpx.AsyncClient:
    key = (id(asyncio.get_running_loop()), timeout)
    client = _clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=timeout, limits=_POOL_LIMITS)
        _clients[key] = client
    return client


async def aclose_clients() -> None:
    """Close every pooled client. Called from the app lifespan on shutdown."""
    for client in list(_clients.values()):
        if not client.is_closed:
            try:
                await client.aclose()
            except Exception as exc:  # noqa: BLE001
                log.warning("llm_client_close_failed", error=str(exc))
    _clients.clear()


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """Seconds Groq asked us to wait, or None if it did not say."""
    raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-tokens")
    if not raw:
        return None
    try:
        # Groq sends plain seconds on Retry-After and suffixed values like
        # "7.66s" or "2m59s" on the x-ratelimit-reset-* headers.
        if raw.endswith("s") and "m" not in raw:
            return float(raw[:-1])
        return float(raw)
    except ValueError:
        return None


def _groq_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
async def _groq_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    # Reasoning models bill their hidden reasoning against max_tokens, so a tight
    # budget is spent thinking and the reply comes back empty. Cap the reasoning
    # so short calls (a single triage question) still leave room for an answer.
    if "gpt-oss" in settings.groq_model:
        payload["reasoning_effort"] = "low"
    client = _client(_TIMEOUT)
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=_groq_headers(),
        json=payload,
    )
    # Groq's free tier rate-limits in bursts and says exactly how long to
    # wait. Sitting out a short cooldown costs seconds; falling through to
    # the extractive tier costs the caller a generated answer entirely, and
    # for a brief that means an ungrounded one the doctor cannot use.
    if resp.status_code == 429:
        wait = _retry_after_seconds(resp)
        if wait is not None and wait <= _MAX_RATE_LIMIT_WAIT:
            log.warning("llm_rate_limited", provider="groq", retry_after=wait)
            await asyncio.sleep(wait)
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=_groq_headers(),
                json=payload,
            )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    log.info(
        "llm_call",
        provider="groq",
        model=settings.groq_model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )
    choice = data["choices"][0]
    text = choice["message"]["content"] or ""
    if not text.strip():
        # An empty completion is a failure, not an answer -- fall through to
        # the next provider rather than handing callers a blank string.
        raise LlmEmptyResponse(
            f"groq returned an empty completion (finish_reason="
            f"{choice.get('finish_reason')!r}, max_tokens={max_tokens})"
        )
    return text


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)
async def _ollama_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"
    client = _client(_OLLAMA_TIMEOUT)
    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()
    log.info("llm_call", provider="ollama", model=settings.ollama_model)
    return data["message"]["content"]


def _extractive_fallback(prompt: str, system: str | None) -> str:
    log.warning("llm_call", provider="extractive_fallback")
    snippet = prompt.strip().splitlines()
    head = " ".join(snippet[:3])[:400]
    return (
        "Automated summary unavailable from the language model provider; "
        f"showing retrieved context instead: {head}"
    )


async def complete(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    if settings.groq_api_key:
        try:
            return await _groq_chat(messages, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            log.warning("llm_provider_failed", provider="groq", error=str(exc))
    try:
        return await _ollama_chat(messages, max_tokens=max_tokens, temperature=temperature)
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_provider_failed", provider="ollama", error=str(exc))
    return _extractive_fallback(prompt, system)


async def stream(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    text = await complete(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
    chunk_size = 24
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def _field_hint(schema: type[BaseModel]) -> str:
    """The schema's keys and shapes, as a one-line hint for the model.

    Small local models are the ones that get the shape wrong -- a 7B asked for
    `differentials` will happily return `differential1`, `differential2` -- and
    naming the keys up front costs a handful of tokens against a whole retry.
    """
    parts = []
    for name, field in schema.model_fields.items():
        ann = field.annotation
        kind = getattr(ann, "__name__", None) or str(ann).replace("typing.", "")
        parts.append(f"{name} ({kind})")
    return ", ".join(parts)


def _fallback_instance(schema: type[ModelT]) -> ModelT:
    defaults: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if field.is_required():
            ann = field.annotation
            if ann in (str, str | None):
                defaults[name] = ""
            elif ann in (int, int | None):
                defaults[name] = 0
            elif ann in (float, float | None):
                defaults[name] = 0.0
            elif ann in (bool, bool | None):
                defaults[name] = False
            else:
                defaults[name] = [] if "list" in str(ann) else None
    return schema.model_construct(**defaults)


async def json_complete(
    prompt: str,
    *,
    schema: type[ModelT],
    system: str | None = None,
    retries: int = 2,
) -> ModelT:
    sys_prompt = (system or "") + (
        "\nRespond with a single valid JSON object with exactly these keys: "
        f"{_field_hint(schema)}. "
        "Use those key names verbatim -- not numbered variants, not synonyms. "
        "No prose, no markdown fences."
    )
    last_error: str | None = None
    current_prompt = prompt
    for attempt in range(retries + 1):
        try:
            raw = await complete(
                current_prompt, system=sys_prompt, max_tokens=2048, temperature=0.1
            )
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            data = json.loads(cleaned)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            current_prompt = (
                f"{prompt}\n\nYour previous response was invalid JSON for this schema: "
                f"{last_error}. Return corrected JSON only."
            )
            log.warning("json_complete_retry", attempt=attempt, error=last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            log.warning("json_complete_error", error=last_error)
            break
    log.error("json_complete_fallback", schema=schema.__name__, error=last_error)
    return _fallback_instance(schema)
