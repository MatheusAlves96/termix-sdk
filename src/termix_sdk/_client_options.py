# Adapted from stripe-python (stripe/_client_options.py and
# stripe/_requestor_options.py), MIT License, Copyright (c) 2010-2018 Stripe.
# See NOTICE for the full license text.
"""Connection-level options: how to reach Termix and authenticate.

Termix is not one server behind one base URL. Its 8 backend services each
listen on their own port; in production a reverse proxy (nginx, in the
project's own docker image) puts them all behind one origin by routing on
path prefix. `base_url` should point at that proxy. `service_urls` lets a
caller bypass it per service — useful in dev/Electron, where each service is
reachable directly on localhost. See docs/sdk-plan.md section 1 and 2.
"""

from __future__ import annotations


class ClientOptions:
    base_url: str
    service_urls: dict[str, str]
    api_key: str | None
    jwt: str | None
    timeout: float
    verify: bool
    max_network_retries: int
    default_headers: dict[str, str]

    def __init__(
        self,
        *,
        base_url: str,
        service_urls: dict[str, str] | None = None,
        api_key: str | None = None,
        jwt: str | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if api_key is None and jwt is None:
            raise ValueError(
                "TermixClient needs either api_key (a 'tmx_...' API key, the "
                "recommended way) or jwt (a bearer token obtained via "
                "TermixClient.login(...) or TOTP verification)."
            )
        if api_key is not None and jwt is not None:
            raise ValueError(
                "Pass only one of api_key or jwt, not both — the SDK sends "
                "whichever one wins as the sole Authorization: Bearer value."
            )

        self.base_url = base_url.rstrip("/")
        self.service_urls = {k: v.rstrip("/") for k, v in (service_urls or {}).items()}
        self.api_key = api_key
        self.jwt = jwt
        self.timeout = timeout
        self.verify = verify
        self.max_network_retries = max_network_retries
        self.default_headers = dict(default_headers or {})

    @property
    def bearer_token(self) -> str:
        """The value sent as `Authorization: Bearer <...>`.

        Never both: `__init__` already rejected passing both `api_key` and
        `jwt`, so exactly one of them is set here.
        """
        token = self.api_key if self.api_key is not None else self.jwt
        assert token is not None  # guaranteed by __init__
        return token

    def base_url_for(self, service: str | None) -> str:
        if service and service in self.service_urls:
            return self.service_urls[service]
        return self.base_url

    def with_jwt(self, jwt: str) -> ClientOptions:
        """Return a copy of these options authenticated with a fresh JWT.

        Used by `TermixClient.login()`/`.verify_totp()` to swap in the token
        obtained from the login flow without touching `api_key`.
        """
        return ClientOptions(
            base_url=self.base_url,
            service_urls=dict(self.service_urls),
            jwt=jwt,
            timeout=self.timeout,
            verify=self.verify,
            max_network_retries=self.max_network_retries,
            default_headers=dict(self.default_headers),
        )
