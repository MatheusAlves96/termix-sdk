from __future__ import annotations

from termix_sdk._util import logfmt, looks_secret, redact_headers, redact_mapping, redact_value


def test_looks_secret_matches_known_suffixes():
    names = ("password", "sudoPassword", "autostartKeyPassword", "apiKey", "token", "tempToken")
    for name in names:
        assert looks_secret(name), name


def test_looks_secret_false_for_normal_fields():
    for name in ("username", "ip", "port", "name"):
        assert not looks_secret(name), name


def test_redact_value_only_redacts_strings():
    assert redact_value("password", "s3cr3t") == "<redacted>"
    assert redact_value("password", None) is None
    assert redact_value("username", "alice") == "alice"


def test_redact_headers_masks_auth_and_cookie():
    raw = {"Authorization": "Bearer x", "Cookie": "jwt=y", "Content-Type": "application/json"}
    headers = redact_headers(raw)
    assert headers["Authorization"] == "<redacted>"
    assert headers["Cookie"] == "<redacted>"
    assert headers["Content-Type"] == "application/json"


def test_redact_mapping_shallow():
    data = redact_mapping({"username": "alice", "auth": {"password": "s3cr3t", "ok": True}})
    assert data["username"] == "alice"
    assert data["auth"]["password"] == "<redacted>"
    assert data["auth"]["ok"] is True


def test_logfmt_redacts_and_quotes():
    line = logfmt({"method": "POST", "password": "s3cr3t", "url": "http://x/y z"})
    assert "s3cr3t" not in line
    assert 'url="http://x/y z"' in line
