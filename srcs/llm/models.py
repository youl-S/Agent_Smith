from pydantic import BaseModel, Field, model_validator


class LLMResponse(BaseModel):
    """
    Result of a single LLM call (after the fallback cascade, if any).

    Two mutually exclusive states, enforced by the validator:
      - success: success=True, text filled, real stats, error=None
      - total failure: success=False, error set, empty text, zeroed stats
    """

    success: bool = Field(
        ...,
        description="True if a response was obtained, False if everything failed",
    )
    error: str | None = Field(
        default=None, description="Error message on failure, None on success"
    )

    text: str = Field(
        default="", description="Raw model response (empty on failure)"
    )
    finish_reason: str = Field(
        default="",
        description="Stop reason returned by the API (stop, length, ...)",
    )

    input_tokens: int = Field(default=0, description="usage.prompt_tokens")
    output_tokens: int = Field(
        default=0, description="usage.completion_tokens"
    )
    request_time_ms: float = Field(
        default=0.0,
        description="Duration of the successful call in milliseconds",
    )
    retries: int = Field(
        default=0,
        description="Failed attempts before success (0 = succeeded first try)",
    )

    model_name: str = Field(default="", description="Model actually used")
    api_url: str = Field(default="", description="API URL actually used")

    @model_validator(mode="after")
    def _check_coherence(self) -> "LLMResponse":
        if self.success:
            if not self.text:
                raise ValueError("success=True but text is empty")
            if self.error is not None:
                raise ValueError("success=True but error is set")
        else:
            if not self.error:
                raise ValueError("success=False but error is empty")
        return self

    @classmethod
    def failure(cls, error: str) -> "LLMResponse":
        """Convenience factory for a total failure."""
        return cls(success=False, error=error)


class ProviderTarget(BaseModel):
    name: str = Field(default="", description="The provider name ex Groq")
    base_url: str = Field(
        default="",
        description="provider url to comunicate with ex https://api.groq.com/openai/v1",
    )
    model: str = Field(
        default="", description="Model choose to generate answer"
    )
    key_env_vars: list[str] = Field(
        default_factory=lambda: [], description="API env variables"
    )
