"""Kenneth French Data Library factors (FF3 + momentum, daily and monthly) and FRED DTB3.

Raw files are saved as downloaded; ``parse_french_csv`` turns one into a tidy DataFrame
(used by the ETL in Phase 2). Values in French files are percent; we keep them as published
and convert in the ETL.
"""
from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from quantagents.data.download.base import HttpClient, Manifest

log = logging.getLogger(__name__)

FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRENCH_FILES = {
    "ff3_daily": "F-F_Research_Data_Factors_daily_CSV.zip",
    "ff3_monthly": "F-F_Research_Data_Factors_CSV.zip",
    "mom_daily": "F-F_Momentum_Factor_daily_CSV.zip",
    "mom_monthly": "F-F_Momentum_Factor_CSV.zip",
}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def parse_french_csv(zip_bytes: bytes) -> pd.DataFrame:
    """First data block of a French CSV zip -> DataFrame indexed by date (daily or month-end)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith(",") and any(c.isalpha() for c in l))
    header = [h.strip() for h in lines[start].split(",")]
    header[0] = "date"
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if not parts[0].isdigit():
            break  # end of first block (annual block or copyright follows)
        rows.append(parts)
    df = pd.DataFrame(rows, columns=header[:len(rows[0])])
    fmt = "%Y%m%d" if len(df["date"].iloc[0]) == 8 else "%Y%m"
    df["date"] = pd.to_datetime(df["date"], format=fmt)
    if fmt == "%Y%m":
        df["date"] = df["date"] + pd.offsets.MonthEnd(0)
    return df.set_index("date").apply(pd.to_numeric, errors="coerce")


@dataclass
class FrenchFactors:
    raw_dir: Path
    manifest: Manifest
    http: HttpClient
    name: str = "french"

    @classmethod
    def create(cls, raw_dir: Path, manifest: Manifest) -> "FrenchFactors":
        return cls(raw_dir, manifest, HttpClient(1.0, headers={"User-Agent": "QuantAgents-research/0.1"}))

    def download(self) -> list[Path]:
        out = []
        for key, fname in FRENCH_FILES.items():
            path = self.raw_dir / "factors" / "french" / fname
            if not self.manifest.is_complete(path):
                content = self.http.get(FRENCH_BASE + fname).content
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                self.manifest.record("factors", path, len(parse_french_csv(content)), {"key": key})
            out.append(path)
        return out


@dataclass
class FredRiskFree:
    raw_dir: Path
    manifest: Manifest
    http: HttpClient
    series: str = "DTB3"
    name: str = "fred"

    @classmethod
    def create(cls, raw_dir: Path, manifest: Manifest) -> "FredRiskFree":
        return cls(raw_dir, manifest, HttpClient(1.0, headers={"User-Agent": "QuantAgents-research/0.1"}))

    def download(self, start: date, end: date) -> Path:
        path = self.raw_dir / "riskfree" / f"{self.series}.csv"
        if self._covers(path, start, end):
            return path
        text = self.http.get(FRED_URL, params={"id": self.series, "cosd": start.isoformat(),
                                               "coed": end.isoformat()}).text
        df = pd.read_csv(io.StringIO(text))
        if df.shape[1] < 2:
            raise ValueError("unexpected FRED response")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.manifest.record("riskfree", path, len(df), {"series": self.series, "start": str(start),
                                                          "end": str(end)})
        return path

    def _covers(self, path: Path, start: date, end: date) -> bool:
        """Complete AND downloaded for at least this date range. A file saved for the 3-month
        pilot window must not count as the full series (found 12 Nov: DTB3 stopped in July 2015)."""
        if not self.manifest.is_complete(path):
            return False
        e = self.manifest.entry(path)
        return (e is not None and "start" in e.params and "end" in e.params
                and e.params["start"] <= str(start) and e.params["end"] >= str(end))
