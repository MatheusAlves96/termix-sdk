# Adapted from stripe-python (stripe/_stripe_client.py), MIT License,
# Copyright (c) 2010-2018 Stripe. See NOTICE for the full license text.
"""TermixClient: the sync entry point.

Resource attributes (`client.hosts`, `client.credentials`, ...) are not
here yet — they're wired in by `tools/sdk-gen` once the resource-map exists
(docs/sdk-plan.md phases F3/F4). Everything below is the F1 core: options,
the requestor, a generic low-level `request()` escape hatch, and lifecycle
(`close()`/context manager).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any

from ._api_requestor import APIRequestor
from ._client_options import ClientOptions
from ._http_client import HTTPClient
from ._request_options import RequestOptions
from ._response import TermixResponse

# --- generated resource imports start ---

from .resources import ai as _ai
from .resources import alerts as _alerts
from .resources import api_keys as _api_keys
from .resources import audit as _audit
from .resources import automations as _automations
from .resources import credentials as _credentials
from .resources import dashboard as _dashboard
from .resources import database as _database
from .resources import docker as _docker
from .resources import encryption as _encryption
from .resources import file_manager as _file_manager
from .resources import fleets as _fleets
from .resources import guacamole as _guacamole
from .resources import homepage as _homepage
from .resources import host_file_manager as _host_file_manager
from .resources import hosts as _hosts
from .resources import instance_settings as _instance_settings
from .resources import metrics as _metrics
from .resources import network_topology as _network_topology
from .resources import open_tabs as _open_tabs
from .resources import preferences as _preferences
from .resources import proxmox as _proxmox
from .resources import proxmox_stats as _proxmox_stats
from .resources import rbac as _rbac
from .resources import session_logs as _session_logs
from .resources import session_sharing as _session_sharing
from .resources import snippets as _snippets
from .resources import sso as _sso
from .resources import sync as _sync
from .resources import system as _system
from .resources import tailscale as _tailscale
from .resources import terminal as _terminal
from .resources import termix_id as _termix_id
from .resources import tmux as _tmux
from .resources import tunnel as _tunnel
from .resources import tunnel_presets as _tunnel_presets
from .resources import user_admin as _user_admin
from .resources import users as _users
from .resources import vault as _vault
from .resources import webauthn as _webauthn
from .resources import workspaces as _workspaces

# --- generated resource imports end ---

if TYPE_CHECKING:
    from ._auth import PendingTOTP


class TermixClient:
    """
    Example:
        >>> client = TermixClient(base_url="https://termix.example.com", api_key="tmx_...")
        >>> client.request("GET", "/health")
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
        _http_client: HTTPClient | None = None,
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
        self._requestor = APIRequestor(self._options, http_client=_http_client)

        # --- generated resource attributes start ---

        self.ai = _ai.AiService(self._requestor)
        self.alerts = _alerts.AlertsService(self._requestor)
        self.api_keys = _api_keys.ApiKeysService(self._requestor)
        self.audit = _audit.AuditService(self._requestor)
        self.automations = _automations.AutomationsService(self._requestor)
        self.credentials = _credentials.CredentialsService(self._requestor)
        self.dashboard = _dashboard.DashboardService(self._requestor)
        self.database = _database.DatabaseService(self._requestor)
        self.docker = _docker.DockerService(self._requestor)
        self.encryption = _encryption.EncryptionService(self._requestor)
        self.file_manager = _file_manager.FileManagerService(self._requestor)
        self.fleets = _fleets.FleetsService(self._requestor)
        self.guacamole = _guacamole.GuacamoleService(self._requestor)
        self.homepage = _homepage.HomepageService(self._requestor)
        self.host_file_manager = _host_file_manager.HostFileManagerService(self._requestor)
        self.hosts = _hosts.HostsService(self._requestor)
        self.instance_settings = _instance_settings.InstanceSettingsService(self._requestor)
        self.metrics = _metrics.MetricsService(self._requestor)
        self.network_topology = _network_topology.NetworkTopologyService(self._requestor)
        self.open_tabs = _open_tabs.OpenTabsService(self._requestor)
        self.preferences = _preferences.PreferencesService(self._requestor)
        self.proxmox = _proxmox.ProxmoxService(self._requestor)
        self.proxmox_stats = _proxmox_stats.ProxmoxStatsService(self._requestor)
        self.rbac = _rbac.RbacService(self._requestor)
        self.session_logs = _session_logs.SessionLogsService(self._requestor)
        self.session_sharing = _session_sharing.SessionSharingService(self._requestor)
        self.snippets = _snippets.SnippetsService(self._requestor)
        self.sso = _sso.SsoService(self._requestor)
        self.sync = _sync.SyncService(self._requestor)
        self.system = _system.SystemService(self._requestor)
        self.tailscale = _tailscale.TailscaleService(self._requestor)
        self.terminal = _terminal.TerminalService(self._requestor)
        self.termix_id = _termix_id.TermixIdService(self._requestor)
        self.tmux = _tmux.TmuxService(self._requestor)
        self.tunnel = _tunnel.TunnelService(self._requestor)
        self.tunnel_presets = _tunnel_presets.TunnelPresetsService(self._requestor)
        self.user_admin = _user_admin.UserAdminService(self._requestor)
        self.users = _users.UsersService(self._requestor)
        self.vault = _vault.VaultService(self._requestor)
        self.webauthn = _webauthn.WebauthnService(self._requestor)
        self.workspaces = _workspaces.WorkspacesService(self._requestor)

        # --- generated resource attributes end ---

    @classmethod
    def _with_options(cls, options: ClientOptions, requestor: APIRequestor) -> TermixClient:
        """Build a client that shares an existing requestor — used by
        `login()`/TOTP verification (F2) to return a new, JWT-authenticated
        client without re-parsing constructor arguments.
        """
        instance = cls.__new__(cls)
        instance._options = options
        instance._requestor = requestor
        return instance

    @classmethod
    def login(
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
        _http_client: HTTPClient | None = None,
    ) -> TermixClient | PendingTOTP:
        """`POST /users/login`. Returns a ready, JWT-authenticated
        `TermixClient` — or, if the account has TOTP enabled and this
        device isn't already trusted, a `PendingTOTP`: call
        `.verify(code)` on it with the 6-digit code to get the client.
        See `_auth.py` for why this always behaves like a native app
        request under the hood.
        """
        from ._auth import login as _login

        return _login(
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

    def request(
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
        """Low-level escape hatch: call any endpoint the generated resources
        don't cover yet, or that was deliberately left out of the SDK's
        surface (docs/sdk-plan.md section 2, item 10).
        """
        return self._requestor.request(
            method,
            path,
            service=service,
            query=query,
            json_body=json_body,
            files=files,
            options=options,
        )

    def close(self) -> None:
        self._requestor.close()

    def __enter__(self) -> TermixClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
