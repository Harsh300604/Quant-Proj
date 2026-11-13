"""Markdown to Word (.docx) with the standard library only (no python-docx, no pandoc). NO network.

    python -m quantagents.eval.md_docx docs/proto20_student_guide.md out/proto20_student_guide.docx

Covers what our docs use: headings, paragraphs, bullet and numbered lists (nested by indent), tables,
code blocks, block quotes, **bold**, _italic_, `code` and [links](url) (the link text is kept, the URL
follows in brackets). Images are not embedded.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
TEXT_WIDTH = 9360  # twips: A4/Letter with 1-inch margins

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '</Types>')
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
    'Target="docProps/core.xml"/>'
    '</Relationships>')
DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>')


def _style(sid: str, name: str, ppr: str = "", rpr: str = "", based: str = "Normal") -> str:
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>'
            f'<w:next w:val="Normal"/><w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


STYLES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
    '<w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" '
    'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _style("Heading1", "heading 1", '<w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/>',
             '<w:b/><w:color w:val="1F3864"/><w:sz w:val="34"/>')
    + _style("Heading2", "heading 2", '<w:keepNext/><w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="1"/>',
             '<w:b/><w:color w:val="2F5496"/><w:sz w:val="28"/>')
    + _style("Heading3", "heading 3", '<w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="2"/>',
             '<w:b/><w:color w:val="2F5496"/><w:sz w:val="24"/>')
    + _style("Code", "Code", '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:shd w:val="clear" w:fill="F2F2F2"/>',
             '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="18"/>')
    + _style("Quote", "Quote", '<w:ind w:left="567"/>', '<w:i/><w:color w:val="404040"/>')
    + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
    + "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>'
              for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    + '</w:tblBorders><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
    '</w:tblPr></w:style></w:styles>')

INLINE = re.compile(r"(\*\*[^*]+?\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|(?<![\w*])\*(?!\s)[^*]+?(?<!\s)\*(?![\w*])"
                    r"|(?<!\w)_(?!\s)[^_]+?(?<!\s)_(?!\w))")
BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _run(text: str, bold=False, italic=False, code=False, size: int | None = None) -> str:
    if not text:
        return ""
    rpr = ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "")
    if code:
        rpr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:shd w:val="clear" w:fill="F2F2F2"/>'
    if size:
        rpr += f'<w:sz w:val="{size}"/>'
    text = BAD_XML.sub("", text)
    return f'<w:r>{f"<w:rPr>{rpr}</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def inline(text: str, bold=False, size: int | None = None) -> str:
    """Runs for one line of markdown text: **bold**, *italic* / _italic_, `code`, [text](url)."""
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(inline(part[2:-2], bold=True, size=size))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(_run(part[1:-1], bold=bold, code=True, size=size))
        elif part.startswith("[") and "](" in part:
            label, url = part[1:-1].split("](", 1)
            out.append(inline(label, bold=bold, size=size))
            if not url.startswith("#") and label != url:
                out.append(_run(f" ({url})", bold=bold, size=size))
        elif len(part) > 2 and part[0] == part[-1] and part[0] in "*_":
            out.append(_run(part[1:-1], bold=bold, italic=True, size=size))
        else:
            out.append(_run(part, bold=bold, size=size))
    return "".join(out)


def _para(runs: str, style: str | None = None, ppr: str = "") -> str:
    p = (f'<w:pStyle w:val="{style}"/>' if style else "") + ppr
    return f'<w:p>{f"<w:pPr>{p}</w:pPr>" if p else ""}{runs}</w:p>'


def _cells(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


NO_SPACE = '<w:spacing w:after="0"/>'


def _table(rows: list[list[str]]) -> str:
    n = max(len(r) for r in rows)
    col = TEXT_WIDTH // n
    size = 18 if n >= 6 else 20
    grid = "".join(f'<w:gridCol w:w="{col}"/>' for _ in range(n))
    trs = []
    for i, r in enumerate(rows):
        r = r + [""] * (n - len(r))
        shade = '<w:shd w:val="clear" w:fill="DCE6F2"/>' if i == 0 else ""
        tcs = "".join(f'<w:tc><w:tcPr><w:tcW w:w="{col}" w:type="dxa"/>{shade}</w:tcPr>'
                      f'{_para(inline(c, bold=i == 0, size=size), ppr=NO_SPACE)}</w:tc>' for c in r)
        trs.append(f'<w:tr>{"<w:trPr><w:tblHeader/></w:trPr>" if i == 0 else ""}{tcs}</w:tr>')
    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{col * n}" w:type="dxa"/>'
            f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>'
            + _para(""))


LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def body_xml(md: str) -> str:
    """The <w:body> content for a markdown text."""
    lines = md.replace("\r\n", "\n").split("\n")
    out, i, buf = [], 0, []

    def flush():
        if buf:
            out.append(_para(inline(" ".join(s.strip() for s in buf))))
            buf.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                out.append(_para(_run(lines[i].rstrip() or " ", code=False), style="Code"))
                i += 1
            out.append(_para(""))
        elif not s:
            flush()
        elif re.match(r"^#{1,6}\s", s):
            flush()
            level = min(len(s) - len(s.lstrip("#")), 3)
            out.append(_para(inline(s.lstrip("#").strip()), style=f"Heading{level}"))
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _cells(lines[i])
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                out.append(_table(rows))
            continue
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            flush()
        elif s.startswith(">"):
            flush()
            out.append(_para(inline(s.lstrip("> ").strip()), style="Quote"))
        elif LIST_ITEM.match(line):
            flush()
            m = LIST_ITEM.match(line)
            level = min(len(m.group(1).expandtabs(4)) // 2, 4)
            text = m.group(3)
            while i + 1 < len(lines) and lines[i + 1].strip() and not LIST_ITEM.match(lines[i + 1]) \
                    and not lines[i + 1].strip().startswith(("|", "#", "```", ">")) and lines[i + 1].startswith(" "):
                i += 1
                text += " " + lines[i].strip()
            mark = "•" if m.group(2) in "-*+" else m.group(2)
            left = 360 * (level + 1)
            out.append(_para(_run(f"{mark}\t") + inline(text),
                             ppr=f'<w:tabs><w:tab w:val="left" w:pos="{left}"/></w:tabs>'
                                 f'<w:spacing w:after="60"/><w:ind w:left="{left}" w:hanging="360"/>'))
        else:
            buf.append(line)
        i += 1
    flush()
    return "".join(out)


def md_to_docx(md: str, out_path: Path, title: str = "") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1273" w:bottom="1440" '
            'w:left="1273" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
           f'{body_xml(md)}{sect}</w:body></w:document>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{escape(title)}</dc:title></cp:coreProperties>')
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("docProps/core.xml", core)
    return out_path


def convert(src: Path, out: Path) -> Path:
    md = Path(src).read_text(encoding="utf-8")
    first = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), Path(src).stem)
    return md_to_docx(md, out, title=first)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    args = ap.parse_args(argv)
    print(f"written: {convert(Path(args.src), Path(args.out))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
