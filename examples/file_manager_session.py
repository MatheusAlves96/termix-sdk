"""List a directory over an SSH-backed file manager session, using a
saved credential (rather than re-supplying raw SSH details). Requires
TERMIX_BASE_URL, TERMIX_API_KEY, and TERMIX_HOST_ID (an existing SSH
host's id) — see examples/README.md.
"""

from __future__ import annotations

import os

from termix_sdk import TermixClient, ssh_session


def main() -> None:
    base_url = os.environ["TERMIX_BASE_URL"]
    api_key = os.environ["TERMIX_API_KEY"]
    host_id = int(os.environ["TERMIX_HOST_ID"])

    with TermixClient(base_url=base_url, api_key=api_key) as client:
        host = client.hosts.retrieve(str(host_id))
        # `connect()`'s own parameters use the API's field names verbatim
        # (ip, port, username, authType, credentialId, ...) — see
        # FileManagerConnectParams. Reusing the host's saved credential
        # here rather than re-typing SSH details.
        with ssh_session(
            client.file_manager,
            host_id=host_id,
            ip=host.ip,
            port=host.port,
            username=host.username,
            authType=host.authType,
            credentialId=host.credentialId,
        ) as fm:
            for entry in fm.list_files(path="/"):
                print(entry)


if __name__ == "__main__":
    main()
