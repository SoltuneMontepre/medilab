"""Build the website of the activity diagrams from ../final, and the pictures, zip and PDF of ../final.

../final holds the draw.io file of the system activity map and of each flow, named with its ID and title: the core
flows WF-01 to WF-06, each with a Workflow and a Demo scenarios page, and the supporting flows SF-01 to SF-11. To
change a diagram, edit its draw.io file there, then build and deploy.

The home page is the system activity map, whose flows link to their own pages. Titles come from the headings of
business-flows.md, and the flows each one comes from and leads to come from the lines of the map.
Next to each draw.io file of ../final, a build writes an SVG of each page and, for a core flow, a PNG of each page.
activity-diagrams-final.zip holds ../final; activity-diagrams-final.pdf holds the map and the Workflow page of each
flow, with a bookmark for each.
Run: uv run --with pypdf python build.py, then deploy the folder with: vercel deploy --prod
"""

import base64
import html
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from datetime import date
from pathlib import Path
from string import Template

HERE = Path(__file__).resolve().parent
DIAGRAMS = HERE.parent
ROOT = HERE.parents[3]
FLOWS_MD = ROOT / "docs" / "functional" / "business-flows.md"
LOGO = ROOT / "src" / "core" / "modules" / "sol_theme" / "static" / "src" / "img" / "medilab.svg"
STATIC = HERE / "static"
PUBLIC = HERE / "public"
FINAL = DIAGRAMS / "final"
MAP_DRAWIO = FINAL / "System activity map.drawio"
FINAL_ZIP = DIAGRAMS / "activity-diagrams-final.zip"
FINAL_PDF = DIAGRAMS / "activity-diagrams-final.pdf"
FLOW_KEY = re.compile(r"^m_((?:WF|SF)\d\d)$")
FALLBACK = re.compile(r"(<switch>.*?</foreignObject>)<image [^>]*/>(</switch>)", re.S)


def drawio():
    for name in ("drawio", "draw.io"):
        if shutil.which(name):
            return shutil.which(name)
    return "C:/Program Files/draw.io/draw.io.exe"


def titles():
    text = FLOWS_MD.read_text(encoding="utf-8")
    return dict(re.findall(r"^## ((?:WF|SF)-\d\d) (.+)$", text, re.M))


def folder(fid):
    return FINAL / ("Core flows" if fid.startswith("WF") else "Supporting flows")


def source(fid):
    """The draw.io file of a flow in ../final."""
    return next(folder(fid).glob(f"{fid} *.drawio"))


def pages(path):
    """The name and graph model of each page of a draw.io file."""
    for diagram in ET.parse(path).getroot().iter("diagram"):
        model = diagram.find("mxGraphModel")
        if model is None:
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15).decode()
            model = ET.fromstring(urllib.parse.unquote(raw))
        yield diagram.get("name"), model


def map_links():
    """For each flow, the flows and events that lead to it and the flows it leads to, from the map's lines."""
    _, model = next(pages(MAP_DRAWIO))
    cells = {c.get("id"): c for c in model.iter("mxCell") if (c.get("id") or "").startswith("m_")}
    names = {cid: re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", c.get("value") or ""))).strip()
             for cid, c in cells.items()}
    comes, leads = {}, {}
    for cell in cells.values():
        if cell.get("edge") != "1":
            continue
        source_id, target_id = cell.get("source"), cell.get("target")
        s_key, t_key = FLOW_KEY.match(source_id or ""), FLOW_KEY.match(target_id or "")
        if t_key:
            entry = flow_id(s_key.group(1)) if s_key else names.get(source_id, "")
            comes.setdefault(flow_id(t_key.group(1)), []).append(entry)
        if s_key and t_key:
            leads.setdefault(flow_id(s_key.group(1)), []).append(flow_id(t_key.group(1)))
    return comes, leads


def flow_id(key):
    return f"{key[:2]}-{key[2:]}"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def for_web(svg_text):
    """Keep the light colours of a draw.io export whatever the viewer's colour scheme, and drop the PNG copies of
    its HTML labels, which only viewers without HTML in SVG use."""
    svg_text = svg_text.replace("color-scheme: light dark;", "color-scheme: light;", 1)
    return FALLBACK.sub(r"\1\2", svg_text)


def export(path, number, out, kind):
    subprocess.run([drawio(), "-x", "-f", kind, "-p", str(number), "-o", str(out), str(path)],
                   check=True, capture_output=True)


def export_svg(path, number, out):
    """Export one page to SVG; draw.io names each export with a random id, which is replaced by the file's name so
    that an unchanged page exports the same file."""
    export(path, number, out, "svg")
    text = for_web(out.read_text(encoding="utf-8"))
    random_id = re.search(r'id="(ge-svg-[^"]+)"', text)
    if random_id:
        text = text.replace(random_id.group(1), f"ge-svg-{out.stem}")
    out.write_text(text, encoding="utf-8")


