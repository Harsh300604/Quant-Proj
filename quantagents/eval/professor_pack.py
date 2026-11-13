"""The professor pack (proto20 P7): everything to present the prototype, from stored runs. NO LLM calls.

    python -m quantagents.eval.professor_pack

Writes to <storage>/reports/<name>/ (default name proto20):
- results.md, results.csv, growth_of_1.html / .svg, active_return.svg (via eval/report.py);
- architecture.svg: the pipeline of one monthly rebalance;
- sample_transcript_<run>_<date>.md: one committee meeting without the long briefing and memos;
- Word versions (.docx) of the summary, the student guide and the problems log;
- README.md: what each file is.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from quantagents.config import CONFIG_DIR, load_config
from quantagents.eval import report
from quantagents.eval.md_docx import convert
from quantagents.paths import Paths

REPO = Path(__file__).resolve().parents[2]
RUNS = ["proto20_paper_baseline", "proto20_paper_enhanced", "proto20_paper_enh_hidden"]
SAMPLE = ("proto20_paper_enhanced", "2022-06-01")
DOCS = ["docs/proto20_summary.md", "docs/proto20_student_guide.md", "docs/proto20_problems_log.md"]

# (label, detail, kind): kind "py" = Python (no AI), "ai" = an LLM call, "data" = stored data
STEPS = [
    ("Point-in-time data gateway", "prices, filings, news up to the decision time only", "data"),
    ("20 research memos", "one per company; small model, 4 in parallel", "ai"),
    ("Briefing", "simulated trading, risk table, track record (Python numbers)", "py"),
    ("Emily", "news and fundamentals", "ai"),
    ("Bob", "quantitative signals and simulated trading", "ai"),
    ("Dave", "risk control", "ai"),
    ("Otto drafts", "a view for every company", "ai"),
    ("Draft check", "weights, rules and trading cost of the draft", "py"),
    ("Otto decides", "final view (and rating + confidence in the enhanced version)", "ai"),
    ("Optimizer", "baseline: multipliers; enhanced: Black-Litterman with a risk budget; then the rules", "py"),
    ("Trading simulator", "trade at the next open, 0.1% cost, daily value", "py"),
    ("Evaluation", "metrics, bootstrap intervals, Carhart alpha, red flags", "py"),
]
FILL = {"py": ("#e8f1fb", "#2f6fb3"), "ai": ("#fbeee4", "#c4682b"), "data": ("#eef5ee", "#2e8b57")}


def architecture_svg() -> str:
    w, box_h, gap, top = 640, 44, 14, 64
    h = top + len(STEPS) * (box_h + gap) + 48
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
             "<style>text{font:12px Calibri,Arial,sans-serif;fill:#222}.t{font-size:16px;font-weight:bold}"
             ".d{fill:#555;font-size:11px}</style>",
             '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<text x="20" y="28" class="t">One monthly rebalance (the same for every month)</text>',
             '<defs><marker id="a" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" '
             'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#888"/></marker></defs>']
    for i, (kind, txt) in enumerate((("data", "stored data"), ("ai", "AI call (LLM)"), ("py", "Python, no AI"))):
        fill, stroke = FILL[kind]
        parts.append(f'<rect x="{20 + i * 150}" y="40" width="14" height="12" fill="{fill}" stroke="{stroke}"/>'
                     f'<text x="{40 + i * 150}" y="50" class="d">{txt}</text>')
    for i, (lab, detail, kind) in enumerate(STEPS):
        y = top + i * (box_h + gap)
        fill, stroke = FILL[kind]
        parts.append(f'<rect x="20" y="{y}" width="{w - 40}" height="{box_h}" rx="6" fill="{fill}" stroke="{stroke}"/>'
                     f'<text x="34" y="{y + 19}"><tspan font-weight="bold">{html.escape(lab)}</tspan></text>'
                     f'<text x="34" y="{y + 35}" class="d">{html.escape(detail)}</text>')
        if i < len(STEPS) - 1:
            parts.append(f'<line x1="{w / 2}" x2="{w / 2}" y1="{y + box_h}" y2="{y + box_h + gap - 2}" '
                         'stroke="#888" stroke-width="1.5" marker-end="url(#a)"/>')
    parts.append(f'<text x="20" y="{h - 30}" class="d">Committee members share one prompt-cached briefing and one '
                 f'answer format.</text><text x="20" y="{h - 14}" class="d">Every answer is checked against a schema; '
                 'Python does all the maths.</text></svg>')
    return "".join(parts)


def sample_transcript(text: str, run: str, date: str) -> str:
    """The meeting itself: the decision table and the five calls, without the briefing and the memos."""
    cut = text.find("\n## Shared briefing")
    head = text if cut < 0 else text[:cut]
    note = (f"_Sample from run `{run}`, meeting of {date}. The shared briefing (Python's numbers and the 20 memo "
            "summaries) and the memos are left out here; they are in the full transcript in the run folder._\n\n")
    return note + head.rstrip() + "\n"


README = """# proto20 professor pack

Made from stored runs by `python -m quantagents.eval.professor_pack`; no AI calls.

| file | what it is |
|---|---|
| proto20_summary.docx | the one-document summary (from docs/proto20_summary.md) |
| results.md / results.csv | every number: returns, risk, active metrics with 90% intervals, Carhart alpha, ENT/ENB, view accuracy |
| growth_of_1.svg / growth_of_1.html | growth of $1 for the three runs, the benchmark, QQQ and ^NDX |
| active_return.svg | each run's cumulative return relative to the benchmark (the committee's real contribution) |
| architecture.svg | the steps of one monthly rebalance |
| {sample} | one committee meeting: what each member was asked and answered |
| proto20_student_guide.docx | the plain-language guide |
| proto20_problems_log.docx | every problem we found and how we solved it |

The SVG files open in any browser and can be inserted into Word or PowerPoint (Insert > Pictures).
"""


def build(runs=None, name: str = "proto20", sample=SAMPLE, cfg_path=None) -> Path:
    runs = runs or RUNS
    cfg = load_config(cfg_path or CONFIG_DIR / "base.yaml")
    paths = Paths.from_config(cfg)
    out = report.build(runs, name, cfg_path)
    (out / "architecture.svg").write_text(architecture_svg(), encoding="utf-8")
    run, date = sample
    src = paths.runs / run / "transcripts" / f"{date}.md"
    sample_name = f"sample_transcript_{run}_{date}.md"
    (out / sample_name).write_text(sample_transcript(src.read_text(encoding="utf-8"), run, date), encoding="utf-8")
    for doc in DOCS:
        p = REPO / doc
        if p.exists():
            convert(p, out / (p.stem + ".docx"))
    (out / "README.md").write_text(README.format(sample=sample_name), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", default=RUNS)
    ap.add_argument("--name", default="proto20")
    ap.add_argument("--sample", nargs=2, metavar=("RUN", "DATE"), default=list(SAMPLE))
    ap.add_argument("--config")
    args = ap.parse_args(argv)
    out = build(args.runs, args.name, tuple(args.sample), args.config)
    for f in sorted(out.iterdir()):
        print(f"{f.name:60s} {f.stat().st_size:>9,d} bytes")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
