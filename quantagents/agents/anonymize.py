"""Names-hidden control (brief section 9, D44): everything the LLMs see uses stable aliases instead of
tickers and company names, so the model cannot simply recall how a famous company did.

- Aliases: "X001", "X002", ... (shown as "Company X001"), numbered in company-id order the first
  time a company appears in the run and saved in runs/<run_id>/aliases.json, so they stay the
  same on every date.
- Scrubbed: every ticker of every company in the run (whole words, case-sensitive), the company
  names and their short forms ("Apple Inc." -> also "Apple"), and the extra brands, products and
  executives in reference/name_aliases.csv (case-insensitive, whole words).
- The LLMs' answers come back with aliases; Python maps them to the real companies.

This is a best-effort control: sector, size, figures and news content can still identify a
mega-cap (D44: reported as a weak control). Dates are kept (filings and news need them).

    python -m quantagents.agents.anonymize --scan --run-id pilot_enh_hidden_dev
scans every saved LLM input of a run (runs/<run_id>/llm_inputs/) for real names and tickers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from quantagents.config import REPO_ROOT

SUFFIXES = (", Inc.", " Inc.", " Inc", " Corporation", " Corp.", " Holdings", " Holding", " Systems", " Group",
            " plc", " N.V.", " Ltd", " US", ".com", " Co.")


def name_forms(name: str) -> set[str]:
    forms = {name.strip()}
    core = name.strip()
    changed = True
    while changed:
        changed = False
        for s in SUFFIXES:
            if core.endswith(s) and len(core) > len(s) + 2:
                core = core[: -len(s)].strip(" ,")
                changed = True
    forms.add(core)
    return {f for f in forms if len(f) >= 3}


def extra_names(path: Path = REPO_ROOT / "reference" / "name_aliases.csv") -> dict[str, list[str]]:
    if not path.exists():
        return {}
    d = pd.read_csv(path)
    return {c: list(g["alias"]) for c, g in d.groupby("company_id")}


class Anonymizer:
    def __init__(self, companies: dict[str, dict], aliases: dict[str, str] | None = None,
                 extras: dict[str, list[str]] | None = None):
        """``companies``: {company_id: {"name": str, "tickers": [str, ...]}} for every company in the run."""
        self.companies = companies
        self.aliases = dict(aliases or {})
        for c in sorted(companies):
            if c not in self.aliases:
                self.aliases[c] = f"X{len(self.aliases) + 1:03d}"
        self.reverse = {a: c for c, a in self.aliases.items()}
        extras = extra_names() if extras is None else extras
        tick, names = [], []
        for c, info in companies.items():
            a = self.aliases[c]
            for t in {c, *info.get("tickers", [])}:
                if t:
                    tick.append((t, a))
            for f in name_forms(info.get("name") or c) | set(extras.get(c, [])):
                names.append((f, f"Company {a}"))
        # longest first so "Amazon.com" is replaced before "Amazon"
        self._names = sorted(names, key=lambda x: -len(x[0]))
        self._ticks = sorted(tick, key=lambda x: -len(x[0]))
        self._name_re = [(re.compile(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", re.IGNORECASE), r) for n, r in self._names]
        self._tick_re = [(re.compile(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])"), a) for t, a in self._ticks]

    def scrub(self, text: str) -> str:
        for rx, rep in self._name_re:
            text = rx.sub(rep, text)
        for rx, rep in self._tick_re:
            text = rx.sub(rep, text)
        return text

    def real_id(self, shown: str) -> str:
        s = str(shown).strip().upper()
        if s.startswith("COMPANY "):
            s = s[len("COMPANY "):]
        return self.reverse.get(s, s)

    def leaks(self, text: str) -> list[str]:
        """Real names or tickers still present in ``text`` (empty = clean)."""
        found = [n for (n, _), (rx, _) in zip(self._names, self._name_re) if rx.search(text)]
        found += [t for (t, _), (rx, _) in zip(self._ticks, self._tick_re) if rx.search(text)]
        return sorted(set(found))


def for_run(gw, as_of, companies: list[str], run_dir: Path) -> Anonymizer:
    """The run's anonymizer: company names and tickers from the store, aliases persisted in the run folder."""
    u = gw.get_universe(as_of).set_index("company_id")
    info = {}
    for c in companies:
        tk = str(u["tickers"].get(c, c) or c)
        info[c] = {"name": str(u["name"].get(c, c) or c), "tickers": [t.strip() for t in tk.split(",") if t.strip()]}
    f = Path(run_dir) / "aliases.json"
    saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    an = Anonymizer(info, saved)
    if an.aliases != saved:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(an.aliases, indent=2, sort_keys=True), encoding="utf-8")
    return an


def scan_run(run_dir: Path, gw) -> tuple[int, int, dict[str, list[str]]]:
    """(files scanned, files with leaks, {file: leaked names}) over runs/<id>/llm_inputs/."""
    run_dir = Path(run_dir)
    aliases = json.loads((run_dir / "aliases.json").read_text(encoding="utf-8"))
    u = gw.con.execute("SELECT company_id, name, tickers FROM companies").df().set_index("company_id")
    info = {c: {"name": str(u["name"].get(c, c)), "tickers": [t for t in str(u["tickers"].get(c, c)).split(",") if t]}
            for c in aliases}
    an = Anonymizer(info, aliases)
    files = sorted((run_dir / "llm_inputs").rglob("*.txt"))
    bad = {}
    for p in files:
        hits = an.leaks(p.read_text(encoding="utf-8"))
        if hits:
            bad[str(p.relative_to(run_dir))] = hits
    return len(files), len(bad), bad


def main(argv: list[str] | None = None) -> int:
    from quantagents.config import CONFIG_DIR, load_config
    from quantagents.data.gateway import Gateway
    from quantagents.paths import Paths
    ap = argparse.ArgumentParser(description="Scan a names-hidden run's LLM inputs for real names")
    ap.add_argument("--scan", action="store_true", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    paths = Paths.from_config(load_config(args.config))
    gw = Gateway(paths.duckdb_file)
    try:
        n, nbad, bad = scan_run(paths.runs / args.run_id, gw)
    finally:
        gw.close()
    sys.stdout.reconfigure(encoding="utf-8")
    for f, hits in list(bad.items())[:20]:
        print(f"  {f}: {', '.join(hits[:8])}")
    share = (n - nbad) / n if n else 0.0
    print(f"{nbad} files with real names found; {share:.0%} of {n} LLM inputs are clean")
    return 0 if nbad == 0 and n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
