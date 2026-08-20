import socket

import pytest

from app.main import BenchmarkRequest, _public_addresses


def test_benchmark_request_rejects_whitespace_host():
    with pytest.raises(ValueError):
        BenchmarkRequest(host="bad host")


def test_public_addresses_reject_private_literal():
    with pytest.raises(Exception):
        _public_addresses("127.0.0.1")


def test_public_addresses_reject_private_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))],
    )
    with pytest.raises(Exception):
        _public_addresses("internal.example")
