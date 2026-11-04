import os

import pytest

from quantagents.config import CONFIG_DIR, load_config
from quantagents.paths import (
    ForbiddenDriveError, Paths, assert_not_forbidden, configure_third_party_caches, drive_of,
)


@pytest.mark.parametrize("p, d", [
    (r"C:\Users\me\data", "C:"), ("c:/temp", "C:"), (r"D:\CreatED-Quant\qa_store", "D:"),
    ("D:/CreatED-Quant", "D:"), ("/mnt/c/Users", "C:"), ("/mnt/d/x", "D:"), ("/home/user", ""),
    ("/mnt/data/x", ""),
])
def test_drive_of(p, d):
    assert drive_of(p) == d


@pytest.mark.parametrize("p", [r"C:\anything", "c:/x", "/mnt/c/x", r"C:\Users\me\AppData\Local\Temp"])
def test_c_drive_rejected(p):
    with pytest.raises(ForbiddenDriveError, match="must not use"):
        assert_not_forbidden(p)


def test_storage_root_on_c_rejected(monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", r"C:\qa_store")
    with pytest.raises(ForbiddenDriveError):
        Paths.from_config(load_config(CONFIG_DIR / "base.yaml"))


def test_default_root_is_d():
    cfg = load_config(CONFIG_DIR / "base.yaml")
    assert drive_of(cfg.storage.root) == "D:"


def test_paths_resolve_under_root(store):
    paths = Paths.from_config(load_config(CONFIG_DIR / "base.yaml")).ensure()
    for d in paths.all_dirs():
        assert d.is_dir() and str(d).startswith(str(store))
    assert paths.response_cache.parent == paths.cache


def test_third_party_caches_redirected(store, monkeypatch):
    monkeypatch.setenv("TEMP", r"C:\Users\me\AppData\Local\Temp")
    for v in ("MPLCONFIGDIR", "NUMBA_CACHE_DIR"):
        monkeypatch.delenv(v, raising=False)
    paths = Paths.from_config(load_config(CONFIG_DIR / "base.yaml"))
    configure_third_party_caches(paths)
    assert os.environ["TEMP"] == str(paths.tmp)
    assert os.environ["MPLCONFIGDIR"].startswith(str(store))
    assert os.environ["NUMBA_CACHE_DIR"].startswith(str(store))
