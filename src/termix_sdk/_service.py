# Adapted from stripe-python (stripe/_stripe_service.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""Base class every generated resource module subclasses.

A generated method looks roughly like:

    def retrieve(self, id: int, *, options: RequestOptions | None = None) -> Host:
        response = self._request("GET", f"/host/db/host/{id}", options=options)
        return Host.construct_from(response.data if response else None, last_response=response)

`_request`/`_request_stream` do not convert the response into a model —
that's the generated method's job, since only it knows which model class
the endpoint's 200 response maps to (see docs/sdk-plan.md section 8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, ClassVar

from ._api_requestor import APIRequestor, AsyncAPIRequestor
from ._request_options import RequestOptions
from ._response import AsyncTermixStreamResponse, SSEEvent, TermixResponse, TermixStreamResponse


class TermixService:
    # Overridden by every generated subclass with the Termix backend
    # service (and therefore base URL) its paths live on — "database",
    # "metrics", "file-manager", etc. `None` is only valid for a subclass
    # that itself has no directly-requestable paths (a pure grouping class).
    service: ClassVar[str | None] = None

    def __init__(self, requestor: APIRequestor) -> None:
        self._requestor = requestor

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        files: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> TermixResponse | None:
        return self._requestor.request(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    def _request_stream(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        options: RequestOptions | None = None,
    ) -> TermixStreamResponse:
        return self._requestor.request_stream(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            options=options,
        )

    def _request_sse(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        options: RequestOptions | None = None,
    ) -> Iterator[SSEEvent]:
        return self._requestor.request_sse(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            options=options,
        )


class AsyncTermixService:
    service: ClassVar[str | None] = None

    def __init__(self, requestor: AsyncAPIRequestor) -> None:
        self._requestor = requestor

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        files: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> TermixResponse | None:
        return await self._requestor.request(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    async def _request_stream(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        options: RequestOptions | None = None,
    ) -> AsyncTermixStreamResponse:
        return await self._requestor.request_stream(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            options=options,
        )

    async def _request_sse(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        options: RequestOptions | None = None,
    ) -> AsyncIterator[SSEEvent]:
        return await self._requestor.request_sse(
            method,
            path,
            service=self.service,
            query=query,
            json_body=json_body,
            options=options,
        )
