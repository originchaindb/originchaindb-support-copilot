import socket

import pytest

from scripts.smoke_live import require_cloud_origin
from support_copilot.config import CopilotError


def test_cloud_verification_rejects_plain_http_before_connecting():
    with pytest.raises(CopilotError, match="HTTPS"):
        require_cloud_origin("http://127.0.0.1:19419")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.2", "::1"])
def test_cloud_verification_rejects_private_dns_results(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", (address, 443))])
    with pytest.raises(CopilotError, match="loopback/private"):
        require_cloud_origin("https://fixture.example")


def test_cloud_verification_accepts_public_https_dns(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", ("1.1.1.1", 443))]
    )
    require_cloud_origin("https://fixture.example")