def build_diagrams(names):
    """Write the diagrams to public/diagrams and return the views of each flow: (label, page number, published
    path). A flow with one page has the view Activity diagram."""
    out_dir = PUBLIC / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)
    export_svg(MAP_DRAWIO, 1, out_dir / "map.svg")
    views = {}
    for fid in names:
        path = source(fid)
        found = [page for page, _ in pages(path)]
        views[fid] = []
        for number, page in enumerate(found, 1):
            label = page.removeprefix(fid).strip() if len(found) > 1 else "Activity diagram"
            name = f"{slug(fid)}-{slug(label)}.svg" if len(found) > 1 else f"{slug(fid)}.svg"
            export_svg(path, number, out_dir / name)
            views[fid].append((label, number, f"/diagrams/{name}"))
        print(f"{fid}: {', '.join(label for label, _, _ in views[fid])}")
    return views


PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$page_title</title>
<meta name="description" content="$description">
<link rel="icon" href="/assets/medilab.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/assets/style.css">
<script src="/assets/app.js" defer></script>
</head>
<body>
<header class="navbar">
  <a class="brand" href="/"><img src="/assets/medilab.svg" alt="" width="28" height="28"><span>Medilab</span><span class="brand-sub">Activity diagrams</span></a>
  <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="menu" aria-label="Menu"><span></span></button>
  <nav id="menu" class="menu" aria-label="Flows">
    <a class="entry$map_active" href="/">System activity map</a>
    <details class="dropdown$core_active">
      <summary class="entry">Core flows</summary>
      <div class="dropdown-menu">$core_menu</div>
    </details>
    <details class="dropdown$support_active">
      <summary class="entry">Supporting flows</summary>
      <div class="dropdown-menu">$support_menu</div>
    </details>
  </nav>
</header>
<div class="control-panel">
  <nav aria-label="Breadcrumb"><ol class="breadcrumb">$crumbs</ol></nav>
  $tabs
</div>
<main>
$main
</main>
<footer class="footer">Built $built from <code>docs/functional/business-flows.md</code> and the flow diagrams.</footer>
</body>
</html>
""")

VIEWER = Template("""<section class="viewer" data-src="$src"$extra>
  <div class="toolbar" role="toolbar" aria-label="Zoom">
    <button type="button" data-zoom="out" aria-label="Zoom out">&minus;</button>
    <output class="zoom-level">100%</output>
    <button type="button" data-zoom="in" aria-label="Zoom in">+</button>
    <button type="button" data-zoom="fit">Fit</button>
    <button type="button" data-zoom="actual">100%</button>
    <span class="hint">Drag to move · Ctrl + scroll or pinch to zoom</span>
    <a class="open" href="$src" target="_blank" rel="noopener">Open SVG</a>
  </div>
  <div class="canvas" tabindex="0" aria-label="$label"><div class="stage"></div></div>
</section>""")


def esc(text):
    return html.escape(text, quote=True)


def menu(names, prefix, current):
    items = []
    for fid, title in names.items():
        if fid.startswith(prefix):
            here = ' aria-current="page"' if fid == current else ""
            items.append(f'<a href="/{slug(fid)}/"{here}><b>{fid}</b><span>{esc(title)}</span></a>')
    return "".join(items)


def crumb(label, href=None):
    if href:
        return f'<li><a href="{href}">{esc(label)}</a></li>'
    return f'<li aria-current="page">{esc(label)}</li>'


def chip(entry, names):
    if entry in names:
        return f'<a class="chip chip-{entry[:2].lower()}" href="/{slug(entry)}/"><b>{entry}</b> {esc(names[entry])}</a>'
    return f'<span class="chip chip-event">{esc(entry)}</span>'


def write_page(path, *, title, description, current, crumbs, tabs, main, names):
    family = current[:2] if current else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.substitute(
        page_title=esc(title), description=esc(description),
        map_active=" active" if not current else "",
        core_active=" active" if family == "WF" else "",
        support_active=" active" if family == "SF" else "",
        core_menu=menu(names, "WF", current), support_menu=menu(names, "SF", current),
        crumbs="".join(crumbs), tabs=tabs, main=main, built=date.today().strftime("%d-%m-%Y"),
    ), encoding="utf-8")


def cards(names, prefix):
    return "".join(
        f'<a class="card card-{prefix.lower()}" href="/{slug(fid)}/"><b>{fid}</b><span>{esc(title)}</span></a>'
        for fid, title in names.items() if fid.startswith(prefix))


def write_home(names):
    links = {fid.replace("-", ""): {"href": f"/{slug(fid)}/", "title": f"{fid} {title}"}
             for fid, title in names.items()}
    flows_attr = esc(json.dumps(links))
    main = VIEWER.substitute(src="/diagrams/map.svg", extra=f' data-map="{flows_attr}"',
                             label="System activity map") + f"""
<section class="index" id="core">
  <h2>Core flows</h2>
  <p>The path of one order, from the customer's order to the delivered report.</p>
  <div class="cards">{cards(names, "WF")}</div>
