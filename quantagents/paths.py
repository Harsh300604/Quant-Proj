"""Every storage location the project uses, derived from config.

Rule: nothing is ever written to the C: drive. ``Paths`` refuses a storage root on C:,
and ``configure_third_party_caches`` points library caches (yfinance, matplotlib, numba)
at folders under the storage root instead of their defaults in the user profile on C:.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from quantagents.config import Config

FORBIDDEN_DRIVES = {"C:"}


class ForbiddenDriveError(RuntimeError):
    pass


def drive_of(path: str | os.PathLike) -> str:
    """Windows drive letter of a path ('C:', 'D:'), or '' if none.

    Also recognises WSL-style '/mnt/c/...' paths.
    """
    s = str(path).replace("\\", "/")
    low = s.lower()
    if low.startswith("/mnt/") and len(low) >= 6 and low[5].isalpha() \
            and (len(low) == 6 or low[6] == "/"):
        return low[5].upper() + ":"
    return PureWindowsPath(s).drive.upper()


def assert_not_forbidden(path: str | os.PathLike, what: str = "path") -> None:
    d = drive_of(path)
    if d in FORBIDDEN_DRIVES:
        raise ForbiddenDriveError(
            f"{what} {str(path)!r} is on {d}, which this project must not use. "
            f"Use a folder on D: (e.g. D:\\CreatED-Quant\\qa_store).")


def storage_root(cfg: Config) -> Path:
    root = os.environ.get("QA_STORE_ROOT") or cfg.storage.root
    assert_not_forbidden(root, "storage root")
    if sys.platform == "win32" and drive_of(root) == "":
        raise ForbiddenDriveError(
            f"storage root {root!r} has no drive letter; on Windows give a full D:\\ path")
    return Path(root)


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def from_config(cls, cfg: Config) -> "Paths":
        return cls(storage_root(cfg))

    # Downloads (raw, as received) and user-supplied files
    @property
    def raw(self) -> Path: return self.root / "raw"
    @property
    def manual_prices(self) -> Path: return self.root / "manual_prices"
    @property
    def derived(self) -> Path: return self.root / "derived"
    @property
    def duckdb_file(self) -> Path: return self.root / "quantagents.duckdb"
    # LLM response cache and cost ledger
    @property
    def cache(self) -> Path: return self.root / "cache"
    @property
    def response_cache(self) -> Path: return self.cache / "responses.sqlite"
    @property
    def ledger(self) -> Path: return self.cache / "ledger.sqlite"
    # Outputs
    @property
    def runs(self) -> Path: return self.root / "runs"
    @property
    def reports(self) -> Path: return self.root / "reports"
    @property
    def logs(self) -> Path: return self.root / "logs"
    @property
    def tmp(self) -> Path: return self.root / "tmp"
    # Third-party caches redirected off C:
    @property
    def lib_cache(self) -> Path: return self.root / "lib-cache"

    def all_dirs(self) -> list[Path]:
        return [self.raw, self.manual_prices, self.derived, self.cache, self.runs,
                self.reports, self.logs, self.tmp, self.lib_cache]

    def ensure(self) -> "Paths":
        for d in self.all_dirs():
            assert_not_forbidden(d)
            d.mkdir(parents=True, exist_ok=True)
        return self


def configure_third_party_caches(paths: Paths) -> None:
    """Point library caches and temp files at the storage root (this process only)."""
    lib = paths.lib_cache
    for sub in ("yfinance", "matplotlib", "numba"):
        (lib / sub).mkdir(parents=True, exist_ok=True)
    paths.tmp.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(lib / "matplotlib"))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(lib / "numba"))
    for var in ("TMP", "TEMP", "TMPDIR"):
        current = os.environ.get(var)
        if not current or drive_of(current) in FORBIDDEN_DRIVES:
            os.environ[var] = str(paths.tmp)
    import tempfile
    tempfile.tempdir = None  # re-read TMP/TEMP on next use
    try:
        import yfinance as yf
        yf.set_tz_cache_location(str(lib / "yfinance"))
        if hasattr(yf, "cache") and hasattr(yf.cache, "set_cache_location"):
            yf.cache.set_cache_location(str(lib / "yfinance"))
    except Exception:  # yfinance not installed or API changed: never fatal here
        pass
