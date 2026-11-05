"""Show what changed in a flow diagram: a page with the pictures side by side and the changes coloured.

change BEFORE AFTER OUT
    Compares two versions of one file, cell by cell id, on every page. Green is added, red is removed, amber is a
    changed label, shape, lane or line end; everything else is faded.
compare TUYEN MINE MAPPING OUT [--page N]
    Compares page N (default 1) of a file of this folder with a generated flow of ../flows, which share no ids.
    MAPPING is a JSON file: {"pairs": [{"tuyen": "<id>", "mine": "<id>", "same": true|false, "note": "..."}]}.
    Purple is only in Tuyen's drawing, orange only in the owner's, amber in both but different.
OUT gets diff.html, the coloured .drawio copies and their pictures.
Run: python _review/flow_diff.py change before.drawio after.drawio _review/wf-03/step-01
"""

import base64
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

GREEN, RED, AMBER, PURPLE, ORANGE = ("#16A34A", "#DCFCE7"), ("#DC2626", "#FEE2E2"), ("#D97706", "#FEF3C7"), \
    ("#7C3AED", "#EDE9FE"), ("#EA580C", "#FFEDD5")
FADE = "opacity=22;textOpacity=35;"


def drawio():
    for name in ("drawio", "draw.io"):
        if shutil.which(name):
            return shutil.which(name)
    default = Path("C:/Program Files/draw.io/draw.io.exe")
    if default.exists():
        return str(default)
    raise SystemExit("draw.io desktop is needed to draw the pictures")


def load(path):
    tree = ET.parse(path)
    for diagram in tree.getroot().iter("diagram"):
        if diagram.find("mxGraphModel") is None:
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15).decode()
            diagram.text = None
            diagram.append(ET.fromstring(urllib.parse.unquote(raw)))
    return tree


def pages(tree):
    return [(d.get("name"), {c.get("id"): c for c in d.iter("mxCell")}) for d in tree.getroot().iter("diagram")]


