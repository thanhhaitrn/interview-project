"""Helpers for talking to Ollama-compatible APIs."""

from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

import requests
from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_ollama import ChatOllama
from pydantic import BaseModel


load_dotenv()


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)
_LLM_CALL_TRACE: list[dict[str, Any]] = []


class _UsageCaptureHandler(BaseCallbackHandler):
    """Capture provider token metadata when LangChain exposes it."""

    def __init__(self) -> None:
        self.usage_metadata: dict[str, Any] = {}
        self.response_metadata: dict[str, Any] = {}

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        llm_output = getattr(response, "llm_output", None)
        if isinstance(llm_output, dict):
            self.response_metadata.update(llm_output)

        generations = getattr(response, "generations", []) or []
        for generation_group in generations:
            for generation in generation_group:
                message = getattr(generation, "message", None)
                if message is None:
                    continue

                usage_metadata = getattr(message, "usage_metadata", None)
                if isinstance(usage_metadata, dict):
                    self.usage_metadata.update(usage_metadata)

                response_metadata = getattr(message, "response_metadata", None)
                if isinstance(response_metadata, dict):
                    self.response_metadata.update(response_metadata)


def reset_call_trace() -> None:
    """Clear runtime LLM call trace for a new interview run."""
    _LLM_CALL_TRACE.clear()


def get_call_trace() -> list[dict[str, Any]]:
    """Return a copy of collected LLM call metadata."""
    return [dict(item) for item in _LLM_CALL_TRACE]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate when provider usage metadata is unavailable."""
    if not text:
        return 0

    return max(1, round(len(text) / 4))


def _first_int(payload: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)

    token_usage = payload.get("token_usage")
    if isinstance(token_usage, dict):
        return _first_int(token_usage, keys)

    return None


def _resolve_token_counts(
    *,
    prompt_text: str,
    output_text: str,
    usage_metadata: dict[str, Any],
    response_metadata: dict[str, Any],
) -> dict[str, Any]:
    estimated_prompt_tokens = _estimate_tokens(prompt_text)
    estimated_completion_tokens = _estimate_tokens(output_text)

    prompt_tokens = _first_int(
        usage_metadata,
        ["input_tokens", "prompt_tokens", "prompt_eval_count"],
    )
    completion_tokens = _first_int(
        usage_metadata,
        ["output_tokens", "completion_tokens", "eval_count"],
    )
    total_tokens = _first_int(
        usage_metadata,
        ["total_tokens"],
    )

    if prompt_tokens is None:
        prompt_tokens = _first_int(response_metadata, ["prompt_eval_count"])
    if completion_tokens is None:
        completion_tokens = _first_int(response_metadata, ["eval_count"])
    if total_tokens is None:
        total_tokens = _first_int(response_metadata, ["total_tokens"])

    token_source = "provider_usage_metadata"
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        token_source = "estimated_chars_div_4"
        prompt_tokens = estimated_prompt_tokens
        completion_tokens = estimated_completion_tokens
        total_tokens = prompt_tokens + completion_tokens
    else:
        prompt_tokens = prompt_tokens or estimated_prompt_tokens
        completion_tokens = completion_tokens or estimated_completion_tokens
        total_tokens = total_tokens or prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "token_source": token_source,
    }


def _prompt_to_text(prompt: Any) -> str:
    if hasattr(prompt, "to_string"):
        return str(prompt.to_string())

    return str(prompt)


def get_model_settings():
    """Read Ollama configuration from environment variables."""
    base_url = os.getenv("OLLAMA_BASE_URL")
    api_key = os.getenv("OLLAMA_API_KEY", "")
    model_name = os.getenv("OLLAMA_MODEL", "")

    if not base_url:
        raise ValueError("OLLAMA_BASE_URL is missing in .env")
    if not model_name:
        raise ValueError("OLLAMA_MODEL is missing in .env")

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
    }


def get_model_temperature(default: float = 0.2) -> float:
    """Read model temperature from environment with a safe fallback."""
    raw_value = os.getenv("OLLAMA_TEMPERATURE")
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def get_max_retries(default: int = 2) -> int:
    """Read the max structured-output retry count from the environment."""
    raw_value = os.getenv("OLLAMA_MAX_RETRIES")
    if raw_value is None:
        return default

    try:
        return max(0, int(raw_value))
    except ValueError:
        return default


def get_request_timeout(default: float = 120.0) -> float:
    """Read the LLM request timeout (seconds) from the environment."""
    raw_value = os.getenv("OLLAMA_TIMEOUT")
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _status_code(exc: Exception) -> int | None:
    """Best-effort HTTP status code from common Ollama/HTTP error shapes."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)

    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_retryable_error(exc: Exception) -> bool:
    """Retry only transient failures: network/timeout and HTTP 5xx.

    Client errors (4xx, including 429 weekly-quota that will not recover within
    a run) and schema validation errors are not retryable — the same prompt
    would fail again, so fail fast instead of wasting attempts.
    """
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        return False

    status = _status_code(exc)
    if status is not None:
        return 500 <= status <= 599

    # No HTTP status: typically a connection/timeout error, which is retryable.
    return True


