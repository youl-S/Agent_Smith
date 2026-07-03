import os
import time

from srcs.llm.exceptions import AuthError, FatalError, RecoverableError
from srcs.llm.client import LLMClient
from srcs.llm.models import ProviderTarget, LLMResponse


class LLMManager:
    """Drive LLM calls across multiple targets and API keys.

    Cascades over the configured provider targets and their API keys: on an
    auth error (401) the key is banned for the session; on a transient error
    (429/timeout/5xx) it backs off and tries the next key; on a fatal error
    it stops. Returns a successful LLMResponse or a failure one.
    """

    def __init__(
        self,
        targets: list[ProviderTarget],
        client: LLMClient,
        base_backoff_s: float = 1.0,
        max_backoff_s: float = 8.0,
    ):
        """Initialize the manager.

        Args:
            targets: Provider targets to try in order, each with its keys.
            client: The client used to perform a single completion.
            base_backoff_s: Base delay for exponential backoff, in seconds.
            max_backoff_s: Maximum backoff delay, in seconds.
        """
        self._targets = targets
        self._client = client
        self._invalid_api_keys = set()
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s

    def _backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff, capped at max_backoff_s.

        The delay is base_backoff_s * 2**attempt, bounded by max_backoff_s,
        so repeated failures wait longer without growing unbounded.
        """

        delay = min(
            self._base_backoff_s * (2**attempt),
            self._max_backoff_s,
        )
        time.sleep(delay)

    def generate(
        self, messages, stop_sequences=None, max_tokens: int | None = None
    ) -> LLMResponse:
        """Generate a completion, cascading over targets and keys.

        Skips already-banned keys, then for each key calls the client. On
        AuthError the key is banned (no wait); on RecoverableError it backs
        off and moves on; on FatalError it returns a failure immediately.
        The number of retries is recorded on the returned response.

        Args:
            messages: The chat messages to send.
            stop_sequences: Optional stop sequences for generation.
            max_tokens: Optional cap on output tokens for this call.

        Returns:
            A successful LLMResponse, or a failure LLMResponse if every
            target and key is exhausted.
        """
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
