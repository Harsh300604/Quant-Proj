"""P7: the professor pack pieces (no LLM, no network): Word writer, standalone SVGs, sample transcript."""
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from quantagents.eval.md_docx import body_xml, inline, md_to_docx
from quantagents.eval.professor_pack import STEPS, architecture_svg, sample_transcript
from quantagents.eval.report import standalone_svg

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MD = """# Title & more

Intro with **bold**, _italic_, `code` and [a link](https://example.org).
Second line of the same paragraph.

## Section

| a | b |
|---|---:|
| 1 | **2** |
| x \\| y | <3 |

- first
- second item
  continues here
   - nested
1. numbered

```text
code  line
```

> a quote
"""


def _doc(tmp_path, md=MD):
    p = md_to_docx(md, tmp_path / "t.docx", title="T")
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        root = ET.fromstring(z.read("word/document.xml"))
        ET.fromstring(z.read("word/styles.xml"))
    return names, root


def test_docx_is_a_valid_package(tmp_path):
    names, root = _doc(tmp_path)
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"} <= names
    styles = [e.get(f"{W}val") for e in root.iter(f"{W}pStyle")]
    assert "Heading1" in styles and "Heading2" in styles and "Code" in styles and "Quote" in styles


def test_docx_keeps_text_tables_and_lists(tmp_path):
    _, root = _doc(tmp_path)
    text = "".join(t.text or "" for t in root.iter(f"{W}t"))
    assert "Title & more" in text
    assert "Second line of the same paragraph" in text  # joined into the intro paragraph
    assert "a link (https://example.org)" in text
    assert "x | y" in text and "<3" in text
    assert "continues here" in text and "code  line" in text
    tbl = list(root.iter(f"{W}tbl"))
    assert len(tbl) == 1 and len(list(tbl[0].iter(f"{W}tr"))) == 3  # separator row dropped
    assert "**" not in text and "`" not in text


def test_inline_bold_italic_code():
    x = inline("a **b** _c_ `d`")
    assert "<w:b/>" in x and "<w:i/>" in x and "Consolas" in x
    assert "snake_case_name" in "".join(ET.fromstring(f'<p xmlns:w="x">{inline("snake_case_name")}</p>').itertext())


def test_body_has_no_control_characters():
    assert "\x07" not in body_xml("bell \x07 here")


def test_standalone_svg_parses_and_has_legend():
    idx = pd.bdate_range("2021-01-04", periods=50)
    lines = {"A": pd.Series(range(50), index=idx, dtype=float) / 50 + 1,
             "B & C": pd.Series(1.0, index=idx)}
    svg = standalone_svg(lines, {"A": "#000", "B & C": "#f00"}, "Title", ylabel=lambda v: f"{v:+.1%}")
    root = ET.fromstring(svg)
    texts = " ".join(root.itertext())
    assert "Title" in texts and "B & C" in texts and "%" in texts
    assert root.get("xmlns") is None and root.tag.endswith("svg")


def test_architecture_svg_lists_every_step():
    root = ET.fromstring(architecture_svg())
    texts = " ".join(root.itertext())
    assert all(lab in texts for lab, _, _ in STEPS)


def test_sample_transcript_drops_briefing_and_memos():
    t = "# Committee meeting\n\n## Decision\nrow\n\n## Meetings\nx\n\n## Shared briefing (cached)\nlong\n\n## Research memos\nm\n"
    s = sample_transcript(t, "run1", "2022-06-01")
    assert "## Decision" in s and "## Meetings" in s
    assert "long" not in s and "Research memos" not in s and "run1" in s
