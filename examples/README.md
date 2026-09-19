# Examples

Each script expects a real, reachable Termix instance and reads its
connection details from environment variables — nothing here talks to a
mock. Set at least:

```bash
export TERMIX_BASE_URL="https://termix.example.com"
export TERMIX_API_KEY="tmx_..."          # sync_quickstart.py, async_quickstart.py, file_manager_session.py
export TERMIX_USERNAME="alice"           # login_with_totp.py
export TERMIX_PASSWORD="..."             # login_with_totp.py
```

| Script | Shows |
|---|---|
| [`sync_quickstart.py`](sync_quickstart.py) | `TermixClient`, listing hosts, error handling |
| [`async_quickstart.py`](async_quickstart.py) | `AsyncTermixClient`, the same thing with `asyncio` |
| [`login_with_totp.py`](login_with_totp.py) | `TermixClient.login()`, handling `PendingTOTP` |
| [`file_manager_session.py`](file_manager_session.py) | `ssh_session()` against `client.file_manager` |

Run any of them with `python examples/<script>.py`.
