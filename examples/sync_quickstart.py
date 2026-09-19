"""List every SSH host, and show typed-error handling on a lookup that
doesn't exist. Requires TERMIX_BASE_URL and TERMIX_API_KEY — see
examples/README.md.
"""

from __future__ import annotations

import os

from termix_sdk import NotFoundError, TermixClient


def main() -> None:
    base_url = os.environ["TERMIX_BASE_URL"]
    api_key = os.environ["TERMIX_API_KEY"]

    with TermixClient(base_url=base_url, api_key=api_key) as client:
        hosts = client.hosts.list()
        if not hosts:
            print("No hosts yet.")
        for host in hosts:
            print(f"{host.id:>4}  {host.name or '(unnamed)':<30} {host.ip}:{host.port}")

        try:
            client.hosts.retrieve("999999999")
        except NotFoundError as e:
            print(f"\nLookup of a made-up host id failed as expected: {e}")


if __name__ == "__main__":
    main()
