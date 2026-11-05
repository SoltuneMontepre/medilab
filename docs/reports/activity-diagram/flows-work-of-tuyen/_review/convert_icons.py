"""Change a flow file of this folder to the owner's notation, in place, on every page.

- The green START circle becomes an initial node (●); its text loses the word START.
- The red END circle becomes an activity final (◉) when its text names an outcome, or a flow final (⊗) when it only
  hands the work to another flow; its text loses the word END.
- The legend shows the new symbols, with a flow final row only on pages that use one.
- Every flow ID that stands alone gets its title from business-flows.md: "→ WF-04" becomes
  "→ WF-04 Result entry and approval".
Run: python _review/convert_icons.py "<flow file>.drawio"
"""

import base64
import html
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
FLOWS_MD = ROOT / "docs" / "functional" / "business-flows.md"
FLOW_ID = re.compile(r"\b((?:WF|SF)-\d\d)\b(?!-)")
SIZE = 24
INITIAL = "ellipse;html=1;fillColor=#111827;strokeColor=#111827;"
FINAL = "shape=endState;html=1;fillColor=#111827;strokeColor=#111827;"
FLOW_FINAL = "shape=sumEllipse;perimeter=ellipsePerimeter;html=1;fillColor=#FFFFFF;strokeColor=#111827;strokeWidth=1.5;"


def titles():
    text = FLOWS_MD.read_text(encoding="utf-8")
    return dict(re.findall(r"^## ((?:WF|SF)-\d\d) (.+)$", text, re.M))


def models(root):
    """The graph model of each page, decompressing a compressed page in place."""
    for diagram in root.iter("diagram"):
        model = diagram.find("mxGraphModel")
        if model is None:
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15).decode()
            model = ET.fromstring(urllib.parse.unquote(raw))
            diagram.text = None
            diagram.append(model)
        yield diagram, model


def plain(value):
    return html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"</?b>", "", value or ""))).strip()


def with_titles(text, names):
    def name(match):
        fid = match.group(1)
        rest = text[match.end():]
        title = names.get(fid)
        if not title or rest.startswith(" " + title):
            return fid
        return f"{fid} {title}"

    return FLOW_ID.sub(name, text)


def resize(cell, size):
    g = cell.find("mxGeometry")
    x, y, w, h = (float(g.get(k)) for k in ("x", "y", "width", "height"))
    g.set("x", f"{x + (w - size) / 2:g}")
    g.set("y", f"{y + (h - size) / 2:g}")
    g.set("width", str(size))
    g.set("height", str(size))


def is_start(style):
    return style.startswith("ellipse") and "fillColor=#16A34A" in style


def is_end(style):
    return "doubleEllipse" in style and "fillColor=#DC2626" in style


def convert_page(model, names):
    cells = {c.get("id"): c for c in model.iter("mxCell")}
    legend = [c for c in cells.values() if (c.get("value") or "") == "Legend"]
    used_flow_final = False
    for cid, cell in cells.items():
        style = cell.get("style") or ""
        if cid.startswith(tuple(l.get("id") for l in legend)) and legend:
            continue
        if is_start(style):
            cell.set("style", INITIAL)
            resize(cell, SIZE)
            text = cells.get(cid + "_t")
            if text is not None:
                body = re.sub(r"^START\s*\n?", "", plain(text.get("value")))
                text.set("value", html.escape(with_titles(body, names)).replace("\n", "<br>"))
        elif is_end(style):
            text = cells.get(cid + "_t")
            body = re.sub(r"^END\s*:?\s*", "", plain(text.get("value"))) if text is not None else ""
            handover_only = body.startswith("→")
            used_flow_final |= handover_only
            cell.set("style", FLOW_FINAL if handover_only else FINAL)
            resize(cell, SIZE)
            if text is not None:
                text.set("value", html.escape(with_titles(body, names)).replace("\n", "<br>"))
    for cell in cells.values():
        style = cell.get("style") or ""
        value = cell.get("value") or ""
        if value and not style.startswith("swimlane") and FLOW_ID.search(plain(value)):
            fixed = with_titles(value, names)
            if fixed != value:
                cell.set("value", fixed)
    for box in legend:
        update_legend(model, box, used_flow_final)


def update_legend(model, box, used_flow_final):
    root = model.find("root")
    prefix = box.get("id")
    rows = {c.get("id"): c for c in root if (c.get("id") or "").startswith(prefix) and c.get("id") != prefix}
    start, start_text = rows.get(prefix + "0"), rows.get(prefix + "0t")
    end, end_text = rows.get(prefix + "1"), rows.get(prefix + "1t")
    if start is None or end is None:
        return
    start.set("style", INITIAL)
    resize(start, 20)
    start_text.set("value", "Initial node")
    end.set("style", FINAL)
    resize(end, 20)
    end_text.set("value", "Activity final")
    if not used_flow_final or (prefix + "ff") in rows:
        return
    step = float(rows[prefix + "2"].find("mxGeometry").get("y")) - float(end.find("mxGeometry").get("y"))
    for cid, cell in rows.items():
        g = cell.find("mxGeometry")
        if cid[len(prefix):][:1].isdigit() and int(re.match(r"\d+", cid[len(prefix):]).group()) >= 2:
            g.set("y", f"{float(g.get('y')) + step:g}")
    bg = box.find("mxGeometry")
    bg.set("height", f"{float(bg.get('height')) + step:g}")
    position = list(root).index(end_text) + 1
    for offset, (suffix, source, value, style) in enumerate(
            (("ff", end, "", FLOW_FINAL), ("fft", end_text, "Flow final", None))):
        copy = ET.fromstring(ET.tostring(source))
        copy.set("id", prefix + suffix)
        copy.set("value", value)
        if style:
            copy.set("style", style)
        g = copy.find("mxGeometry")
        g.set("y", f"{float(g.get('y')) + step:g}")
        root.insert(position + offset, copy)


def main():
    path = Path(sys.argv[1])
    tree = ET.parse(path)
    names = titles()
    for _, model in models(tree.getroot()):
        convert_page(model, names)
    tree.write(path, encoding="unicode")
    print(f"Converted {path.name}")


if __name__ == "__main__":
    main()
