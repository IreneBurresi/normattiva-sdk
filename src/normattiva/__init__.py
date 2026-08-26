"""SDK non ufficiale per Normattiva, il portale della legge vigente."""

from normattiva import codici
from normattiva.codici import AttoNoto
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
from normattiva.testo import normalize_accents
from normattiva.urn import Urn

__version__ = "0.1.0"

__all__ = [
    "AmbiguityError",
    "AttoNoto",
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
    "Urn",
    "ValidityMismatchError",
    "VersionNotFoundError",
    "__version__",
    "codici",
    "normalize_accents",
]
