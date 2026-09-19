"""Username/password login, handling the TOTP second factor if the
account has one enabled. Requires TERMIX_BASE_URL, TERMIX_USERNAME,
TERMIX_PASSWORD — see examples/README.md.
"""

from __future__ import annotations

import os
import sys

from termix_sdk import PendingTOTP, TermixClient


def main() -> None:
    base_url = os.environ["TERMIX_BASE_URL"]
    username = os.environ["TERMIX_USERNAME"]
    password = os.environ["TERMIX_PASSWORD"]

    result = TermixClient.login(base_url=base_url, username=username, password=password)

    if isinstance(result, PendingTOTP):
        code = input("6-digit TOTP code: ").strip()
        client = result.verify(code)
    else:
        client = result

    me = client.users.get_me()
    print(f"Logged in as {me.username} (admin={me.is_admin})")
    client.close()


if __name__ == "__main__":
    sys.exit(main())
