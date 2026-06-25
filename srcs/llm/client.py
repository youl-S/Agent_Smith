import time
import openai
from openai import OpenAI

from exceptions import AuthError, FatalError, RecoverableError
from models import LLMResponse


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
            )

        except openai.AuthenticationError as e:
            raise AuthError(f"{type(e).__name__}: {e}") from e

        except (
            openai.RateLimitError,
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
