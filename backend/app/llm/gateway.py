"""LLM gateway: Groq -> Ollama -> extractive fallback. Never raises to the caller."""

import json
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

_TIMEOUT = 30.0
ModelT = TypeVar("ModelT", bound=BaseModel)


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
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
        return data["choices"][0]["message"]["content"]


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
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
        "\nRespond with a single valid JSON object matching the required schema. "
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
