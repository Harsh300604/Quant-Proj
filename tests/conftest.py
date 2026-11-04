"""Shared test fixtures. Tests never touch the network or the real storage root."""
from __future__ import annotations

import socket

import pytest

from quantagents.data.download import base


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """Every test gets its own empty storage root."""
    root = tmp_path / "qa_store"
    monkeypatch.setenv("QA_STORE_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(base.RateLimiter, "wait", lambda self: None)
    monkeypatch.setattr(base.HttpClient, "_sleep", lambda self, a, r: None)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Block real sockets; HTTP is mocked with the `responses` library."""
    def guard(*a, **k):
        raise RuntimeError("network access is not allowed in tests")
    monkeypatch.setattr(socket.socket, "connect", guard)
