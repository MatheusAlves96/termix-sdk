# Adapted from stripe-python (stripe/_stripe_client.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""AsyncTermixClient: the async entry point, kept as its own class rather
than `x_async()` methods on `TermixClient` (docs/sdk-plan.md section 2,
item 7). See `_client.py` for the sync twin this mirrors line for line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ._api_requestor import AsyncAPIRequestor
from ._client_options import ClientOptions
from ._http_client import AsyncHTTPClient
from ._request_options import RequestOptions
from ._response import TermixResponse

# --- generated resource imports start ---

from .resources import alerts as _alerts
from .resources import api_keys as _api_keys
from .resources import audit as _audit
from .resources import automations as _automations
from .resources import credentials as _credentials
from .resources import database as _database
from .resources import encryption as _encryption
from .resources import guacamole as _guacamole
from .resources import instance_settings as _instance_settings
from .resources import network_topology as _network_topology
from .resources import open_tabs as _open_tabs
from .resources import preferences as _preferences
from .resources import rbac as _rbac
from .resources import session_logs as _session_logs
from .resources import session_sharing as _session_sharing
from .resources import snippets as _snippets
from .resources import sso as _sso
from .resources import sync as _sync
from .resources import system as _system
from .resources import tailscale as _tailscale
from .resources import termix_id as _termix_id
from .resources import tunnel_presets as _tunnel_presets
from .resources import user_admin as _user_admin
from .resources import users as _users
from .resources import vault as _vault
from .resources import webauthn as _webauthn
from .resources import workspaces as _workspaces

# --- generated resource imports end ---

if TYPE_CHECKING:
    from ._auth import AsyncPendingTOTP


class AsyncTermixClient:
    """
    Example:
        >>> client = AsyncTermixClient(base_url="https://termix.example.com", api_key="tmx_...")
        >>> await client.request("GET", "/health")
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        jwt: str | None = None,
        service_urls: dict[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        _http_client: AsyncHTTPClient | None = None,
    ) -> None:
        self._options = ClientOptions(
            base_url=base_url,
            service_urls=service_urls,
            api_key=api_key,
            jwt=jwt,
            timeout=timeout,
            verify=verify,
            max_network_retries=max_network_retries,
            default_headers=default_headers,
        )
        self._requestor = AsyncAPIRequestor(self._options, http_client=_http_client)

        # --- generated resource attributes start ---

        self.alerts = _alerts.AsyncAlertsService(self._requestor)
        self.api_keys = _api_keys.AsyncApiKeysService(self._requestor)
        self.audit = _audit.AsyncAuditService(self._requestor)
        self.automations = _automations.AsyncAutomationsService(self._requestor)
        self.credentials = _credentials.AsyncCredentialsService(self._requestor)
        self.database = _database.AsyncDatabaseService(self._requestor)
        self.encryption = _encryption.AsyncEncryptionService(self._requestor)
        self.guacamole = _guacamole.AsyncGuacamoleService(self._requestor)
        self.instance_settings = _instance_settings.AsyncInstanceSettingsService(self._requestor)
        self.network_topology = _network_topology.AsyncNetworkTopologyService(self._requestor)
        self.open_tabs = _open_tabs.AsyncOpenTabsService(self._requestor)
        self.preferences = _preferences.AsyncPreferencesService(self._requestor)
        self.rbac = _rbac.AsyncRbacService(self._requestor)
        self.session_logs = _session_logs.AsyncSessionLogsService(self._requestor)
        self.session_sharing = _session_sharing.AsyncSessionSharingService(self._requestor)
        self.snippets = _snippets.AsyncSnippetsService(self._requestor)
        self.sso = _sso.AsyncSsoService(self._requestor)
        self.sync = _sync.AsyncSyncService(self._requestor)
        self.system = _system.AsyncSystemService(self._requestor)
        self.tailscale = _tailscale.AsyncTailscaleService(self._requestor)
        self.termix_id = _termix_id.AsyncTermixIdService(self._requestor)
        self.tunnel_presets = _tunnel_presets.AsyncTunnelPresetsService(self._requestor)
        self.user_admin = _user_admin.AsyncUserAdminService(self._requestor)
        self.users = _users.AsyncUsersService(self._requestor)
        self.vault = _vault.AsyncVaultService(self._requestor)
        self.webauthn = _webauthn.AsyncWebauthnService(self._requestor)
        self.workspaces = _workspaces.AsyncWorkspacesService(self._requestor)

        # --- generated resource attributes end ---

    @classmethod
    def _with_options(
        cls, options: ClientOptions, requestor: AsyncAPIRequestor
    ) -> AsyncTermixClient:
        instance = cls.__new__(cls)
        instance._options = options
        instance._requestor = requestor
        return instance

    @classmethod
    async def login(
        cls,
        *,
        base_url: str,
        username: str,
        password: str,
        remember_me: bool = False,
        service_urls: dict[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        max_network_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        _http_client: AsyncHTTPClient | None = None,
    ) -> AsyncTermixClient | AsyncPendingTOTP:
        """Async mirror of `TermixClient.login()` — see its docstring and
        `_auth.py`.
        """
        from ._auth import login_async

        return await login_async(
            base_url=base_url,
            username=username,
            password=password,
            remember_me=remember_me,
            service_urls=service_urls,
            timeout=timeout,
            verify=verify,
            max_network_retries=max_network_retries,
            default_headers=default_headers,
            _http_client=_http_client,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        service: str | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        files: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> TermixResponse | None:
        return await self._requestor.request(
            method,
            path,
            service=service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    async def close(self) -> None:
        await self._requestor.close()

    async def __aenter__(self) -> AsyncTermixClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
