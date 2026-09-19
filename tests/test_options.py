from __future__ import annotations

import pytest

from termix_sdk._client_options import ClientOptions
from termix_sdk._request_options import ADMIN_TARGET_USER_HEADER, request_headers


def test_requires_exactly_one_credential():
    with pytest.raises(ValueError, match="needs either"):
        ClientOptions(base_url="http://x")
    with pytest.raises(ValueError, match="only one"):
        ClientOptions(base_url="http://x", api_key="tmx_a", jwt="jwt_b")


def test_api_key_wins_as_bearer_token():
    opts = ClientOptions(base_url="http://x", api_key="tmx_abc")
    assert opts.bearer_token == "tmx_abc"


def test_jwt_used_as_bearer_token():
    opts = ClientOptions(base_url="http://x", jwt="jwt_abc")
    assert opts.bearer_token == "jwt_abc"


def test_base_url_stripped_of_trailing_slash():
    opts = ClientOptions(base_url="http://x/", api_key="tmx_a")
    assert opts.base_url == "http://x"


def test_service_urls_override_base_url():
    opts = ClientOptions(
        base_url="http://gateway",
        service_urls={"metrics": "http://localhost:30005/"},
        api_key="tmx_a",
    )
    assert opts.base_url_for("metrics") == "http://localhost:30005"
    assert opts.base_url_for("docker") == "http://gateway"
    assert opts.base_url_for(None) == "http://gateway"


def test_anonymous_options_have_no_bearer_token():
    opts = ClientOptions.anonymous(base_url="http://x")
    assert opts.bearer_token is None


def test_anonymous_options_with_jwt_becomes_a_real_credential():
    anon = ClientOptions.anonymous(base_url="http://x")
    authed = anon.with_jwt("jwt_fresh")
    assert authed.bearer_token == "jwt_fresh"


def test_with_jwt_returns_new_options_without_mutating_original():
    opts = ClientOptions(base_url="http://x", api_key="tmx_a")
    swapped = opts.with_jwt("jwt_fresh")
    assert swapped.bearer_token == "jwt_fresh"
    assert opts.bearer_token == "tmx_a"


def test_request_headers_empty_without_options():
    assert request_headers(None) == {}


def test_request_headers_includes_impersonation():
    headers = request_headers({"impersonate_user": "alice"})
    assert headers[ADMIN_TARGET_USER_HEADER] == "alice"


def test_request_headers_merges_custom_headers():
    headers = request_headers({"headers": {"X-Custom": "1"}, "impersonate_user": "bob"})
    assert headers["X-Custom"] == "1"
    assert headers[ADMIN_TARGET_USER_HEADER] == "bob"
