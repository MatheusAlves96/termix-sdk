"""Exercises the F3 pilot's generated modules (system, credentials)
through the real client, end to end — none of the other test files touch
generated code at all. See docs/sdk-plan.md phase F3 and
tools/sdk-gen/generate.py.
"""

from __future__ import annotations

import pytest

from termix_sdk._client import TermixClient
from termix_sdk.models.credentials import CredentialsCreateResult, CredentialsDeleteResult
from termix_sdk.models.system import SystemHealthResult

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


def test_system_health(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    result = client.system.health()
    assert isinstance(result, SystemHealthResult)
    assert result.status == "ok"
    assert mock_http_client.requests[0].method == "GET"
    assert mock_http_client.requests[0].url.endswith("/health")


def test_system_version_sends_query_param(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body={"localVersion": "1.0", "status": "x"})
    client.system.version(checkRemote="true")
    assert mock_http_client.requests[0].params == {"checkRemote": "true"}


def test_credentials_list(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body=[{"id": 1}, {"id": 2}])
    result = client.credentials.list()
    assert result == [{"id": 1}, {"id": 2}]
    assert mock_http_client.requests[0].url.endswith("/credentials")


def test_credentials_create_sends_json_body(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=201, body={"id": 5, "name": "prod-key"})
    result = client.credentials.create(name="prod-key", authType="key")
    assert isinstance(result, CredentialsCreateResult)
    assert mock_http_client.requests[0].json == {"name": "prod-key", "authType": "key"}


def test_credentials_retrieve_substitutes_path_param(
    client: TermixClient, mock_http_client: MockHTTPClient
):
    mock_http_client.queue_response(status_code=200, body={"id": 5, "name": "prod-key"})
    client.credentials.retrieve("5")
    assert mock_http_client.requests[0].url.endswith("/credentials/5")


def test_credentials_update_sends_body_with_id_in_path(
    client: TermixClient, mock_http_client: MockHTTPClient
):
    mock_http_client.queue_response(status_code=200, body={"id": 5, "name": "renamed"})
    client.credentials.update("5", name="renamed")
    sent = mock_http_client.requests[0]
    assert sent.url.endswith("/credentials/5")
    assert sent.method == "PUT"
    assert sent.json == {"name": "renamed"}


def test_credentials_delete(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(
        status_code=200, body={"message": "Credential deleted successfully"}
    )
    result = client.credentials.delete("5")
    assert isinstance(result, CredentialsDeleteResult)
    assert result.message == "Credential deleted successfully"
    assert mock_http_client.requests[0].method == "DELETE"


def test_credentials_apply_to_host_two_path_params_no_body(
    client: TermixClient, mock_http_client: MockHTTPClient
):
    mock_http_client.queue_response(
        status_code=200, body={"message": "Credential applied to host successfully"}
    )
    client.credentials.apply_to_host("5", "9")
    sent = mock_http_client.requests[0]
    assert sent.url.endswith("/credentials/5/apply-to-host/9")
    assert sent.json is None


def test_credentials_hosts_subresource_list(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body=[{"id": 1}])
    result = client.credentials.hosts("5")
    assert result == [{"id": 1}]
    assert mock_http_client.requests[0].url.endswith("/credentials/5/hosts")


def test_generated_call_carries_auth_header(client: TermixClient, mock_http_client: MockHTTPClient):
    mock_http_client.queue_response(status_code=200, body={"status": "ok"})
    client.system.health()
    assert mock_http_client.requests[0].headers["Authorization"] == "Bearer tmx_test_key"


@pytest.mark.asyncio
async def test_async_credentials_retrieve(
    async_client, mock_async_http_client: MockAsyncHTTPClient
):
    mock_async_http_client.queue_response(status_code=200, body={"id": 7, "name": "x"})
    result = await async_client.credentials.retrieve("7")
    assert result.id == 7
    assert mock_async_http_client.requests[0].url.endswith("/credentials/7")
