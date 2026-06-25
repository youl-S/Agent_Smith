from pydantic import BaseModel, Field, model_validator
from enum import Enum, auto


class ExtractedBlockStatus(Enum):
    OK = auto()
    NO_CODE_FOUND = auto()
    MALFORMED_RECOVERED = auto()


class ExtractedBlockFormat(Enum):
    PYTHON_FORMAT = auto()
    XML_FORMAT = auto()
    JSON_HERMES_FORMAT = auto()
    REACT_FORMAT = auto()
    UNKNOWN = auto()


class LLMResponse(BaseModel):
    """
    Result of a single LLM call (after the fallback cascade, if any).

    Two mutually exclusive states, enforced by the validator:
      - success: success=True, text filled, real stats, error=None
      - total failure: success=False, error set, empty text, zeroed stats
    """

    success: bool = Field(
        ...,
        description=(
            "True if a response was obtained, False if everything failed"
        ),
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
        """
        Convenience factory for a total failure.
        """
        return cls(success=False, error=error)


class ProviderTarget(BaseModel):
    name: str = Field(default="", description="The provider name ex Groq")
    base_url: str = Field(
        default="",
        description=(
            "provider url to comunicate with ex https://api.groq.com/openai/v1"
        ),
    )
    model: str = Field(
        default="", description="Model choose to generate answer"
    )
    key_env_vars: list[str] = Field(
        default_factory=lambda: [], description="API env variables"
    )


class ExtractedCodeBlock(BaseModel):
    code_extracted: str | None = Field(
        default=None, description="Code extracted from the llm response"
    )
    extracted_block_status: ExtractedBlockStatus = Field(
        description=(
            "LLM response status (OK, NO_CODE_FOUND, MALFORMED_RECOVERED)"
        )
    )
    extracted_block_format: ExtractedBlockFormat = Field(
        description="Code response 's format"
    )

    @model_validator(mode="after")
    def _check_coherence(self) -> "ExtractedCodeBlock":
        has_code = bool(self.code_extracted)
        if self.extracted_block_status == ExtractedBlockStatus.NO_CODE_FOUND:
            if has_code:
                raise ValueError("status=NO_CODE_FOUND but code is present")
            if self.extracted_block_format != ExtractedBlockFormat.UNKNOWN:
                raise ValueError(
                    "status=NO_CODE_FOUND but format is not UNKNOWN"
                )
        else:
            if not has_code:
                raise ValueError(
                    f"status={self.extracted_block_status.name} "
                    "but no code extracted"
                )
            if self.extracted_block_format == ExtractedBlockFormat.UNKNOWN:
                raise ValueError(
                    f"status={self.extracted_block_status.name} "
                    "but format is UNKNOWN"
                )
        return self
