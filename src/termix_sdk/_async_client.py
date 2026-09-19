# Adapted from stripe-python (stripe/_stripe_client.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""AsyncTermixClient: the async entry point, kept as its own class rather
than `x_async()` methods on `TermixClient` (docs/sdk-plan.md section 2,
item 7). See `_client.py` for the sync twin this mirrors line for line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._api_requestor import AsyncAPIRequestor
from ._client_options import ClientOptions
from ._http_client import AsyncHTTPClient
from ._request_options import RequestOptions
from ._response import TermixResponse


class AsyncTermixClient:
    """
    Example:
        >>> client = AsyncTermixClient(base_url="https://termix.example.com", api_key="tmx_...")
        >>> await client.request("GET", "/health")
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        jwt: str | None = None,
        service_urls: dict[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        _http_client: AsyncHTTPClient | None = None,
    ) -> None:
        self._options = ClientOptions(
            base_url=base_url,
            service_urls=service_urls,
            api_key=api_key,
            jwt=jwt,
            timeout=timeout,
            verify=verify,
            max_network_retries=max_network_retries,
            default_headers=default_headers,
        )
        self._requestor = AsyncAPIRequestor(self._options, http_client=_http_client)

        # --- generated resource attributes start ---
        # tools/sdk-gen fills this region with one attribute per resource
        # module (self.hosts = resources.hosts.AsyncHostsService(self._requestor),
        # etc.) once tools/sdk-gen/config/resource-map.json exists. Left
        # empty until then — see docs/sdk-plan.md phases F3/F4/F7.
        # --- generated resource attributes end ---

    @classmethod
    def _with_options(
        cls, options: ClientOptions, requestor: AsyncAPIRequestor
    ) -> AsyncTermixClient:
        instance = cls.__new__(cls)
        instance._options = options
        instance._requestor = requestor
        return instance

    async def request(
        self,
        method: str,
        path: str,
        *,
        service: str | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        files: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> TermixResponse | None:
        return await self._requestor.request(
            method,
            path,
            service=service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    async def close(self) -> None:
        await self._requestor.close()

    async def __aenter__(self) -> AsyncTermixClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
