"""Write the comparison of the feature list workbook with its previous version, as a workbook and a PDF.

Words removed since the previous version are struck through in red, words added are underlined in blue.
The PDF is printed from an HTML page by Chrome or Edge.
"""

import difflib
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = {"ID": 7, "Feature": 30, "Actor": 24, "Acceptance criteria": 80, "Workflow": 11, "Owner": 20, "Change": 10}
KINDS = ("Main", "Rule", "Exception")
REMOVED = "C00000"
ADDED = "1F4E9E"
HEADER_FILL = "14233A"
BROWSERS = [
    "chrome",
    "msedge",
    "google-chrome",
    "chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
PAGE_COLUMN_WIDTHS = ["4%", "17%", "12%", "45%", "6%", "9%", "7%"]
PAGE_STYLE = """
@page { size: A4 landscape; margin: 10mm; }
body { font: 9pt Calibri, Arial, sans-serif; }
h1 { font-size: 13pt; margin: 0 0 4px; }
p { margin: 0 0 8px; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th { background: #14233A; color: #fff; text-align: left; }
th, td { border: 1px solid #bbb; padding: 3px 4px; vertical-align: top; }
tr { break-inside: avoid; }
del { color: #C00000; }
ins { color: #1F4E9E; text-decoration: underline; }
"""


def read_rows(path):
    """The rows of a feature list workbook in the six columns of BM04, by feature ID.

    Version 1.0 has Main, Rule and Exception columns and a Flow column instead.
    """
    sheet = load_workbook(path).active
    rows = list(sheet.iter_rows(values_only=True))
    header = list(rows[0])
    result = {}
    for values in rows[1:]:
        cell = dict(zip(header, values))
        if "Acceptance criteria" in cell:
            acceptance = cell["Acceptance criteria"]
        else:
            acceptance = " ".join(f"{kind}: {cell[kind]}" for kind in KINDS)
        result[cell["ID"]] = (
            cell["ID"],
            cell["Feature"],
            cell["Actor"],
            acceptance,
            cell.get("Workflow", cell.get("Flow")),
            cell.get("Owner"),
        )
    return result


def word_diff(old, new):
    """The parts of a cell as (kind, text), kind being equal, removed or added, compared word by word."""
    old_words = re.findall(r"\S+\s*", old or "")
    new_words = re.findall(r"\S+\s*", new or "")
    parts = []
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append(("equal", "".join(old_words[i1:i2])))
            continue
        if i2 > i1:
            parts.append(("removed", "".join(old_words[i1:i2])))
        if j2 > j1:
            parts.append(("added", "".join(new_words[j1:j2])))
    return parts


def compare(previous, current):
    """Each feature of either version with the word diff of every cell and its change."""
    compared = []
    for feature_id in sorted(set(previous) | set(current)):
        old = previous.get(feature_id, (None,) * 6)
        new = current.get(feature_id, (None,) * 6)
        cells = [word_diff(a, b) for a, b in zip(old, new)]
        if feature_id not in previous:
            change = "Added"
        elif feature_id not in current:
            change = "Removed"
        else:
            change = "Changed" if old != new else None
        compared.append((cells, change))
    return compared


def rich_text(parts):
    """A workbook cell value for the parts of a cell."""
    if all(kind == "equal" for kind, _ in parts):
        return "".join(text for _, text in parts) or None
    blocks = []
    for kind, text in parts:
        if kind == "equal":
            blocks.append(text)
        elif kind == "removed":
            blocks.append(TextBlock(InlineFont(strike=True, color=REMOVED), text))
        else:
            blocks.append(TextBlock(InlineFont(u="single", color=ADDED), text))
    return CellRichText(blocks)


def write_workbook(compared, title, sheet_title, path):
    """Write the comparison workbook."""
    book = Workbook()
    sheet = book.active
    sheet.title = sheet_title
    sheet.append([title])
    sheet["A1"].font = Font(bold=True)
    sheet.append(list(COLUMNS))
    for cell in sheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
    for cells, change in compared:
        sheet.append([rich_text(parts) for parts in cells] + [change])
    for row in sheet.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column, width in zip("ABCDEFG", COLUMNS.values()):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "B3"
    book.save(path)


def page(compared, versions):
    """The HTML page of the comparison."""
    old, new = versions
    tags = {"equal": "{}", "removed": "<del>{}</del>", "added": "<ins>{}</ins>"}
    rows = []
    for cells, change in compared:
        tds = ["".join(tags[kind].format(html.escape(text)) for kind, text in parts) for parts in cells]
        rows.append("<tr>" + "".join(f"<td>{td}</td>" for td in tds + [change or ""]) + "</tr>")
    columns = "".join(f"<col style='width: {width}'>" for width in PAGE_COLUMN_WIDTHS)
    header = "".join(f"<th>{name}</th>" for name in COLUMNS)
    heading = f"SWP490_GFA26SE153 Feature List: {old} vs {new}"
    legend = f"<del>Red strikethrough</del>: removed in {new}. <ins>Blue underline</ins>: added in {new}."
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{heading}</title>"
        f"<style>{PAGE_STYLE}</style></head><body><h1>{heading}</h1><p>{legend}</p>"
        f"<table><colgroup>{columns}</colgroup><thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def find_browser():
    """The path of an installed Chrome or Edge, or None."""
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
        if Path(name).is_file():
            return name
    return None


def print_pdf(content, path):
    """Print an HTML page to a PDF with Chrome or Edge; return False when neither is installed."""
    browser = find_browser()
    if not browser:
        return False
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "comparison.html"
        source.write_text(content, encoding="utf-8")
        subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={path}",
                source.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    return True


def write(previous_path, current, versions, workbook_path, pdf_path):
    """Write the comparison of the current rows with the previous workbook, as a workbook and a PDF."""
    old, new = versions
    title = f"Feature list {old} vs {new}. Red strikethrough: removed in {new}. Blue underline: added in {new}."
    compared = compare(read_rows(previous_path), {row[0]: row for row in current})
    write_workbook(compared, title, f"{old} vs {new}", workbook_path)
    if not print_pdf(page(compared, versions), pdf_path):
        print(f"No Chrome or Edge found: {pdf_path.name} was not updated", file=sys.stderr)
    return compared
