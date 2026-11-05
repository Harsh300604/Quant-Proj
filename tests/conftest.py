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


@pytest.fixture(scope="session")
def synthetic_db(tmp_path_factory):
    """Synthetic raw store (tests/fixtures/synthetic_store.py) built into DuckDB once per session.

    Returns (root, db_path, build_at): ``build_at(cutoff)`` builds the same store as if today
    were ``cutoff`` (all later data removed) - used by the "no future influence" leak test."""
    import os
    from tests.fixtures.synthetic_store import build_raw_store
    from quantagents.data.etl import build
    root = tmp_path_factory.mktemp("synthetic_store")
    build_raw_store(root)
    old = os.environ.get("QA_STORE_ROOT")
    os.environ["QA_STORE_ROOT"] = str(root)
    try:
        db = build()
    finally:
        if old is None:
            os.environ.pop("QA_STORE_ROOT", None)
        else:
            os.environ["QA_STORE_ROOT"] = old
    cache = {}

    def build_at(cutoff):
        key = str(cutoff)
        if key not in cache:
            current = os.environ.get("QA_STORE_ROOT")
            os.environ["QA_STORE_ROOT"] = str(root)
            try:
                cache[key] = build(out=root / f"cut_{len(cache)}.duckdb", cutoff_utc=cutoff)
            finally:
                if current is None:
                    os.environ.pop("QA_STORE_ROOT", None)
                else:
                    os.environ["QA_STORE_ROOT"] = current
        return cache[key]
    return root, db, build_at
