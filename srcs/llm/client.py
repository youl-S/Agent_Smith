import re
import time
import openai
from openai import OpenAI

from srcs.llm.exceptions import (
    AuthError,
    FatalError,
    RateLimitError,
    RecoverableError,
)
from srcs.llm.models import LLMResponse


def _parse_retry_after(err: openai.RateLimitError) -> float | None:
    """Extract the server-suggested wait, in seconds, from a 429.

    Prefers the standard ``Retry-After`` header; falls back to parsing
    the message body (e.g. "Please try again in 19.45s"). Returns None
    if neither is present.
    """
    response = getattr(err, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except (TypeError, ValueError):
                pass

    match = re.search(r"try again in ([\d.]+)\s*s", str(err))
    if match:
        return float(match.group(1))

    return None


class LLMClient:
    """
    Executes a single chat completion against a single provider target.

    It does not know about key rotation or provider fallback: it is given
    one base_url, one model, one api_key, and either returns an LLMResponse
    (success) or raises AuthError / RecoverableError / FatalError.
    """

    def __init__(self, timeout_s: float = 60.0):
        self._timeout_s = timeout_s

    def complete(
        self,
        base_url: str,
        model: str,
        api_key: str,
        messages: list[dict],
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
            timeout=self._timeout_s,
        )

        start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                stop=stop_sequences or None,
                max_tokens=max_tokens,
            )

        except openai.AuthenticationError as e:
            raise AuthError(f"{type(e).__name__}: {e}") from e

        except openai.RateLimitError as e:
            raise RateLimitError(
                f"{type(e).__name__}: {e}",
                retry_after=_parse_retry_after(e),
            ) from e

        except (
            openai.APITimeoutError,
            openai.APIConnectionError,
        ) as e:
            raise RecoverableError(f"{type(e).__name__}: {e}") from e

        except openai.BadRequestError as e:
            raise FatalError(f"{type(e).__name__}: {e}") from e

        except openai.APIStatusError as e:
            if e.status_code >= 500:
                raise RecoverableError(f"HTTP {e.status_code}: {e}") from e
            raise FatalError(f"HTTP {e.status_code}: {e}") from e

        except openai.APIError as e:
            raise RecoverableError(f"{type(e).__name__}: {e}") from e

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        choice = resp.choices[0]
        usage = resp.usage

        return LLMResponse(
            success=True,
            text=choice.message.content or "",
            finish_reason=choice.finish_reason or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            request_time_ms=elapsed_ms,
            retries=0,
            model_name=model,
            api_url=base_url,
        )
