class LLMError(Exception):
    """Base class for every error raised by the LLM layer."""


class RecoverableError(LLMError):
    """Transient failure: try another key or provider (429, timeout, 5xx, bad key)."""


class FatalError(LLMError):
    """Non-recoverable: switching target won't help (e.g. 400 bad request)."""