</section>
<section class="index" id="supporting">
  <h2>Supporting flows</h2>
  <p>Flows that a core flow hands work to, or that an event starts on its own.</p>
  <div class="cards">{cards(names, "SF")}</div>
</section>"""
    write_page(PUBLIC / "index.html", title="System activity map · Medilab",
               description="The business flows of Medilab and how they hand work to each other.",
               current=None, crumbs=[crumb("System activity map")], tabs="", main=main, names=names)


def write_flow(fid, names, views, comes, leads):
    family, anchor = ("Core flows", "core") if fid.startswith("WF") else ("Supporting flows", "supporting")
    title = f"{fid} {names[fid]}"
    tabs = ""
    if len(views) > 1:
        tabs = '<div class="tabs" role="tablist" aria-label="Diagram">' + "".join(
            f'<button type="button" role="tab" aria-selected="{"true" if i == 0 else "false"}" '
            f'data-src="{src}" data-hash="{slug(label)}">{esc(label)}</button>'
            for i, (label, _, src) in enumerate(views)) + "</div>"
    related = []
    if comes.get(fid):
        related.append('<div class="related-group"><span class="related-label">Comes from</span>'
                       + "".join(chip(e, names) for e in dict.fromkeys(comes[fid])) + "</div>")
    if leads.get(fid):
        related.append('<div class="related-group"><span class="related-label">Leads to</span>'
                       + "".join(chip(e, names) for e in dict.fromkeys(leads[fid])) + "</div>")
    main = (f'<div class="related">{"".join(related)}</div>' if related else "") + VIEWER.substitute(
        src=views[0][2], extra="", label=f"{title}, {views[0][0]}")
    write_page(PUBLIC / slug(fid) / "index.html", title=f"{title} · Medilab",
               description=f"Activity diagram of {title}.", current=fid,
               crumbs=[crumb("System activity map", "/"), crumb(family, f"/#{anchor}"), crumb(title)],
               tabs=tabs, main=main, names=names)


def write_final(names, views):
    """Write the SVG of each page next to its draw.io file in ../final, a PNG of each page for the core flows, and
    zip the folder."""
    for old in [*FINAL.rglob("*.svg"), *FINAL.rglob("*.png")]:
        old.unlink()
    shutil.copy(PUBLIC / "diagrams" / "map.svg", MAP_DRAWIO.with_suffix(".svg"))
    for fid in names:
        path = source(fid)
        for label, number, src in views[fid]:
            stem = f"{path.stem} - {label}" if len(views[fid]) > 1 else path.stem
            shutil.copy(PUBLIC / src.lstrip("/"), path.with_name(f"{stem}.svg"))
            if fid.startswith("WF"):
                export(path, number, path.with_name(f"{stem}.png"), "png")
    FINAL_ZIP.unlink(missing_ok=True)
    shutil.make_archive(str(FINAL_ZIP.with_suffix("")), "zip", FINAL.parent, FINAL.name)
    print(f"Wrote the pictures of {FINAL.relative_to(DIAGRAMS)} and {FINAL_ZIP.name}")


def write_pdf(names, views):
    """Join the map and the Workflow page of each flow into one PDF, with a bookmark for each. A core flow's Demo
    scenarios stay in ../final and on the website."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    with tempfile.TemporaryDirectory() as tmp:
        def append(path, page):
            out = Path(tmp) / f"{len(writer.pages)}.pdf"
            subprocess.run([drawio(), "-x", "-f", "pdf", "-p", str(page), "--crop", "-b", "16", "-o", str(out),
                            str(path)], check=True, capture_output=True)
            start = len(writer.pages)
            writer.append(str(out))
            return start

        writer.add_outline_item("System activity map", append(MAP_DRAWIO, 1))
        groups = {}
        for fid, title in names.items():
            number = next((n for label, n, _ in views[fid] if label == "Workflow"), 1)
            start = append(source(fid), number)
            group = folder(fid).name
            if group not in groups:
                groups[group] = writer.add_outline_item(group, start)
            writer.add_outline_item(f"{fid} {title}", start, parent=groups[group])
    writer.add_metadata({"/Title": "Medilab activity diagrams"})
    writer.page_mode = "/UseOutlines"
    with FINAL_PDF.open("wb") as file:
        writer.write(file)
    print(f"Wrote {FINAL_PDF.name}: {len(writer.pages)} pages")


def main():
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    names = titles()
    views = build_diagrams(names)
    comes, leads = map_links()
    assets = PUBLIC / "assets"
    shutil.copytree(STATIC, assets)
    shutil.copy(LOGO, assets / "medilab.svg")
    write_home(names)
    for fid in names:
        write_flow(fid, names, views[fid], comes, leads)
    print(f"Wrote {len(names) + 1} pages to {PUBLIC.relative_to(DIAGRAMS)}")
    write_final(names, views)
    write_pdf(names, views)


if __name__ == "__main__":
    main()
