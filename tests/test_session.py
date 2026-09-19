from __future__ import annotations

import time

import pytest

from termix_sdk._session import SessionHandle, async_ssh_session, ssh_session
from termix_sdk.resources.docker import DockerService
from termix_sdk.resources.file_manager import AsyncFileManagerService, FileManagerService

from .http_client_mock import MockAsyncHTTPClient, MockHTTPClient


def _file_manager(mock_http_client: MockHTTPClient) -> FileManagerService:
    from termix_sdk._api_requestor import APIRequestor
    from termix_sdk._client_options import ClientOptions

    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    return FileManagerService(APIRequestor(options, http_client=mock_http_client))


def _async_file_manager(mock_async_http_client: MockAsyncHTTPClient) -> AsyncFileManagerService:
    from termix_sdk._api_requestor import AsyncAPIRequestor
    from termix_sdk._client_options import ClientOptions

    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    return AsyncFileManagerService(AsyncAPIRequestor(options, http_client=mock_async_http_client))


def test_session_connects_and_disconnects(mock_http_client: MockHTTPClient):
    fm = _file_manager(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"status": "connected"})  # connect
    mock_http_client.queue_response(status_code=200, body={"message": "ok"})  # list_files
    mock_http_client.queue_response(status_code=200, body={"message": "disconnected"})  # disconnect

    with ssh_session(fm, host_id=5) as session:
        assert isinstance(session, SessionHandle)
        session.list_files(path="/")

    connect_req, list_req, disconnect_req = mock_http_client.requests
    assert connect_req.url.endswith("/ssh/file_manager/ssh/connect")
    assert connect_req.json["hostId"] == 5
    assert "sessionId" in connect_req.json

    sid = connect_req.json["sessionId"]
    assert list_req.params["sessionId"] == sid
    assert disconnect_req.json["sessionId"] == sid


def test_session_disconnects_even_on_error(mock_http_client: MockHTTPClient):
    fm = _file_manager(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={"status": "connected"})
    mock_http_client.queue_response(status_code=200, body={"message": "disconnected"})

    with pytest.raises(RuntimeError):
        with ssh_session(fm, host_id=5) as _session:
            raise RuntimeError("boom")

    assert mock_http_client.requests[-1].url.endswith("/ssh/file_manager/ssh/disconnect")


def test_session_accepts_explicit_session_id(mock_http_client: MockHTTPClient):
    fm = _file_manager(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={})
    mock_http_client.queue_response(status_code=200, body={})

    with ssh_session(fm, host_id=5, session_id="fixed-sid") as session:
        assert session.session_id == "fixed-sid"

    assert mock_http_client.requests[0].json["sessionId"] == "fixed-sid"


def test_session_keepalive_pings_in_background(mock_http_client: MockHTTPClient):
    fm = _file_manager(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={})  # connect
    for _ in range(50):
        mock_http_client.queue_response(status_code=200, body={})  # keepalive pings
    mock_http_client.queue_response(status_code=200, body={})  # disconnect

    with ssh_session(fm, host_id=5, keepalive=True, keepalive_interval=0.01):
        time.sleep(0.3)  # let a few keepalive pings fire

    keepalive_calls = [
        r for r in mock_http_client.requests if r.url.endswith("/ssh/file_manager/ssh/keepalive")
    ]
    assert len(keepalive_calls) >= 1


def test_session_call_without_sessionid_field_is_harmless(mock_http_client: MockHTTPClient):
    # list_trash doesn't take a sessionId at all — the session handle
    # still injects one; it just rides along unused, per _session.py's
    # docstring.
    fm = _file_manager(mock_http_client)
    mock_http_client.queue_response(status_code=200, body={})
    mock_http_client.queue_response(status_code=200, body=[])
    mock_http_client.queue_response(status_code=200, body={})

    with ssh_session(fm, host_id=5) as session:
        session.list_trash()


@pytest.mark.asyncio
async def test_async_session_connects_and_disconnects(mock_async_http_client: MockAsyncHTTPClient):
    fm = _async_file_manager(mock_async_http_client)
    mock_async_http_client.queue_response(status_code=200, body={})
    mock_async_http_client.queue_response(status_code=200, body={"message": "ok"})
    mock_async_http_client.queue_response(status_code=200, body={})

    async with async_ssh_session(fm, host_id=7) as session:
        await session.list_files(path="/")

    connect_req, list_req, disconnect_req = mock_async_http_client.requests
    assert connect_req.json["hostId"] == 7
    sid = connect_req.json["sessionId"]
    assert list_req.params["sessionId"] == sid
    assert disconnect_req.json["sessionId"] == sid


@pytest.mark.asyncio
async def test_async_session_disconnects_on_error(mock_async_http_client: MockAsyncHTTPClient):
    fm = _async_file_manager(mock_async_http_client)
    mock_async_http_client.queue_response(status_code=200, body={})
    mock_async_http_client.queue_response(status_code=200, body={})

    with pytest.raises(RuntimeError):
        async with async_ssh_session(fm, host_id=7):
            raise RuntimeError("boom")

    assert mock_async_http_client.requests[-1].url.endswith("/ssh/file_manager/ssh/disconnect")


def test_session_works_with_docker_service(mock_http_client: MockHTTPClient):
    from termix_sdk._api_requestor import APIRequestor
    from termix_sdk._client_options import ClientOptions

    options = ClientOptions(base_url="http://gateway", api_key="tmx_test")
    docker = DockerService(APIRequestor(options, http_client=mock_http_client))

    mock_http_client.queue_response(status_code=200, body={})
    mock_http_client.queue_response(status_code=200, body=[])
    mock_http_client.queue_response(status_code=200, body={})

    with ssh_session(docker, host_id=1) as session:
        session.list_containers()

    assert mock_http_client.requests[0].url.endswith("/docker/ssh/connect")
    assert mock_http_client.requests[-1].url.endswith("/docker/ssh/disconnect")
