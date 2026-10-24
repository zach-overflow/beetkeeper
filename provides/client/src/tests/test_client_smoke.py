"""Smoke tests proving Pants generates an importable `beetkeeper_api_client` from `provides/client/src/openapi.json`."""

import pytest

from beetkeeper_api_client import ApiClient, Configuration, MonitoringApi


def test_api_client_targets_configured_host() -> None:
    api_client = ApiClient(Configuration(host="http://beetkeeper.test"))
    assert api_client.configuration.host == "http://beetkeeper.test"


@pytest.mark.parametrize("method_name", ["health_api_health_get", "health_api_health_get_sync"])
def test_monitoring_api_exposes_async_and_sync_methods(method_name: str) -> None:
    assert callable(getattr(MonitoringApi, method_name))
