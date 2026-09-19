"""Same thing as sync_quickstart.py, with AsyncTermixClient. Requires
TERMIX_BASE_URL and TERMIX_API_KEY — see examples/README.md.
"""

from __future__ import annotations

import asyncio
import os

from termix_sdk import AsyncTermixClient


async def main() -> None:
    base_url = os.environ["TERMIX_BASE_URL"]
    api_key = os.environ["TERMIX_API_KEY"]

    async with AsyncTermixClient(base_url=base_url, api_key=api_key) as client:
        hosts, snippets = await asyncio.gather(
            client.hosts.list(),
            client.snippets.list(),
        )
        print(f"{len(hosts)} host(s), {len(snippets)} snippet(s)")
        for host in hosts:
            print(f"  {host.name} ({host.ip}:{host.port})")


if __name__ == "__main__":
    asyncio.run(main())
