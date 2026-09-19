"""The login/TOTP flow (docs/sdk-plan.md phase F2).

`POST /users/login` and `POST /users/totp/verify-login` are public
endpoints (`security: []` in the spec) — there's no credential yet when
calling them, which is why they go through `ClientOptions.anonymous()`
instead of a normal `TermixClient`.

Both endpoints only put the JWT in the response *body* when the request
looks like it came from a native app (`user-totp-routes.ts`/`users.ts`:
`isNativeAppRequest`, checked via the `X-Electron-App: true` header or a
`Termix-Mobile/` User-Agent prefix). Otherwise the JWT only ever reaches a
`Set-Cookie: jwt=...` header, which is useless to a Python client — so
every request this module makes sends `X-Electron-App: true`
unconditionally to guarantee the token comes back in the body
(docs/sdk-plan.md section 2, item 2, and docs/api-schema-validation.md
case 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._api_requestor import APIRequestor, AsyncAPIRequestor
from ._client_options import ClientOptions
from ._error import TermixError

if TYPE_CHECKING:
    from ._async_client import AsyncTermixClient
    from ._client import TermixClient

DATABASE_SERVICE = "database"
NATIVE_APP_HEADERS = {"X-Electron-App": "true"}


def _merge_native_headers(default_headers: dict[str, str] | None) -> dict[str, str]:
    return {**NATIVE_APP_HEADERS, **(default_headers or {})}


def _extract_token(data: dict[str, Any], *, endpoint: str) -> str:
    token = data.get("token")
    if not isinstance(token, str) or not token:
        raise TermixError(
            f"{endpoint} answered success without a token in the body, even "
            f"though the SDK always sends X-Electron-App: true. This "
            f"shouldn't happen against a real Termix instance — the token "
            f"only stays cookie-only when that header is absent. Body: "
            f"{data!r}"
        )
    return token


class PendingTOTP:
    """Returned by `login()`/`login_async()` when the account has TOTP
    enabled and the device isn't trusted. Call `verify()`/`verify_async()`
    with the 6-digit code to finish authenticating.

    `temp_token` expires after 10 minutes (`users.ts`: `generateJWTToken`
    with `expiresIn: "10m"`) and is only valid for this one exchange —
    it's a distinct, narrowly-scoped token, not a usable API credential.
    """

    def __init__(
        self,
        *,
        options: ClientOptions,
        requestor: APIRequestor,
        temp_token: str,
        remember_me: bool,
    ) -> None:
        self._options = options
        self._requestor = requestor
        self.temp_token = temp_token
        self.remember_me = remember_me

    def verify(self, totp_code: str) -> TermixClient:
        from ._client import TermixClient

        response = self._requestor.request(
            "POST",
            "/users/totp/verify-login",
            service=DATABASE_SERVICE,
            json_body={
                "temp_token": self.temp_token,
                "totp_code": totp_code,
                "rememberMe": self.remember_me,
            },
        )
        data = (response.data if response else None) or {}
        jwt = _extract_token(data, endpoint="POST /users/totp/verify-login")
        authed_options = self._options.with_jwt(jwt)
        self._requestor._options = authed_options
        return TermixClient._with_options(authed_options, self._requestor)


class AsyncPendingTOTP:
    """Async mirror of `PendingTOTP` — see its docstring."""

    def __init__(
        self,
        *,
        options: ClientOptions,
        requestor: AsyncAPIRequestor,
        temp_token: str,
        remember_me: bool,
    ) -> None:
        self._options = options
        self._requestor = requestor
        self.temp_token = temp_token
        self.remember_me = remember_me

    async def verify(self, totp_code: str) -> AsyncTermixClient:
        from ._async_client import AsyncTermixClient

        response = await self._requestor.request(
            "POST",
            "/users/totp/verify-login",
            service=DATABASE_SERVICE,
            json_body={
                "temp_token": self.temp_token,
                "totp_code": totp_code,
                "rememberMe": self.remember_me,
            },
        )
        data = (response.data if response else None) or {}
        jwt = _extract_token(data, endpoint="POST /users/totp/verify-login")
        authed_options = self._options.with_jwt(jwt)
        self._requestor._options = authed_options
        return AsyncTermixClient._with_options(authed_options, self._requestor)


def login(
    *,
    base_url: str,
    username: str,
    password: str,
    remember_me: bool = False,
    service_urls: dict[str, str] | None = None,
    timeout: float = 30.0,
    verify: bool = True,
    max_network_retries: int = 2,
    default_headers: dict[str, str] | None = None,
    _http_client: Any = None,
) -> TermixClient | PendingTOTP:
    """`POST /users/login`. Returns a ready `TermixClient` when the account
    has no second factor (or the device is already trusted server-side),
    or a `PendingTOTP` to finish with a 6-digit code otherwise.
    """
    from ._client import TermixClient

    options = ClientOptions.anonymous(
        base_url=base_url,
        service_urls=service_urls,
        timeout=timeout,
        verify=verify,
        max_network_retries=max_network_retries,
        default_headers=_merge_native_headers(default_headers),
    )
    requestor = APIRequestor(options, http_client=_http_client)
    response = requestor.request(
        "POST",
        "/users/login",
        service=DATABASE_SERVICE,
        json_body={"username": username, "password": password, "rememberMe": remember_me},
    )
    data = (response.data if response else None) or {}

    if data.get("requires_totp"):
        return PendingTOTP(
            options=options,
            requestor=requestor,
            temp_token=data["temp_token"],
            remember_me=bool(data.get("rememberMe", remember_me)),
        )

    jwt = _extract_token(data, endpoint="POST /users/login")
    authed_options = options.with_jwt(jwt)
    requestor._options = authed_options
    return TermixClient._with_options(authed_options, requestor)


async def login_async(
    *,
    base_url: str,
    username: str,
    password: str,
    remember_me: bool = False,
    service_urls: dict[str, str] | None = None,
    timeout: float = 30.0,
    verify: bool = True,
    max_network_retries: int = 2,
    default_headers: dict[str, str] | None = None,
    _http_client: Any = None,
) -> AsyncTermixClient | AsyncPendingTOTP:
    """Async mirror of `login()`."""
    from ._async_client import AsyncTermixClient

    options = ClientOptions.anonymous(
        base_url=base_url,
        service_urls=service_urls,
        timeout=timeout,
        verify=verify,
        max_network_retries=max_network_retries,
        default_headers=_merge_native_headers(default_headers),
    )
    requestor = AsyncAPIRequestor(options, http_client=_http_client)
    response = await requestor.request(
        "POST",
        "/users/login",
        service=DATABASE_SERVICE,
        json_body={"username": username, "password": password, "rememberMe": remember_me},
    )
    data = (response.data if response else None) or {}

    if data.get("requires_totp"):
        return AsyncPendingTOTP(
            options=options,
            requestor=requestor,
            temp_token=data["temp_token"],
            remember_me=bool(data.get("rememberMe", remember_me)),
        )

    jwt = _extract_token(data, endpoint="POST /users/login")
    authed_options = options.with_jwt(jwt)
    requestor._options = authed_options
    return AsyncTermixClient._with_options(authed_options, requestor)
