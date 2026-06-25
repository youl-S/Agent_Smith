from exceptions import FatalError, RecoverableError
from client import LLMClient
from models import ProviderTarget, LLMResponse

import os


class LLMManager:
    def __init__(self, targets: list[ProviderTarget], client: LLMClient):
        self._targets = targets
        self._client = client

    def generate(self, messages, stop_sequences=None) -> LLMResponse:
        retries = 0
        last_error = "no targets configured"
        for target in self._targets:
            for key_var in target.key_env_vars:
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
                    )
                    resp.retries = retries
                    return resp
                except RecoverableError as e:
                    retries += 1
                    last_error = str(e)
                    continue
                except FatalError as e:
                    return LLMResponse.failure(str(e))
        return LLMResponse.failure(f"all targets exhausted: {last_error}")


# TODO: 429 -> court backoff avant retry ; 401 -> marquer la clé morte (état interne) et la skip
