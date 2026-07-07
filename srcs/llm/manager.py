import os
import time

from srcs.llm.exceptions import (
    AuthError,
    FatalError,
    RateLimitError,
    RecoverableError,
)
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
        max_rate_limit_wait_s: float = 60.0,
        max_rate_limit_rounds: int = 3,
        rate_limit_wait_s: int = 15,
    ):
        """Initialize the manager.

        Args:
            targets: Provider targets to try in order, each with its keys.
            client: The client used to perform a single completion.
            base_backoff_s: Base delay for exponential backoff, in seconds.
            max_backoff_s: Maximum backoff delay, in seconds.
            max_rate_limit_wait_s: Only wait for a 429 whose reported delay
                is shorter than this; if the shortest delay across all keys
                is longer, give up instead of sleeping.
            max_rate_limit_rounds: How many extra passes over all keys to make
                once every usable key is rate limited. Bounds the total wait so
                a persistently throttled provider cannot loop forever.
        """
        self._targets = targets
        self._client = client
        self._invalid_api_keys = set()
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s
        self._max_rate_limit_wait_s = max_rate_limit_wait_s
        self._max_rate_limit_rounds = max_rate_limit_rounds
        self._rate_limit_wait_s = rate_limit_wait_s

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

        Makes a full pass over every usable key before ever waiting on a
        rate limit: a 429 defers the key to the next pass instead of
        sleeping on it. Only once every remaining key has been rate limited
        does it sleep once (for the shortest server-suggested delay, or a
        backoff if none was given) and try them all again, up to
        max_rate_limit_rounds extra passes.

        Within a pass, AuthError bans the key (no wait), any other
        RecoverableError backs off and moves to the next key, and FatalError
        returns a failure immediately. The number of retries is recorded on
        the response.

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

        for rate_limit_round in range(self._max_rate_limit_rounds + 1):
            rate_limited_waits: list[float | None] = []
            any_key_available = False

            for target in self._targets:
                for key_var in target.key_env_vars:
                    if key_var in self._invalid_api_keys:
                        continue

                    api_key = os.environ.get(key_var)

                    if not api_key:
                        continue

                    any_key_available = True

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

                    except RateLimitError as e:
                        last_error = str(e)
                        retries += 1
                        rate_limited_waits.append(e.retry_after)

                    except RecoverableError as e:
                        last_error = str(e)
                        retries += 1
                        self._backoff(retries)

                    except FatalError as e:
                        last_error = str(e)
                        self._invalid_api_keys.add(key_var)
                        retries += 1

            if not any_key_available or not rate_limited_waits:
                break

            waits = [w for w in rate_limited_waits if w is not None]
            wait = min(waits) if waits else None
            if wait is None:
                time.sleep(self._rate_limit_wait_s)
            elif wait < self._max_rate_limit_wait_s:
                time.sleep(wait)
            else:
                break

        return LLMResponse.failure(f"all targets exhausted: {last_error}")