def plain(cell):
    value = cell.get("value") or ""
    value = re.sub(r"<br\s*/?>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip()


def style_map(style):
    items = {}
    for token in (style or "").split(";"):
        if token:
            key, _, value = token.partition("=")
            items[key] = value if _ else None
    return items


def style_text(items):
    return "".join(f"{k}={v};" if v is not None else f"{k};" for k, v in items.items())


def shape(cell):
    items = style_map(cell.get("style"))
    if "shape" in items:
        return items["shape"]
    first = next(iter(items), "")
    return first if items.get(first) is None else "rect"


def is_lane(cell):
    return (cell.get("style") or "").startswith("swimlane")


def symbol(cell):
    """What a vertex means, by its shape, fill and border."""
    items = style_map(cell.get("style"))
    kind, fill = shape(cell), items.get("fillColor", "")
    if kind == "sumEllipse":
        return "⊗ flow final"
    if kind == "endState":
        return "◉ activity final"
    if kind == "doubleEllipse":
        return "END circle"
    if kind == "ellipse":
        return "START circle" if fill == "#16A34A" else "● initial node"
    if kind == "rhombus":
        return "decision"
    if kind == "text":
        return "text"
    if is_lane(cell):
        return "lane"
    if items.get("dashed") == "1":
        return "notification" if fill == "#EFF6FF" else "system activity"
    return "activity"


def box(cells, cid):
    """Absolute (x, y, w, h) of a vertex."""
    cell = cells[cid]
    g = cell.find("mxGeometry")
    x, y = float(g.get("x", 0)), float(g.get("y", 0))
    parent = cell.get("parent")
    while parent in cells and cells[parent].find("mxGeometry") is not None and parent not in ("0", "1"):
        pg = cells[parent].find("mxGeometry")
        x, y = x + float(pg.get("x", 0)), y + float(pg.get("y", 0))
        parent = cells[parent].get("parent")
    return x, y, float(g.get("width", 0)), float(g.get("height", 0))


def lane_of(cells, cid):
    x, y, w, h = box(cells, cid)
    cx, cy = x + w / 2, y + h / 2
    for lid, lane in cells.items():
        items = style_map(lane.get("style"))
        if not is_lane(lane) or items.get("horizontal") == "0" or plain(lane) == "Legend" or lid == cid:
            continue
        lx, ly, lw, lh = box(cells, lid)
        if lx <= cx < lx + lw and ly <= cy < ly + lh:
            return plain(lane)
    return ""


def describe(cells, cid):
    cell = cells.get(cid)
    if cell is None:
        return cid
    if cell.get("edge") == "1":
        label = plain(cell)
        ends = f"{describe(cells, cell.get('source'))} → {describe(cells, cell.get('target'))}"
        return f"{ends} [{label}]" if label else ends
    attached = next((cells[cid + s] for s in ("_t", "_label") if cid + s in cells), None)
    text = plain(cell) or (plain(attached) if attached is not None else "")
    return f"{symbol(cell)} “{text}”" if text else symbol(cell)


def classify(before, after):
    """{id: (kind, details)} for the cells that differ between two pages with the same ids."""
    result = {}
    for cid in set(before) | set(after):
        if cid in ("0", "1"):
            continue
        if cid not in before:
            result[cid] = ("added", [])
            continue
        if cid not in after:
            result[cid] = ("removed", [])
            continue
        a, b = before[cid], after[cid]
        details = []
        if plain(a) != plain(b):
            details.append(("label", plain(a), plain(b)))
        if a.get("edge") == "1":
            if (a.get("source"), a.get("target")) != (b.get("source"), b.get("target")):
                details.append(("ends", describe(before, cid), describe(after, cid)))
            if ("dashed=1" in (a.get("style") or "")) != ("dashed=1" in (b.get("style") or "")):
                details.append(("line", "dashed" if "dashed=1" in (a.get("style") or "") else "solid",
                                "dashed" if "dashed=1" in (b.get("style") or "") else "solid"))
        elif a.find("mxGeometry") is not None and not is_lane(a):
            if symbol(a) != symbol(b):
                details.append(("shape", f"{symbol(a)} {describe(before, cid)}", symbol(b)))
            la, lb = lane_of(before, cid), lane_of(after, cid)
            if la != lb:
                details.append(("lane", la, lb))
        if details:
            result[cid] = ("changed", details)
    return result


def paint(cell, colour):
    items = style_map(cell.get("style"))
    line, fill = colour
    items["strokeColor"] = line
    items["strokeWidth"] = "3"
    items["fontColor"] = line if cell.get("edge") == "1" else items.get("fontColor", "#111827")
    if cell.get("edge") != "1":
        if items.get("text", "x") is None or next(iter(items), "") == "text":
            items["labelBackgroundColor"] = fill
            items["fontColor"] = line
            items["strokeColor"] = "none"
        elif items.get("fillColor") not in ("#111827", None) or shape(cell) not in ("endState", "ellipse"):
            items["fillColor"] = fill
    cell.set("style", style_text(items))


def fade(cell):
    if is_lane(cell):
        return
    cell.set("style", (cell.get("style") or "") + FADE)


def colour_copy(tree, page_colours, path):
    """Write a copy of tree where page i's cells take page_colours[i][id] and the rest fade."""
    copy = ET.fromstring(ET.tostring(tree.getroot()))
    for i, diagram in enumerate(copy.iter("diagram")):
        colours = page_colours[i] if i < len(page_colours) else {}
        for cell in diagram.iter("mxCell"):
            cid = cell.get("id")
            if cid in ("0", "1"):
                continue
            if cid in colours:
                paint(cell, colours[cid])
            else:
                fade(cell)
    path.write_text(ET.tostring(copy, encoding="unicode"), encoding="utf-8")


def page_root(tree, page):
    return list(tree.getroot().iter("diagram"))[page - 1].find("mxGraphModel/root")


def bounds(root):
    xs, ys = [], []
    for cell in root:
        g = cell.find("mxGeometry")
        if cell.get("parent") != "1" or g is None:
            continue
        if cell.get("edge") == "1":
            for p in g.iter("mxPoint"):
                if p.get("as") != "offset":
                    xs.append(float(p.get("x", 0)))
                    ys.append(float(p.get("y", 0)))
        else:
            x, y = float(g.get("x", 0)), float(g.get("y", 0))
            xs += [x, x + float(g.get("width", 0))]
            ys += [y, y + float(g.get("height", 0))]
    return min(xs), min(ys), max(xs), max(ys)


def placed_copy(root, prefix, dx, dy):
    """The cells of a page with prefixed ids, the top-level ones moved by (dx, dy)."""
    cells = []
    for cell in root:
        if cell.get("id") in ("0", "1"):
            continue
        copy = ET.fromstring(ET.tostring(cell))
        for key in ("id", "parent", "source", "target"):
            if copy.get(key) and copy.get(key) not in ("0", "1"):
                copy.set(key, prefix + copy.get(key))
        g = copy.find("mxGeometry")
        if copy.get("parent") == "1" and g is not None:
            if copy.get("edge") == "1":
                for p in g.iter("mxPoint"):
                    if p.get("as") != "offset":
                        p.set("x", f"{float(p.get('x', 0)) + dx:g}")
                        p.set("y", f"{float(p.get('y', 0)) + dy:g}")
            else:
                g.set("x", f"{float(g.get('x', 0)) + dx:g}")
                g.set("y", f"{float(g.get('y', 0)) + dy:g}")
        cells.append(copy)
    return cells


def text_cell(cid, value, x, y, w, h, size, bold=False):
    cell = ET.Element("mxCell", id=cid, value=value, vertex="1", parent="1",
                      style=f"text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize={size};"
                            f"fontFamily=Helvetica;fontColor=#111827;{'fontStyle=1;' if bold else ''}")
    ET.SubElement(cell, "mxGeometry", x=f"{x:g}", y=f"{y:g}", width=f"{w:g}", height=f"{h:g}", **{"as": "geometry"})
    return cell


def side_by_side(left, right, captions, notes, out_png):
    """One PNG: the list of changes on top, then the two coloured drawings side by side with their captions."""
    gap, margin = 80, 20
    lb, rb = bounds(left), bounds(right)
    lw, rw = lb[2] - lb[0], rb[2] - rb[0]
    width = lw + gap + rw
    lines = notes or ["Không thay đổi."]
    notes_h = 26 * len(lines) + 16
    top = margin + notes_h + 40
    cells = [text_cell("notes", "<br>".join(html.escape(line) for line in lines), margin, margin, width, notes_h, 17)]
    cells.append(text_cell("cap_l", html.escape(captions[0]), margin, top - 32, lw, 28, 18, True))
    cells.append(text_cell("cap_r", html.escape(captions[1]), margin + lw + gap, top - 32, rw, 28, 18, True))
    cells += placed_copy(left, "l_", margin - lb[0], top - lb[1])
    cells += placed_copy(right, "r_", margin + lw + gap - rb[0], top - rb[1])
    body = "".join(ET.tostring(c, encoding="unicode") for c in cells)
    drawio_file = out_png.with_suffix(".drawio")
    drawio_file.write_text('<mxfile><diagram id="diff" name="diff"><mxGraphModel grid="0" page="0" background="#FFFFFF">'
                           f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>'
                           '</mxfile>', encoding="utf-8")
    subprocess.run([drawio(), "-x", "-f", "png", "-s", "1", "-b", "10", "-o", str(out_png), str(drawio_file)],
                   check=True, capture_output=True)
    return out_png


def picture(drawio_file, page, out):
    subprocess.run([drawio(), "-x", "-f", "png", "-p", str(page), "-s", "1", "-o", str(out), str(drawio_file)],
                   check=True, capture_output=True)
    return "data:image/png;base64," + base64.b64encode(out.read_bytes()).decode()


PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><style>
:root{{--bg:#FFFFFF;--fg:#111827;--muted:#6B7280;--line:#E5E7EB}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0F172A;--fg:#E5E7EB;--muted:#9CA3AF;--line:#334155}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px;border-top:1px solid var(--line);padding-top:16px}}
.key span{{display:inline-block;margin-right:14px}} .key i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
ul{{margin:6px 0 12px;padding-left:20px}} li{{margin:2px 0}} .muted{{color:var(--muted)}}
.pair{{display:flex;gap:16px;flex-wrap:wrap}} .pair figure{{flex:1 1 420px;margin:0;min-width:0}}
figcaption{{font-weight:600;margin-bottom:6px}} img{{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;background:#FFFFFF}}
</style></head><body><h1>{title}</h1><p class="muted">{subtitle}</p><p class="key">{key}</p>{body}</body></html>"""


def key(entries):
    return "".join(f'<span><i style="background:{fill};border:2px solid {line}"></i>{html.escape(name)}</span>'
                   for name, (line, fill) in entries)


def change_mode(before_path, after_path, out):
    out.mkdir(parents=True, exist_ok=True)
    before, after = load(before_path), load(after_path)
    before_pages, after_pages = pages(before), pages(after)
    sections, before_colours, after_colours = [], [], []
    for i, ((name, bcells), (_, acells)) in enumerate(zip(before_pages, after_pages)):
        changes = classify(bcells, acells)
        bc, ac, items = {}, {}, []
        for cid, (kind, details) in sorted(changes.items(), key=lambda kv: kv[0]):
            if kind == "added":
                ac[cid] = GREEN
                items.append(f"<li><b>Thêm</b> {html.escape(describe(acells, cid))}</li>")
            elif kind == "removed":
                bc[cid] = RED
                items.append(f"<li><b>Xoá</b> {html.escape(describe(bcells, cid))}</li>")
            else:
                bc[cid] = ac[cid] = AMBER
                for what, old, new in details:
                    word = {"label": "Đổi nhãn", "ends": "Đổi đầu cạnh", "line": "Đổi nét", "shape": "Đổi hình",
                            "lane": "Đổi lane"}[what]
                    items.append(f"<li><b>{word}</b>: {html.escape(old)} → {html.escape(new)}</li>")
        before_colours.append(bc)
        after_colours.append(ac)
        sections.append((i, name, items))
    colour_copy(before, before_colours, out / "before-highlighted.drawio")
    colour_copy(after, after_colours, out / "after-highlighted.drawio")
    body = []
    for i, name, items in sections:
        body.append(f"<h2>{html.escape(name)}</h2>")
        if not items:
            body.append('<p class="muted">Không thay đổi.</p>')
            continue
        body.append(f"<ul>{''.join(items)}</ul>")
        left = picture(out / "before-highlighted.drawio", i + 1, out / f"page{i + 1}-before.png")
        right = picture(out / "after-highlighted.drawio", i + 1, out / f"page{i + 1}-after.png")
        body.append(f'<div class="pair"><figure><figcaption>Trước</figcaption><img src="{left}" alt="Trước"></figure>'
                    f'<figure><figcaption>Sau</figcaption><img src="{right}" alt="Sau"></figure></div>')
    count = sum(len(items) for _, _, items in sections)
    before_hl, after_hl = ET.parse(out / "before-highlighted.drawio"), ET.parse(out / "after-highlighted.drawio")
    for i, name, items in sections:
        if items:
            notes = [f"{name}: {len(items)} thay đổi. Xanh lá = thêm · Đỏ = xoá · Vàng cam = đổi; phần còn lại làm mờ."]
            notes += ["• " + html.unescape(re.sub(r"<[^>]+>", "", item)) for item in items]
            png = side_by_side(page_root(before_hl, i + 1), page_root(after_hl, i + 1), ("Trước", "Sau"), notes,
                               out / f"page{i + 1}-diff.png")
            print(f"picture: {png}")
    page = PAGE.format(title=f"Thay đổi: {html.escape(after_path.name)}",
                       subtitle=f"{count} thay đổi, so {html.escape(before_path.name)} với bản hiện tại.",
                       key=key([("Thêm", GREEN), ("Xoá", RED), ("Đổi", AMBER)]), body="".join(body))
    (out / "diff.html").write_text(page, encoding="utf-8")
    print(f"{count} changes; open {out / 'diff.html'}")


def compare_mode(tuyen_path, mine_path, mapping_path, out, page):
    out.mkdir(parents=True, exist_ok=True)
    tuyen, mine = load(tuyen_path), load(mine_path)
    tname, tcells = pages(tuyen)[page - 1]
    _, mcells = pages(mine)[0]
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))["pairs"]

    def owners(cells, suffixes):
        """Shapes that are steps: vertices that are neither lanes, legend rows, nor text attached to a shape."""
        legend = {cid for cid, c in cells.items() if plain(c) == "Legend"}
        result = []
        for cid, c in cells.items():
            if c.get("vertex") != "1" or is_lane(c) or any(cid.startswith(l) for l in legend):
                continue
            if any(cid.endswith(s) and cid[: -len(s)] in cells for s in suffixes):
                continue
            result.append(cid)
        return result

    tsteps, msteps = owners(tcells, ("_t",)), owners(mcells, ("_label",))
    t2m = {p["tuyen"]: p for p in mapping}
    m2t = {p["mine"]: p for p in mapping}
    tc, mc = {}, {}
    for cid in tsteps:
        p = t2m.get(cid)
        colour = PURPLE if p is None else (None if p.get("same") else AMBER)
        if colour:
            tc[cid] = colour
            if cid + "_t" in tcells:
                tc[cid + "_t"] = colour
    for cid in msteps:
        p = m2t.get(cid)
        colour = ORANGE if p is None else (None if p.get("same") else AMBER)
        if colour:
            mc[cid] = colour
            if cid + "_label" in mcells:
                mc[cid + "_label"] = colour

    def edges(cells, other_map):
        return {(c.get("source"), c.get("target")): cid for cid, c in cells.items() if c.get("edge") == "1"}

    tedges, medges = edges(tcells, t2m), edges(mcells, m2t)
    for (s, t), cid in tedges.items():
        ms, mt = t2m.get(s, {}).get("mine"), t2m.get(t, {}).get("mine")
        if not (ms and mt and (ms, mt) in medges):
            tc[cid] = PURPLE
    for (s, t), cid in medges.items():
        ts, tt = m2t.get(s, {}).get("tuyen"), m2t.get(t, {}).get("tuyen")
        if not (ts and tt and (ts, tt) in tedges):
            mc[cid] = ORANGE
    page_colours = [{} for _ in pages(tuyen)]
    page_colours[page - 1] = tc
    colour_copy(tuyen, page_colours, out / "tuyen-highlighted.drawio")
    colour_copy(mine, [mc], out / "mine-highlighted.drawio")
    left = picture(out / "tuyen-highlighted.drawio", page, out / "tuyen.png")
    right = picture(out / "mine-highlighted.drawio", 1, out / "mine.png")
    only_t = [describe(tcells, c) for c in tsteps if c not in t2m]
    only_m = [describe(mcells, c) for c in msteps if c not in m2t]
    differs = [(describe(tcells, p["tuyen"]), describe(mcells, p["mine"]), p.get("note", "")) for p in mapping
               if not p.get("same")]
    same = [(describe(tcells, p["tuyen"]), describe(mcells, p["mine"])) for p in mapping if p.get("same")]
    lists = (f"<h2>Chỉ có ở bản Tuyên ({len(only_t)})</h2><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in only_t)}</ul>"
             f"<h2>Chỉ có ở bản của bạn ({len(only_m)})</h2><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in only_m)}</ul>"
             f"<h2>Có ở cả hai nhưng khác ({len(differs)})</h2><ul>"
             + "".join(f"<li>{html.escape(a)} ↔ {html.escape(b)}{(' — ' + html.escape(n)) if n else ''}</li>"
                       for a, b, n in differs)
             + f"</ul><h2>Giống nhau ({len(same)})</h2><ul>"
             + "".join(f"<li>{html.escape(a)} ↔ {html.escape(b)}</li>" for a, b in same) + "</ul>")
    pictures = (f'<h2>Hai bản</h2><div class="pair"><figure><figcaption>Tuyên (gốc): {html.escape(tname)}</figcaption>'
                f'<img src="{left}" alt="Tuyên"></figure><figure><figcaption>Bản của bạn: {html.escape(mine_path.name)}'
                f'</figcaption><img src="{right}" alt="Bản của bạn"></figure></div>')
    page_html = PAGE.format(title=f"So sánh: {html.escape(tname)}",
                            subtitle="Các ô được ghép theo nghĩa; ô giống nhau được làm mờ.",
                            key=key([("Chỉ có ở bản Tuyên", PURPLE), ("Chỉ có ở bản của bạn", ORANGE),
                                     ("Có ở cả hai nhưng khác", AMBER)]), body=pictures + lists)
    (out / "diff.html").write_text(page_html, encoding="utf-8")
    notes = ["Tím = chỉ có ở bản Tuyên · Cam = chỉ có ở bản của bạn · Vàng cam = có ở cả hai nhưng khác; "
             "ô giống nhau làm mờ.",
             f"Chỉ có ở bản Tuyên ({len(only_t)}): " + "; ".join(only_t),
             f"Chỉ có ở bản của bạn ({len(only_m)}): " + "; ".join(only_m),
             f"Có ở cả hai nhưng khác ({len(differs)}):"]
    notes += [f"• {a} ↔ {b}" + (f" — {n}" if n else "") for a, b, n in differs]
    png = side_by_side(page_root(ET.parse(out / "tuyen-highlighted.drawio"), page),
                       page_root(ET.parse(out / "mine-highlighted.drawio"), 1),
                       (f"Tuyên (gốc): {tname}", f"Bản của bạn: {mine_path.name}"), notes, out / "compare.png")
    print(f"picture: {png}")
    print(f"{len(only_t)} only in Tuyen's, {len(only_m)} only in the owner's, {len(differs)} differ; "
          f"open {out / 'diff.html'}")


def main():
    args = sys.argv[1:]
    if args[:1] == ["change"] and len(args) == 4:
        change_mode(Path(args[1]), Path(args[2]), Path(args[3]))
    elif args[:1] == ["compare"] and len(args) in (5, 7):
        page = int(args[6]) if len(args) == 7 and args[5] == "--page" else 1
        compare_mode(Path(args[1]), Path(args[2]), Path(args[3]), Path(args[4]), page)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
