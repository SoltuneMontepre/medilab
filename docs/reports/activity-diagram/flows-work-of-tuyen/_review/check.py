"""Count the lines that cross on every page of a flow file, as draw.io draws them.

draw.io routes these lines itself, so the file holds no full path: each page is exported to SVG and the drawn
paths of the lines are compared. Lines that share an end are not counted against each other.
Run: python _review/check.py "<flow file>.drawio"
"""

import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"


def drawio():
    for name in ("drawio", "draw.io"):
        if shutil.which(name):
            return shutil.which(name)
    return "C:/Program Files/draw.io/draw.io.exe"


def drawn_lines(svg_path, ids):
    lines = {}
    for g in ET.parse(svg_path).getroot().iter(SVG + "g"):
        cid = g.get("data-cell-id")
        if cid not in ids:
            continue
        for path in g.iter(SVG + "path"):
            if path.get("fill") == "none":
                points = [tuple(map(float, re.findall(r"[-\d.]+", step)[-2:]))
                          for step in re.findall(r"[MLQ][^MLQ]*", path.get("d"))]
                if len(points) > 1:
                    lines[cid] = points
                    break
    return lines


def cross(a, b, c, d):
    def side(p, q, r):
        value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (value > 1e-6) - (value < -1e-6)

    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def main():
    path = Path(sys.argv[1]).resolve()
    diagrams = list(ET.parse(path).getroot().iter("diagram"))
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for number, diagram in enumerate(diagrams, 1):
            edges = {c.get("id"): (c.get("source"), c.get("target"), re.sub("<[^>]+>", "", c.get("value") or ""))
                     for c in diagram.iter("mxCell") if c.get("edge") == "1"}
            labels = {c.get("id"): re.sub("<[^>]+>", " ", c.get("value") or "").strip() for c in diagram.iter("mxCell")}
            svg = Path(tmp) / f"page{number}.svg"
            subprocess.run([drawio(), "-x", "-f", "svg", "-p", str(number), "-o", str(svg), str(path)],
                           check=True, capture_output=True)
            lines = drawn_lines(svg, edges)
            found = []
            names = sorted(lines)
            for i, first in enumerate(names):
                for second in names[i + 1:]:
                    if set(edges[first][:2]) & set(edges[second][:2]):
                        continue
                    if any(cross(a, b, c, d) for a, b in zip(lines[first], lines[first][1:])
                           for c, d in zip(lines[second], lines[second][1:])):
                        found.append((first, second))
            total += len(found)
            print(f"{diagram.get('name')}: {len(lines)} lines, {len(found)} crossings")
            for first, second in found:
                def name(e):
                    s, t, label = edges[e]
                    return f"{labels.get(s, s)} -> {labels.get(t, t)}" + (f" [{label}]" if label else "")
                print(f"  {name(first)}  crosses  {name(second)}")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
