import os
import time

from srcs.llm.exceptions import AuthError, FatalError, RecoverableError
from srcs.llm.client import LLMClient
from srcs.llm.models import ProviderTarget, LLMResponse


class LLMManager:
    def __init__(
        self,
        targets: list[ProviderTarget],
        client: LLMClient,
        base_backoff_s: float = 1.0,
        max_backoff_s: float = 8.0,
    ):
        self._targets = targets
        self._client = client
        self._invalid_api_keys = set()
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s

    def _backoff(self, attempt: int) -> None:
        delay = min(
            self._base_backoff_s * (2**attempt),
            self._max_backoff_s,
        )
        time.sleep(delay)

    def generate(
        self, messages, stop_sequences=None, max_tokens: int | None = None
    ) -> LLMResponse:
        retries = 0
        last_error = "no targets configured"

        for target in self._targets:
            for key_var in target.key_env_vars:
                if key_var in self._invalid_api_keys:
                    continue

                api_key = os.environ.get(key_var)
                if not api_key:
                    continue

                try:
                    resp = self._client.complete(
                        target.base_url,
                        target.model,
                        api_key,
                        messages,
                        stop_sequences,
                        max_tokens,
                    )
                    resp.retries = retries
                    return resp

                except AuthError as e:
                    last_error = str(e)
                    self._invalid_api_keys.add(key_var)
                    retries += 1
                    continue

                except RecoverableError as e:
                    last_error = str(e)
                    self._backoff(retries)
                    retries += 1
                    continue

                except FatalError as e:
                    return LLMResponse.failure(str(e))

        return LLMResponse.failure(f"all targets exhausted: {last_error}")