def get_ollama_chat_model(
    settings: dict[str, str] | None = None,
    response_format: str | dict[str, Any] | None = None,
    temperature: float | None = None,
) -> ChatOllama:
    """Create a LangChain Ollama chat model for structured-output calls."""
    settings = settings or get_model_settings()
    client_kwargs: dict[str, Any] = {"timeout": get_request_timeout()}
    model_kwargs: dict[str, Any] = {}

    if settings["api_key"]:
        client_kwargs["headers"] = {
            "Authorization": f"Bearer {settings['api_key']}"
        }

    if response_format is not None:
        model_kwargs["format"] = response_format

    return ChatOllama(
        model=settings["model_name"],
        base_url=settings["base_url"].rstrip("/"),
        temperature=(
            temperature if temperature is not None else get_model_temperature()
        ),
        client_kwargs=client_kwargs,
        **model_kwargs,
    )


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    return str(content)


def _load_json_value(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Model returned an empty response.")

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        preview = stripped[:500]
        raise ValueError(
            "Model response must be exactly one JSON value with no markdown, "
            f"code fences, or extra text: {preview}"
        ) from exc


def _build_json_retry_prompt(
    *,
    prompt_text: str,
    schema: type[StructuredOutput],
    primary_error: str,
) -> str:
    schema_json = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
    return (
        "The previous model response could not be parsed as JSON.\n"
        f"Parser error: {primary_error}\n\n"
        "Retry the same task and return exactly one JSON value that validates "
        f"against this Pydantic schema: {schema.__name__}.\n"
        "Do not include markdown, code fences, commentary, or blank output.\n\n"
        f"JSON schema:\n{schema_json}\n\n"
        f"Original prompt:\n{prompt_text}"
    )


def _call_json_mode_retry(
    *,
    prompt_text: str,
    schema: type[StructuredOutput],
    settings: dict[str, str],
    primary_error: str,
) -> tuple[StructuredOutput, str, str, str, _UsageCaptureHandler]:
    retry_prompt = _build_json_retry_prompt(
        prompt_text=prompt_text,
        schema=schema,
        primary_error=primary_error,
    )
    fallback_errors = []

    for response_format in (schema.model_json_schema(), "json"):
        usage_handler = _UsageCaptureHandler()
        try:
            llm = get_ollama_chat_model(
                settings,
                response_format=response_format,
            )
            message = llm.invoke(
                retry_prompt,
                config={"callbacks": [usage_handler]},
            )
            raw_text = _message_content_to_text(getattr(message, "content", message))
            parsed_json = _load_json_value(raw_text)
            parsed_result = schema.model_validate(parsed_json)
            format_name = (
                "json_schema"
                if isinstance(response_format, dict)
                else str(response_format)
            )
            return parsed_result, raw_text, retry_prompt, format_name, usage_handler
        except Exception as exc:
            fallback_errors.append(str(exc))

    raise RuntimeError("; ".join(fallback_errors))


def call_llm_with_structured_output(
    prompt: Any,
    schema: type[StructuredOutput],
    temperature: float | None = None,
    max_retries: int | None = None,
) -> StructuredOutput:
    """Call Ollama through LangChain and validate the response as `schema`.

    Retries with a short backoff when the call or structured parse fails, so a
    single bad response does not abort the interview. ``temperature`` overrides
    the env default for this call (use 0 for deterministic scoring).
    """
    prompt_text = _prompt_to_text(prompt)
    trace_prompt_text = prompt_text
    output_text = ""
    settings: dict[str, str] = {}
    started = time.perf_counter()
    status = "ok"
    error = ""
    primary_error = ""
    fallback_used = False
    fallback_format = ""
    fallback_raw_chars = 0
    retry_limit = get_max_retries() if max_retries is None else max(0, max_retries)
    attempts = 0
    usage_handler = _UsageCaptureHandler()
    trace_usage_handler = usage_handler

    try:
        settings = get_model_settings()
        llm = get_ollama_chat_model(settings, temperature=temperature)
        structured_llm = llm.with_structured_output(
            schema,
            method="json_schema",
        )

        last_error: Exception | None = None
        for attempt in range(retry_limit + 1):
            attempts = attempt + 1
            try:
                result = structured_llm.invoke(
                    prompt,
                    config={"callbacks": [usage_handler]},
                )

                if isinstance(result, schema):
                    output_text = result.model_dump_json(exclude_none=True)
                    return result

                parsed_result = schema.model_validate(result)
                output_text = parsed_result.model_dump_json(exclude_none=True)
                return parsed_result
            except Exception as exc:  # noqa: BLE001 - classify then retry/raise
                last_error = exc
                if attempt < retry_limit and _is_retryable_error(exc):
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise

        assert last_error is not None
        raise last_error
    except Exception as exc:
        primary_error = str(exc)
        try:
            (
                retry_result,
                raw_retry_text,
                retry_prompt,
                fallback_format,
                retry_usage_handler,
            ) = _call_json_mode_retry(
                prompt_text=prompt_text,
                schema=schema,
                settings=settings,
                primary_error=primary_error,
            )
            fallback_used = True
            fallback_raw_chars = len(raw_retry_text)
            trace_prompt_text = retry_prompt
            trace_usage_handler = retry_usage_handler
            output_text = retry_result.model_dump_json(exclude_none=True)
            return retry_result
        except Exception as fallback_exc:
            status = "error"
            error = (
                "Structured output failed. "
                f"Primary parser error: {primary_error}. "
                f"JSON retry error: {fallback_exc}"
            )
            raise RuntimeError(error) from fallback_exc
    finally:
        runtime_seconds = time.perf_counter() - started
        token_counts = _resolve_token_counts(
            prompt_text=trace_prompt_text,
            output_text=output_text,
            usage_metadata=trace_usage_handler.usage_metadata,
            response_metadata=trace_usage_handler.response_metadata,
        )
        trace_item = {
            "schema": schema.__name__,
            "model": settings.get("model_name", ""),
            "base_url": settings.get("base_url", ""),
            "status": status,
            "structured_output_method": "json_schema",
            "attempts": attempts,
            "runtime_seconds": round(runtime_seconds, 4),
            "prompt_chars": len(trace_prompt_text),
            "completion_chars": len(output_text),
            "prompt_tokens": token_counts["prompt_tokens"],
            "completion_tokens": token_counts["completion_tokens"],
            "total_tokens": token_counts["total_tokens"],
            "token_source": token_counts["token_source"],
        }
        if fallback_used:
            trace_item["fallback_used"] = True
            trace_item["fallback_format"] = fallback_format
            trace_item["fallback_raw_chars"] = fallback_raw_chars
            trace_item["primary_error"] = primary_error
        if token_counts["token_source"] == "estimated_chars_div_4":
            trace_item["prompt_tokens_estimate"] = token_counts["prompt_tokens"]
            trace_item["completion_tokens_estimate"] = token_counts[
                "completion_tokens"
            ]
            trace_item["total_tokens_estimate"] = token_counts["total_tokens"]
        if trace_usage_handler.usage_metadata:
            trace_item["usage_metadata"] = trace_usage_handler.usage_metadata
        if trace_usage_handler.response_metadata:
            trace_item["response_metadata"] = trace_usage_handler.response_metadata
        if error:
            trace_item["error"] = error

        _LLM_CALL_TRACE.append(trace_item)


def call_ollama_api(prompt: str, response_format: str = "json") -> str:
    """Send a prompt to an Ollama server using its `/api/generate` route."""
    settings = get_model_settings()

    base_url = settings["base_url"].rstrip("/")
    url = f"{base_url}/api/generate"

    headers = {"Content-Type": "application/json"}
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    payload = {
        "model": settings["model_name"],
        "prompt": prompt,
        "stream": False,
        "format": response_format,
        "options": {
            "temperature": get_model_temperature()
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120
    )

    response.raise_for_status()
    data = response.json()

    if "response" not in data:
        raise ValueError("Ollama response is missing the 'response' field.")

    return data["response"]


def call_llm_api(prompt: str) -> str:
    """Call Ollama and return generated JSON text."""
    return call_ollama_api(prompt=prompt, response_format="json")
