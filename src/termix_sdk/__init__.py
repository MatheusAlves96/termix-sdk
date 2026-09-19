"""Python client SDK for the Termix REST API.

See docs/sdk-plan.md for the full design (this file's public surface grows
as tools/sdk-gen generates resources on top of the core in this module).
"""

from ._async_client import AsyncTermixClient
from ._auth import AsyncPendingTOTP, PendingTOTP
from ._client import TermixClient
from ._error import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    DataLockedError,
    InvalidRequestError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    TermixError,
    TOTPRequiredError,
)
from ._object import TermixObject
from ._request_options import RequestOptions
from ._response import SSEEvent, TermixResponse, TermixStreamResponse
from ._version import SPEC_VERSION, __version__

__all__ = [
    "__version__",
    "SPEC_VERSION",
    "TermixClient",
    "AsyncTermixClient",
    "PendingTOTP",
    "AsyncPendingTOTP",
    "TermixObject",
    "TermixResponse",
    "TermixStreamResponse",
    "SSEEvent",
    "RequestOptions",
    "TermixError",
    "APIConnectionError",
    "APIStatusError",
    "InvalidRequestError",
    "AuthenticationError",
    "TOTPRequiredError",
    "SessionExpiredError",
    "PermissionError",
    "NotFoundError",
    "RateLimitError",
    "DataLockedError",
    "ServerError",
]
