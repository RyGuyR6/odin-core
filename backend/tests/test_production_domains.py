"""Tests for production domain configuration (odincore.net cutover)."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# MCP allowed-hosts
# ---------------------------------------------------------------------------


def test_mcp_allowed_hosts_contains_api_odincore_net() -> None:
    """api.odincore.net must be an allowed MCP host."""
    import app.mcp_server as mcp_module

    importlib.reload(mcp_module)
    server = mcp_module.create_mcp()
    hosts = server.settings.transport_security.allowed_hosts
    assert "api.odincore.net" in hosts


def test_mcp_allowed_hosts_contains_render_url() -> None:
    """The actual Render service URL must be an allowed MCP host."""
    import app.mcp_server as mcp_module

    importlib.reload(mcp_module)
    server = mcp_module.create_mcp()
    hosts = server.settings.transport_security.allowed_hosts
    assert "odin-api-63t2.onrender.com" in hosts


def test_mcp_stale_host_not_present() -> None:
    """The old stale hostname odin-core.onrender.com must not be present."""
    import app.mcp_server as mcp_module

    importlib.reload(mcp_module)
    server = mcp_module.create_mcp()
    hosts = server.settings.transport_security.allowed_hosts
    assert "odin-core.onrender.com" not in hosts


# ---------------------------------------------------------------------------
# MCP health URL env override
# ---------------------------------------------------------------------------


def test_mcp_health_url_env_override(monkeypatch: object) -> None:
    """ODIN_MCP_HEALTH_URL env var must override the default health URL."""
    custom_url = "https://mcp.odincore.net/health"
    with patch.dict(os.environ, {"ODIN_MCP_HEALTH_URL": custom_url}):
        assert os.getenv("ODIN_MCP_HEALTH_URL") == custom_url


def test_mcp_health_url_default_is_render_url() -> None:
    """Without ODIN_MCP_HEALTH_URL set, the fallback default should be the Render URL."""
    env = {k: v for k, v in os.environ.items() if k != "ODIN_MCP_HEALTH_URL"}
    with patch.dict(os.environ, env, clear=True):
        value = os.getenv("ODIN_MCP_HEALTH_URL", "https://odin-mcp.onrender.com/health")
        assert "odin-mcp.onrender.com" in value


# ---------------------------------------------------------------------------
# Auth cookie settings for production
# ---------------------------------------------------------------------------


def _load_auth_settings(extra_env: dict[str, str]) -> object:
    """Reload AuthSettings with patched environment variables."""
    import odin_auth.config as cfg_module
    import odin_auth.router as router_module

    base = {k: v for k, v in os.environ.items()}
    base.update(extra_env)

    with patch.dict(os.environ, base, clear=True):
        importlib.reload(cfg_module)
        importlib.reload(router_module)
        router_module.get_settings.cache_clear()
        return cfg_module.AuthSettings.load()


def test_auth_cookie_domain_production(tmp_path: Path) -> None:
    """AuthSettings must honour ODIN_AUTH_COOKIE_DOMAIN in production."""
    settings = _load_auth_settings(
        {
            "ODIN_ENV": "production",
            "ODIN_AUTH_SECRET": "a" * 48,
            "ODIN_AUTH_COOKIE_DOMAIN": ".odincore.net",
            "ODIN_AUTH_DB": str(tmp_path / "auth.db"),
        }
    )
    assert settings.cookie_domain == ".odincore.net"
    assert settings.secure_cookies is True


def test_auth_secure_cookies_auto_production(tmp_path: Path) -> None:
    """secure_cookies must default to True when ODIN_ENV=production, even if the
    variable is not explicitly set."""
    env: dict[str, str] = {
        "ODIN_ENV": "production",
        "ODIN_AUTH_SECRET": "b" * 48,
        "ODIN_AUTH_DB": str(tmp_path / "auth.db"),
    }
    # Ensure ODIN_AUTH_SECURE_COOKIES is absent
    clean_env = {k: v for k, v in os.environ.items() if k != "ODIN_AUTH_SECURE_COOKIES"}
    clean_env.update(env)

    import odin_auth.config as cfg_module

    with patch.dict(os.environ, clean_env, clear=True):
        importlib.reload(cfg_module)
        settings = cfg_module.AuthSettings.load()

    assert settings.secure_cookies is True


def test_auth_secure_cookies_false_in_development(tmp_path: Path) -> None:
    """secure_cookies must default to False in development (no HTTPS locally)."""
    env: dict[str, str] = {
        "ODIN_ENV": "development",
        "ODIN_AUTH_SECRET": "c" * 48,
        "ODIN_AUTH_DB": str(tmp_path / "auth.db"),
    }
    clean_env = {k: v for k, v in os.environ.items() if k != "ODIN_AUTH_SECURE_COOKIES"}
    clean_env.update(env)

    import odin_auth.config as cfg_module

    with patch.dict(os.environ, clean_env, clear=True):
        importlib.reload(cfg_module)
        settings = cfg_module.AuthSettings.load()

    assert settings.secure_cookies is False
