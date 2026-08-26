"""SDK non ufficiale per Normattiva, il portale della legge vigente."""

from normattiva.errori import (
    AmbiguityError,
    ConnectionError,
    ExportFailedError,
    InvalidArgumentError,
    InvalidUrnError,
    NormattivaError,
    NotFoundError,
    NotYetInForceError,
    OverloadedError,
    RequestBlockedError,
    RuleCode,
    RuleViolationError,
    TooManyResultsError,
    TruncationError,
    UnexpectedResponseError,
    ValidityMismatchError,
    VersionNotFoundError,
)

__version__ = "0.1.0"

__all__ = [
    "AmbiguityError",
    "ConnectionError",
    "ExportFailedError",
    "InvalidArgumentError",
    "InvalidUrnError",
    "NormattivaError",
    "NotFoundError",
    "NotYetInForceError",
    "OverloadedError",
    "RequestBlockedError",
    "RuleCode",
    "RuleViolationError",
    "TooManyResultsError",
    "TruncationError",
    "UnexpectedResponseError",
    "ValidityMismatchError",
    "VersionNotFoundError",
    "__version__",
]
