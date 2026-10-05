"""Pytest fixtures."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def allow_local_sockets(socket_enabled):
    """Simulátor PLC běží jako lokální TCP server."""
    yield
