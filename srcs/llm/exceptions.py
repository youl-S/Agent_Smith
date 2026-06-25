class LLMError(Exception):
    """
    Base class for every error raised by the LLM layer.
    """


class RecoverableError(LLMError):
    """
    Transient failure: try another key or provider
    (429, timeout, 5xx, bad key).
    """


class AuthError(RecoverableError):
    """
    Dead credential (401). Recoverable (try next key) but the key is
    permanently invalid, so it must be removed from the pool.
    """


class FatalError(LLMError):
    """
    Non-recoverable: switching target won't help (e.g. 400 bad request).
    """
