"""Our own error types. Providers translate SDK-specific errors into these,
so the rest of the app never depends on a particular SDK."""


class LLMError(Exception):
    """Base class. `error_type` is the short label saved in the llm_calls table."""

    error_type = "llm_error"


class RateLimitError(LLMError):
    """Provider said 'too many requests' (HTTP 429). Worth retrying after a wait."""

    error_type = "rate_limit"

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after  # seconds, from the Retry-After header if given


class TransientError(LLMError):
    """Timeout, network problem or 5xx. Worth retrying."""

    error_type = "transient"

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class AuthError(LLMError):
    """Bad or missing API key / no permission. Retrying cannot help."""

    error_type = "auth"


class BadRequestError(LLMError):
    """The request itself is wrong (e.g. unknown model name). Retrying cannot help."""

    error_type = "bad_request"


class InvalidOutputError(LLMError):
    """The model answered, but not with valid JSON for the expected schema."""

    error_type = "invalid_output"

    def __init__(self, message: str, raw_text: str | None = None) -> None:
        super().__init__(message)
        self.raw_text = raw_text
