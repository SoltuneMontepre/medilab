"""Draw the MediLab conceptual ERD in Chen notation from the tables of readme.md next to this script.

Writes conceptual.puml, the overview with its entities at the grid positions saved in overview-layout.json, and one
conceptual-<area>.puml per area, then renders each to SVG with PlantUML. The overview is converted to conceptual.drawio
and its published SVG is exported from draw.io.
Run: python docs/reports/erd-diagram/erd_diagram.py --plantuml <plantuml.jar> --drawio <draw.io executable>
[--relayout [--seeds N] [--workers N]]
--relayout needs numpy, networkx and scipy, and searches new overview positions by simulated annealing.
"""

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from pathlib import Path
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
README = HERE / "readme.md"
LAYOUT = HERE / "overview-layout.json"
AREAS = [
    ("Catalog", "catalog", "#F9C08A"),
    ("Resources", "resources", "#B7DDA8"),
    ("Scheduling", "scheduling", "#D9D99A"),
    ("Testing", "testing", "#F4A9A9"),
    ("Approval", "approval", "#BFC0EC"),
    ("Sales", "sales", "#A9D4EE"),
    ("Finance", "finance", "#DDB4DD"),
]
HUBS = {"Signature", "ChangeRequest"}  # drawn as a copy next to each other area that uses them
CARDINALITIES = {"1": (1, False), "0..1": (0, False), "0..*": (0, True), "1..*": (1, True)}
KINDS = {"Strong", "Weak", "Composite"}
DIAMOND_OPACITY = 0.35  # a composite entity's diamond is faint, so the name written over it stays readable
COLS, ROWS = 13, 9
CELL_W, CELL_H = 360.0, 250.0
GHOST_FILL = "#E8E8E8"
LINE = "#9C5A24"
CHEN_STYLE = """<style>
element { BackGroundColor #F9C08A; LineColor #9C5A24 }
.rel { BackGroundColor #FFF3E0 }
.ext { BackGroundColor #E8E8E8 }
</style>"""


def table_rows(text, heading):
    """Return the cells of the first Markdown table after a heading, without its header and separator."""
    lines = text.split(heading + "\n", 1)[1].splitlines()
    rows = []
    for line in lines:
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[2:]


def read_model():
    """Read and check the Entities and Relationships tables; stop on the first inconsistency.

    A relationship named after a composite entity is that entity's link of the entities it combines. A weak entity
    has exactly one supporting relationship, in which it has exactly one owner.
    """
    text = README.read_text(encoding="utf-8")
    areas = {title for title, _, _ in AREAS}
    entities = {}
    for name, vietnamese, area, kind, identified_by, _step, _source in table_rows(text, "## Entities"):
        if area not in areas or name in entities or kind not in KINDS:
            sys.exit(f"Entities: bad or duplicate row {name}")
        owners = [] if kind == "Strong" else [part.strip() for part in identified_by.split("+")]
        entities[name] = {"vi": vietnamese, "area": area, "kind": kind, "by": owners}
    relationships = []
    for number, end1, card1, label, card2, end2, _source in table_rows(text, "## Relationships"):
        names = [end1] + [part.strip() for part in end2.split("+")]
        cards = [card1] + [part.strip() for part in card2.split("+")]
        if len(names) != len(cards) or any(n not in entities for n in names) or any(c not in CARDINALITIES for c in cards):
            sys.exit(f"Relationships: bad row {number}")
        composite = label if label in entities else None
        if composite and entities[composite]["kind"] != "Composite":
            sys.exit(f"Relationships: row {number} is named after {composite}, which is not a composite entity")
        relationships.append({"number": int(number), "ends": list(zip(names, cards)), "label": label,
                              "composite": composite, "identifying": False})
    for name, entity in entities.items():
        if entity["kind"] == "Composite":
            rows = [r for r in relationships if r["composite"] == name]
            if len(rows) != 1 or sorted(n for n, _ in rows[0]["ends"]) != sorted(entity["by"]):
                sys.exit(f"{name}: needs one relationship named after it, between {' + '.join(entity['by'])}")
        elif entity["kind"] == "Weak":
            rows = [r for r in relationships if sorted(n for n, _ in r["ends"]) == sorted([name] + entity["by"])]
            if len(entity["by"]) != 1 or len(rows) != 1 or dict(rows[0]["ends"])[entity["by"][0]] != "1":
                sys.exit(f"{name}: needs one supporting relationship with exactly one {entity['by']}")
            rows[0]["identifying"] = True
    used = {name for r in relationships for name in [n for n, _ in r["ends"]] + [r["composite"]] if name}
    if used != set(entities):
        sys.exit(f"Entities without relationships: {sorted(set(entities) - used)}")
    return entities, relationships


def chen_legs(relationship):
    """Chen connector per end, labelled with the end's maximum, 1 or M; minimums are left to the Relationships table."""
    return [f"-{'M' if CARDINALITIES[card][1] else '1'}-" for _, card in relationship["ends"]]


def composite_labels(relationship):
    """Labels of each line of a composite entity, which is one-to-many: 1 at the entity it links, and at the composite
    M when another end has many for that entity, otherwise 1."""
    ends = relationship["ends"]
    return [("1", "M" if any(CARDINALITIES[card][1] for k, (_, card) in enumerate(ends) if k != i) else "1")
            for i in range(len(ends))]


NOTATION = [
    ("1 / M", "Largest number of that entity in the relationship; M is many"),
    ("Double box", "Weak entity: identified only within the entity it belongs to"),
    ("Double diamond", "Supporting relationship of a weak entity and the entity it belongs to"),
    ("Diamond in a box", "Composite (associative) entity: identified by the entities it links, each one-to-many"),
]


def chen_legend(with_external):
    """Legend of an area diagram."""
    rows = ["|= Notation |= Meaning |"] + [f"| {notation} | {meaning} |" for notation, meaning in NOTATION]
    if with_external:
        rows.append("|<#E8E8E8> Grey box | Entity of another area |")
    return "legend right\n" + "\n".join(rows) + "\nendlegend"


def nodes_of(relationship):
    """The entities a relationship draws: its ends, and the composite entity that stands for it."""
    names = [name for name, _ in relationship["ends"]]
    return names + [relationship["composite"]] if relationship["composite"] else names


def inscribe_diamonds(svg_path, names):
    """Draw the diamond of each composite entity inside its box; PlantUML's Chen notation has no composite entity."""
    svg = svg_path.read_text(encoding="utf-8")
    for name in names:
        at = svg.find(f">{name}</text>")
        if at < 0:
            continue
        start = svg.rindex("<rect ", 0, at)
        end = svg.index("/>", start) + 2
        x, y, width, height = (float(re.search(rf'\b{key}="([^"]+)"', svg[start:end]).group(1))
                               for key in ("x", "y", "width", "height"))
        points = (f"{x + width / 2:.2f},{y:.2f} {x + width:.2f},{y + height / 2:.2f} "
                  f"{x + width / 2:.2f},{y + height:.2f} {x:.2f},{y + height / 2:.2f}")
        # Drawn before the box's text, faint, so the text reads over it
        diamond = f'<polygon fill="none" points="{points}" style="stroke:{LINE};stroke-width:1;stroke-opacity:{DIAMOND_OPACITY};"/>'
        svg = svg[:end] + diamond + svg[end:]
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


def svg_path_points(d):
    """Points along an SVG path of M, L and C commands, with ten points on each curve."""
    values, points, command = [], [], None
    for token in re.findall(r"[MLC]|-?\d+(?:\.\d+)?", d):
        if token in ("M", "L", "C"):
            command = token
            continue
        values.append(float(token))
        if command in ("M", "L") and len(values) == 2:
            points.append((values[0], values[1]))
            values = []
        elif command == "C" and len(values) == 6:
            (x0, y0), (x1, y1, x2, y2, x3, y3) = points[-1], values
            for k in range(1, 11):
                t = k / 10
                a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                points.append((a * x0 + b * x1 + c * x2 + e * x3, a * y0 + b * y1 + c * y2 + e * y3))
            values = []
    return points


def label_composite_lines(svg_path, legs):
    """Write the two labels of each composite entity's line in a PlantUML area diagram, which draws one per line.

    The labels are placed like the overview's, clear of the boxes, diamonds, labels and lines PlantUML drew.
    """
    svg = svg_path.read_text(encoding="utf-8")
    shapes, fixed, lines = {}, [], []

    def attribute(text, key):
        return float(re.search(rf'\b{key}="([^"]+)"', text).group(1))

    for k, rect in enumerate(re.findall(r"<rect ([^>]*)/>", svg)):
        shapes[f"E{k}"] = tuple(attribute(rect, key) for key in ("x", "y", "width", "height"))
    for k, polygon in enumerate(re.findall(r'<polygon [^>]*points="([^"]+)"', svg)):
        values = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", polygon)]
        xs, ys = values[0::2], values[1::2]
        shapes[f"R{k}"] = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    for text in re.findall(r'<text ([^>]*font-size="11"[^>]*)>', svg):
        fixed.append((attribute(text, "x") + attribute(text, "textLength") / 2, attribute(text, "y") - 4))
    by_path = {leg["path"]: leg for leg in legs}
    for d, identifier in re.findall(r'<path d="([^"]+)"[^>]*id="([^"]+)"', svg):
        points = svg_path_points(d)
        line = {"id": identifier, "points": points, "ends": tuple(identifier.split("-")), "labels": []}
        leg = by_path.get(identifier)
        if leg:
            at = svg.index(f">{leg['composite']}</text>")
            x, y, width, height = (attribute(svg[svg.rindex("<rect ", 0, at):at], key)
                                   for key in ("x", "y", "width", "height"))

            def gap(point, x=x, y=y, width=width, height=height):
                return math.hypot(max(x - point[0], 0, point[0] - x - width), max(y - point[1], 0, point[1] - y - height))
            composite_end = int(gap(points[-1]) < gap(points[0]))
            line["labels"] = sorted([(1 - composite_end, leg["own"]), (composite_end, leg["at_composite"])])
        lines.append(line)
    centres = place_labels(lines, shapes, fixed)
    for i, line in enumerate(lines):
        texts = "".join(f'<text fill="#000000" font-family="sans-serif" font-size="11" text-anchor="middle" '
                        f'x="{centres[(i, end)][0]:.2f}" y="{centres[(i, end)][1] + 4:.2f}">{text}</text>'
                        for end, text in line["labels"])
        if texts:
            at = svg.index("/>", svg.index(f'id="{line["id"]}"')) + 2
            svg = svg[:at] + texts + svg[at:]
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


def area_diagram(title, area, entities, relationships):
    """Chen diagram of one area: its relationships, with the other areas' entities in grey.

    Returns the PlantUML source and the lines of composite entities, whose labels label_composite_lines writes.
    """
    chosen = [r for r in relationships if any(entities[name]["area"] == area for name in nodes_of(r))]
    names = sorted({name for r in chosen for name in nodes_of(r)}, key=list(entities).index)
    alias = {name: f"E{i}" for i, name in enumerate(names, 1)}
    external = [name for name in names if entities[name]["area"] != area]
    lines = ["@startchen", "' Generated by erd_diagram.py from readme.md.", CHEN_STYLE, f"title Conceptual ERD — {title}"]
    for name in names:
        entity = entities[name]
        stereotype = (" <<weak>>" if entity["kind"] == "Weak" else "") + (" <<ext>>" if name in external else "")
        lines.append(f'entity "{name}\\n<size:10><i>{entity["vi"]}</i></size>" as {alias[name]}{stereotype} {{\n}}')
    centre = {}
    for i, relationship in enumerate(chosen, 1):
        if relationship["composite"]:
            centre[i] = alias[relationship["composite"]]
        else:
            centre[i] = f"R{i}"
            stereotype = " <<identifying>>" if relationship["identifying"] else ""
            lines.append(f'relationship "{relationship["label"]}" as R{i}{stereotype} <<rel>> {{\n}}')
    legs = []
    for i, relationship in enumerate(chosen, 1):
        composite = relationship["composite"]
        labels = composite_labels(relationship) if composite else [(leg, None) for leg in chen_legs(relationship)]
        # End 1 points into the diamond and the other ends out of it, so dot ranks the diagram top to bottom
        for position, ((name, _), (leg, at_composite)) in enumerate(zip(relationship["ends"], labels)):
            pair = (alias[name], centre[i]) if position == 0 else (centre[i], alias[name])
            if composite:
                # PlantUML draws one label per line, so a composite's line is drawn bare and labelled afterwards
                legs.append({"path": "-".join(pair), "composite": composite, "own": leg, "at_composite": at_composite})
                leg = "--"
            lines.append(f" {leg} ".join(pair))
    lines += [chen_legend(bool(external)), "@endchen", ""]
    return "\n".join(lines), legs


def overview_nodes(entities, relationships):
    """Overview nodes and relationship ends: a hub end whose other end is in another area becomes a copy of the hub."""
    nodes = {name: dict(entity, ghost=False) for name, entity in entities.items()}
    drawn = []
    for relationship in relationships:
        ends = [name for name, _ in relationship["ends"]]
        if len(ends) == 2 and ends[0] != ends[1]:
            for side, (hub, other) in enumerate(((ends[0], ends[1]), (ends[1], ends[0]))):
                if hub in HUBS and entities[hub]["area"] != entities[other]["area"]:
                    copy = f"{hub}#{relationship['number']}"
                    nodes[copy] = dict(entities[hub], area=entities[other]["area"], ghost=True)
                    ends[side] = copy
        drawn.append(dict(relationship, nodes=ends))
    return nodes, drawn


def segments_cross(p1, p2, q1, q2, np):
    """Matrix: segment p1p2[i] properly crosses q1q2[j]."""
    def orient(a, b, c):
        return np.sign((b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0]))
    a, b, c, d = p1[:, None], p2[:, None], q1[None], q2[None]
    return (orient(a, b, c) * orient(a, b, d) < 0) & (orient(c, d, a) * orient(c, d, b) < 0)


def segments_hit_boxes(p1, p2, centers, halves, np):
    """Matrix: segment i passes through box j (slab method)."""
    direction = (p2 - p1)[:, None]
    low = centers[None] - halves[None] + 1 - p1[:, None]
    high = centers[None] + halves[None] - 1 - p1[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        t1, t2 = low / direction, high / direction
    inside = (low <= 0) & (high >= 0)
    t_min = np.where(direction == 0, np.where(inside, -np.inf, np.inf), np.minimum(t1, t2))
    t_max = np.where(direction == 0, np.where(inside, np.inf, -np.inf), np.maximum(t1, t2))
    return np.maximum(t_min.max(axis=2), 0) < np.minimum(t_max.min(axis=2), 1)


def box_half(name, node):
    """Half width and height of a node box in points, from its two lines of text."""
    label = name.split("#")[0]
    return max(len(label) * 7.6, len(node["vi"]) * 5.4) / 2 + 19, 26.0


def pairs_of(drawn, index):
    """Node pairs the layout keeps close, each with whether a diamond lies between them.

    Both ends of a binary relationship and every two ends of a three-way one have a diamond between them; a composite
    entity is joined to each entity it links directly.
    """
    pairs = {}
    for relationship in drawn:
        ends = [index[name] for name in relationship["nodes"]]
        if relationship["composite"]:
            for end in ends:
                pairs.setdefault(tuple(sorted((end, index[relationship["composite"]]))), False)
            continue
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                if ends[i] != ends[j]:
                    pairs[tuple(sorted((ends[i], ends[j])))] = True
    return sorted(pairs.items())


class Grid:
    """Cost of placing the overview nodes on grid cells: crossings, lines through boxes, length."""

    def __init__(self, nodes, drawn, np):
        self.np = np
        self.names = list(nodes)
        self.index = {name: i for i, name in enumerate(self.names)}
        pairs = pairs_of(drawn, self.index)
        self.a = np.array([pair[0] for pair, _ in pairs])
        self.b = np.array([pair[1] for pair, _ in pairs])
        self.has_diamond = np.array([diamond for _, diamond in pairs])
        self.share = ((self.a[:, None] == self.a[None]) | (self.a[:, None] == self.b[None])
                      | (self.b[:, None] == self.a[None]) | (self.b[:, None] == self.b[None]))
        self.halves = np.array([box_half(n, nodes[n]) for n in self.names])
        self.not_end = np.ones((len(pairs), len(self.names)), bool)
        self.not_end[np.arange(len(pairs)), self.a] = False
        self.not_end[np.arange(len(pairs)), self.b] = False
        self.diamond = np.full((len(pairs), 2), [55.0, 30.0])
        self.not_self = ~np.eye(len(pairs), dtype=bool)

    def xy(self, cells):
        """Cell numbers to centre points."""
        return self.np.stack([(cells % COLS) * CELL_W, (cells // COLS) * CELL_H], axis=1).astype(float)

    def cost(self, cells):
        """Weighted cost of a placement."""
        np = self.np
        xy = self.xy(cells)
        p1, p2 = xy[self.a], xy[self.b]
        crossings = int(np.triu(segments_cross(p1, p2, p1, p2, np) & ~self.share, 1).sum())
        through = int((segments_hit_boxes(p1, p2, xy, self.halves, np) & self.not_end).sum())
        middles = (p1 + p2) / 2
        through += int((segments_hit_boxes(p1, p2, middles, self.diamond, np) & self.not_self & self.has_diamond[None]).sum())
        near = np.all(np.abs(middles[:, None] - xy[None]) < self.diamond[:, None] + self.halves[None], axis=2)
        through += int((near & self.has_diamond[:, None]).sum())
        delta = (p2 - p1) / [CELL_W, CELL_H]
        return crossings * 10 + through * 60 + float(np.hypot(delta[:, 0], delta[:, 1]).sum())


def anneal(seed, steps):
    """One simulated-annealing run from a Kamada-Kawai start snapped to the grid; returns (cost, positions)."""
    import networkx as nx
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    entities, relationships = read_model()
    nodes, drawn = overview_nodes(entities, relationships)
    grid = Grid(nodes, drawn, np)
    count = len(grid.names)
    graph = nx.Graph()
    graph.add_nodes_from(range(count))
    graph.add_edges_from(zip(grid.a, grid.b))
    start = nx.kamada_kawai_layout(graph, pos=nx.spring_layout(graph, seed=seed))
    points = np.array([start[i] for i in range(count)])
    points = (points - points.min(0)) / (points.max(0) - points.min(0)) * [COLS - 1, ROWS - 1]
    cells_xy = np.array([(c % COLS, c // COLS) for c in range(COLS * ROWS)], float)
    rows, columns = linear_sum_assignment(np.hypot(*(points[:, None] - cells_xy[None]).transpose(2, 0, 1)))
    cells = np.empty(count, int)
    cells[rows] = columns
    rng = random.Random(seed)
    current = best = grid.cost(cells)
    best_cells = cells.copy()
    temperature = 60.0
    for _ in range(steps):
        i = rng.randrange(count)
        target = rng.randrange(COLS * ROWS)
        old = cells[i]
        occupant = np.where(cells == target)[0]
        cells[i] = target
        if len(occupant):
            cells[occupant[0]] = old
        new = grid.cost(cells)
        if new <= current or rng.random() < math.exp((current - new) / temperature):
            current = new
            if new < best:
                best, best_cells = new, cells.copy()
        else:
            cells[i] = old
            if len(occupant):
                cells[occupant[0]] = target
        temperature = max(0.05, temperature * 0.99994)
    columns, rows = best_cells % COLS, best_cells // COLS
    # Drop empty rows and columns so the overview is no wider than it needs to be
    column_rank = {c: k for k, c in enumerate(sorted(set(columns)))}
    row_rank = {r: k for k, r in enumerate(sorted(set(rows)))}
    positions = {name: [column_rank[c], row_rank[r]] for name, c, r in zip(grid.names, columns, rows)}
    return float(best), positions


def diamond_positions(nodes, drawn, points):
    """Diamond centres: middle of the line, spread when two entities share several relationships, beside a self loop."""
    groups = {}
    for relationship in drawn:
        if not relationship["composite"]:
            groups.setdefault(tuple(sorted(set(relationship["nodes"]))), []).append(relationship["number"])
    centres = {}
    lines = [(points[r["nodes"][0]], points[r["nodes"][1]]) for r in drawn
             if not r["composite"] and len(set(r["nodes"])) == 2]
    lines += [(points[name], points[r["composite"]]) for r in drawn if r["composite"] for name in r["nodes"]]
    for key, numbers in groups.items():
        if len(key) == 3:
            centres[numbers[0]] = tuple(sum(points[n][k] for n in key) / 3 for k in (0, 1))
        elif len(key) == 1:
            x, y = points[key[0]]
            options = [(x, y + CELL_H * 0.45), (x + CELL_W * 0.4, y), (x, y - CELL_H * 0.45), (x - CELL_W * 0.4, y)]

            def crowding(option):
                near_box = any(abs(px - option[0]) < 120 and abs(py - option[1]) < 70 for px, py in points.values())
                near_line = sum(distance_to_segment(option, a, b) < 40 for a, b in lines)
                return near_line + 100 * near_box
            for k, number in enumerate(numbers):
                centres[number] = sorted(options, key=crowding)[k]
        else:
            (ax, ay), (bx, by) = points[key[0]], points[key[1]]
            length = math.hypot(bx - ax, by - ay) or 1
            normal = ((ay - by) / length, (bx - ax) / length)
            for k, number in enumerate(numbers):
                shift = (k - (len(numbers) - 1) / 2) * 70
                centres[number] = ((ax + bx) / 2 + normal[0] * shift, (ay + by) / 2 + normal[1] * shift)
    return centres


def distance_to_segment(point, a, b):
    """Distance from a point to a segment."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    length = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0 if not length else max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length))
    return math.hypot(px - ax - t * (bx - ax), py - ay - t * (by - ay))


def overview_diagram(entities, relationships, positions):
    """@startdot overview with every node pinned; each graph attribute on its own line, as PlantUML requires."""
    nodes, drawn = overview_nodes(entities, relationships)
    if set(positions) != set(nodes):
        sys.exit("overview-layout.json does not match the tables; run with --relayout")
    points = {name: (column * CELL_W, row * CELL_H) for name, (column, row) in positions.items()}
    top = max(y for _, y in points.values()) + CELL_H
    colours = {title: colour for title, _, colour in AREAS}

    def pin(point):
        return f'"{point[0]:.0f},{top - point[1]:.0f}!"'

    alias = {name: f"E{i}" for i, name in enumerate(nodes)}
    out = ["@startdot", "graph G {", "layout=neato", "inputscale=72", "splines=false", "overlap=true",
           "outputorder=nodesfirst", 'fontname="Arial"', "label=<<b>Conceptual ERD — Overview</b>>", "labelloc=t",
           "fontsize=22", f'node [fontname="Arial", color="{LINE}"]', f'edge [fontname="Arial", fontsize=11, color="{LINE}"]']
    for name, node in nodes.items():
        style = (f'style="filled,dashed", fillcolor="{GHOST_FILL}"' if node["ghost"]
                 else f'style=filled, fillcolor="{colours[node["area"]]}"')
        # The class names the kind for drawio_from_svg; a weak entity is a double box
        kind = f', class={node["kind"].lower()}' + (", peripheries=2" if node["kind"] == "Weak" else "")
        out.append(f'{alias[name]} [shape=box, {style}{kind}, pos={pin(points[name])}, label=<<font point-size="14">'
                   f'{name.split("#")[0]}</font><br/><font point-size="10"><i>{node["vi"]}</i></font>>]')
    centres = diamond_positions(nodes, drawn, points)
    for relationship in drawn:
        if relationship["composite"]:
            continue
        label = "\\n".join(textwrap.wrap(relationship["label"], 12))
        double = ", class=identifying, peripheries=2" if relationship["identifying"] else ""
        out.append(f'R{relationship["number"]} [shape=diamond, style=filled, fillcolor="#FFF3E0", fontsize=10, '
                   f'margin=0.01{double}, label="{label}", pos={pin(centres[relationship["number"]])}]')
    for relationship in drawn:
        if relationship["composite"]:
            for name, (own, composite) in zip(relationship["nodes"], composite_labels(relationship)):
                out.append(f'{alias[name]} -- {alias[relationship["composite"]]} '
                           f'[taillabel="{own}", headlabel="{composite}"]')
            continue
        for name, leg in zip(relationship["nodes"], chen_legs(relationship)):
            out.append(f'{alias[name]} -- R{relationship["number"]} [taillabel="{leg[1]}"]')
    rows = "".join(f'<tr><td>{notation}</td><td align="left">{meaning}</td></tr>' for notation, meaning in NOTATION)
    rows += "".join(f'<tr><td bgcolor="{colour}">{title}</td><td align="left">Entity of this area</td></tr>'
                    for title, _, colour in AREAS)
    right = max(x for x, _ in points.values())
    out.append('legend [shape=plaintext, label=<<table border="1" cellborder="1" cellspacing="0" cellpadding="4">'
               f'<tr><td><b>Notation</b></td><td><b>Meaning</b></td></tr>{rows}'
               f'<tr><td bgcolor="{GHOST_FILL}">Grey dashed box</td><td align="left">Copy of Signature or '
               'ChangeRequest next to the area that uses it</td></tr>'
               f'</table>>, pos={pin((right - CELL_W * 0.3, top - CELL_H * 0.1))}]')
    out += ["}", "@enddot", ""]
    return "\n".join(out)


def render(plantuml, path):
    """Render one .puml to SVG; PlantUML fails when given several @startdot files at once."""
    subprocess.run(["java", "-DPLANTUML_LIMIT_SIZE=16384", "-jar", plantuml, "-tsvg", "-charset", "UTF-8", str(path)],
                   check=True)


def svg_quality(path):
    """Crossing pairs and lines through boxes, measured on the polygons and paths of a rendered Graphviz SVG."""
    namespace = {"s": "http://www.w3.org/2000/svg"}
    root = ET.parse(path).getroot()
    boxes, edges = {}, []
    for group in root.iter("{http://www.w3.org/2000/svg}g"):
        title = group.find("s:title", namespace)
        if title is None:
            continue
        shapes = []
        for element in group:
            if element.tag.endswith(("polygon", "path")):
                numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", element.get("points") or element.get("d"))]
                shapes.append(list(zip(numbers[0::2], numbers[1::2])))
        classes = (group.get("class") or "").split()
        if "node" in classes and title.text != "legend":
            # A double box or diamond has two outlines; lines end at the outer one
            boxes[title.text] = max(shapes, key=lambda s: max(p[0] for p in s) - min(p[0] for p in s))[:-1]
        elif "edge" in classes:
            edges.append((title.text.split("--"), [p for shape in shapes for p in shape]))

    def inside(point, polygon):
        x, y = point
        hit = False
        for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
        return hit

    def shrunk(polygon):
        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)
        return [(x - (x - cx) * 0.03, y - (y - cy) * 0.03) for x, y in polygon]

    def cross(a, b, c, d):
        def side(p, q, r):
            value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
            return (value > 1e-9) - (value < -1e-9)
        return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0

    through = 0
    for ends, line in edges:
        for name, polygon in boxes.items():
            if name in ends or len(polygon) < 3:
                continue
            polygon = shrunk(polygon)
            if any(inside((x1 + (x2 - x1) * t / 20, y1 + (y2 - y1) * t / 20), polygon)
                   for (x1, y1), (x2, y2) in pairwise(line) for t in range(21)):
                through += 1
    crossings = sum(1 for i, (ends_a, a) in enumerate(edges) for ends_b, b in edges[i + 1:]
                    if not set(ends_a) & set(ends_b)
                    and any(cross(p, q, r, s) for p, q in pairwise(a) for r, s in pairwise(b)))
    return crossings, through


LABEL_HALF = (4.5, 7.0)  # half width and height of a one-character 11 px label
LABEL_ALONG = (11, 16, 22, 30, 40, 52, 66, 80, 96, 112, 130)  # distances from the entity border along the line
LABEL_ACROSS = (10, 14, 18, 7)  # distances from the line, tried on both sides; 7 only where nothing else is clear
LABEL_CLEARANCE = 11  # a label centre closer than this to another line touches it
LABEL_NEAREST = 4  # every other line is at least this much further from the label than its own line


def point_along(points, distance):
    """Point at a distance along a polyline from its first point, and the unit direction of the line there.

    Past the last point the polyline is extended along its last segment.
    """
    segments = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in pairwise(points)]
    segments = [segment for segment in segments if segment[2]] or [(points[0], points[-1], 1.0)]
    for k, ((ax, ay), (bx, by), length) in enumerate(segments):
        if distance <= length or k == len(segments) - 1:
            t = distance / length
            return ax + (bx - ax) * t, ay + (by - ay) * t, (bx - ax) / length, (by - ay) / length
        distance -= length


def distance_to_line(point, points):
    """Distance from a point to a polyline."""
    return min(distance_to_segment(point, a, b) for a, b in pairwise(points))


def place_labels(lines, shapes, fixed=()):
    """Centre of each 1 / M label: beside its line just outside the entity, clear of shapes, labels and other lines.

    Each line has its points from one end to the other, the shapes at its two ends, and its labels as (end, text), end 0
    at the first point and 1 at the last. `fixed` holds the centres of labels already drawn. Every candidate gets a
    cost; a label over a shape or another label costs most, a label that touches another line or is not clearly
    nearest to its own line less, and a label further from the entity a little more. The most crowded entities are
    placed first. Returns the centres by (line index, end).
    """
    def overlaps_box(cx, cy, box, margin):
        x, y, width, height = box
        return (x - margin < cx + LABEL_HALF[0] and cx - LABEL_HALF[0] < x + width + margin
                and y - margin < cy + LABEL_HALF[1] and cy - LABEL_HALF[1] < y + height + margin)

    def in_diamond(cx, cy, box):
        x, y, width, height = box
        mx, my = x + width / 2, y + height / 2
        return any(abs(px - mx) / (width / 2 + 2) + abs(py - my) / (height / 2 + 2) <= 1
                   for px in (cx - LABEL_HALF[0], cx + LABEL_HALF[0]) for py in (cy - LABEL_HALF[1], cy + LABEL_HALF[1]))

    tasks = [(i, end) for i, line in enumerate(lines) for end, _ in line["labels"]]
    crowd = {}
    for i, end in tasks:
        crowd[lines[i]["ends"][end]] = crowd.get(lines[i]["ends"][end], 0) + 1
    tasks.sort(key=lambda task: -crowd[lines[task[0]]["ends"][task[1]]])
    placed, centres = list(fixed), {}
    for i, end in tasks:
        points = lines[i]["points"] if end == 0 else lines[i]["points"][::-1]
        best = None
        for along in LABEL_ALONG:
            x, y, ux, uy = point_along(points, along)
            for across in LABEL_ACROSS:
                for side in (1, -1):
                    cx, cy = x - uy * across * side, y + ux * across * side
                    cost = along * 0.5 + across * 0.2 + (100 if across < 10 else 0)
                    cost += 1000 * sum(in_diamond(cx, cy, shape) if name.startswith("R")
                                       else overlaps_box(cx, cy, shape, 2) for name, shape in shapes.items())
                    cost += 1000 * sum(overlaps_box(cx, cy, (px - LABEL_HALF[0], py - LABEL_HALF[1],
                                                              2 * LABEL_HALF[0], 2 * LABEL_HALF[1]), 2)
                                       for px, py in placed)
                    # The second line of a self relationship counts too, so each label goes on the outer side
                    cost += 300 * sum(distance_to_line((cx, cy), other["points"])
                                      < max(LABEL_CLEARANCE, across + LABEL_NEAREST)
                                      for k, other in enumerate(lines) if k != i)
                    if best is None or cost < best[0]:
                        best = (cost, cx, cy)
        centres[(i, end)] = best[1:]
        placed.append(best[1:])
    return centres


def drawio_from_svg(svg_path, drawio_path):
    """Write the rendered overview as a draw.io file with every shape and line where Graphviz put it.

    Lines are connected to their entity and diamond at Graphviz's end points. The 1 / M labels are placed again by
    place_labels, because Graphviz puts many of them over the entity, and belong to their line, so moving a shape in
    draw.io keeps them together.
    """
    namespace = {"s": "http://www.w3.org/2000/svg"}
    root = ET.parse(svg_path).getroot()
    graph = root.find("s:g", namespace)
    tx, ty = (float(n) for n in re.search(r"translate\(([-\d.]+) ([-\d.]+)\)", graph.get("transform")).groups())

    def numbers(text):
        values = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]
        return [(x + tx, y + ty) for x, y in zip(values[0::2], values[1::2])]

    def box(points):
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    def geometry(x, y, width, height):
        return f'<mxGeometry x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" as="geometry"/>'

    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    shapes, edges = {}, []
    title = graph.find("s:text", namespace)
    cells.append(f'<mxCell id="title" value={quoteattr(title.text)} style="text;html=1;fontFamily=Arial;fontSize=22;'
                 f'fontStyle=1;align=center;verticalAlign=middle;" vertex="1" parent="1">'
                 f'{geometry(float(title.get("x")) + tx, float(title.get("y")) + ty - 24, 320, 30)}</mxCell>')
    cell = f"border:1px solid {LINE};padding:4px"
    for group in graph.findall("s:g", namespace):
        name = group.find("s:title", namespace).text
        polygon = group.find("s:polygon", namespace)
        # A double box or diamond has two outlines; the shape spans the outer one
        outline = [p for each in group.findall("s:polygon", namespace) for p in numbers(each.get("points"))]
        texts = group.findall("s:text", namespace)
        classes = (group.get("class") or "").split()
        if "node" in classes and name == "legend":
            x, y, width, height = box(outline)
            rows = "".join(f'<tr><td style="{cell}">{notation}</td><td style="{cell}">{meaning}</td></tr>'
                           for notation, meaning in NOTATION)
            rows += "".join(f'<tr><td style="{cell};background:{colour}">{title}</td>'
                            f'<td style="{cell}">Entity of this area</td></tr>' for title, _, colour in AREAS)
            label = (f'<table style="border-collapse:collapse;font-family:Arial;font-size:14px">'
                     f'<tr><th style="{cell}">Notation</th><th style="{cell}">Meaning</th></tr>{rows}'
                     f'<tr><td style="{cell};background:{GHOST_FILL}">Grey dashed box</td>'
                     f'<td style="{cell}">Copy of Signature or ChangeRequest next to the area that uses it</td></tr>'
                     f'</table>')
            # draw.io lays the HTML table out a little wider than Graphviz, so the legend box grows to the left
            cells.append(f'<mxCell id="legend" value={quoteattr(label)} style="text;html=1;align=left;'
                         f'verticalAlign=top;" vertex="1" parent="1">{geometry(x - 80, y, width + 80, height)}</mxCell>')
        elif "node" in classes:
            x, y, width, height = box(outline)
            if name.startswith("R"):
                label = "<br>".join(t.text for t in texts)
                shape = "shape=rhombus;double=1;" if "identifying" in classes else "shape=rhombus;"
                style = (f"{shape}perimeter=rhombusPerimeter;whiteSpace=wrap;html=1;fillColor=#FFF3E0;"
                         f"strokeColor={LINE};fontFamily=Arial;fontSize=10;")
            else:
                label = (f'<font style="font-size:14px">{texts[0].text}</font><br>'
                         f'<i><font style="font-size:10px">{texts[1].text}</font></i>')
                fill = next(p.get("fill") for p in group.findall("s:polygon", namespace) if p.get("fill") != "none")
                style = (f"{'shape=ext;margin=3;double=1;' if 'weak' in classes else 'rounded=0;'}whiteSpace=wrap;"
                         f"html=1;fillColor={fill};strokeColor={LINE};fontFamily=Arial;spacing=0;")
                if polygon.get("stroke-dasharray"):
                    style += "dashed=1;dashPattern=5 2;"
            cells.append(f'<mxCell id="{name}" value={quoteattr(label)} style="{style}" vertex="1" parent="1">'
                         f'{geometry(x, y, width, height)}</mxCell>')
            if "composite" in classes:
                # A faint, locked diamond inside the box, which moves with it; the name stays readable over it
                cells.append(f'<mxCell id="{name}-diamond" value="" style="shape=rhombus;perimeter=rhombusPerimeter;'
                             f'fillColor=none;strokeColor={LINE};opacity={DIAMOND_OPACITY * 100:.0f};locked=1;'
                             f'pointerEvents=0;" vertex="1" connectable="0" parent="{name}">'
                             f'{geometry(0, 0, width, height)}</mxCell>')
            shapes[name] = (x, y, width, height)
        elif "edge" in classes:
            source, target = name.split("--")
            path = group.find("s:path", namespace)
            points = numbers(path.get("d"))
            start, end = points[0], points[-1]
            # A tail label is nearer the line's start, a head label nearer its end
            labels = []
            for text in texts:
                at = (float(text.get("x")) + tx, float(text.get("y")) + ty)
                labels.append((int(math.dist(at, end) < math.dist(at, start)), text.text))
            edges.append({"id": f"{source}-{target}-{group.get('id')}", "source": source, "target": target,
                          "width": path.get("stroke-width", "1"), "start": start, "end": end,
                          "points": [start, end], "ends": (source, target), "labels": sorted(labels)})
    centres = place_labels(edges, shapes)
    for i, edge in enumerate(edges):
        # Pin both ends where Graphviz drew them, so the two lines of a self relationship stay apart as in the SVG
        anchors = ""
        for prefix, (px, py), name in (("exit", edge["start"], edge["source"]), ("entry", edge["end"], edge["target"])):
            x, y, width, height = shapes[name]
            anchors += (f"{prefix}X={(px - x) / width:.4f};{prefix}Y={(py - y) / height:.4f};"
                        f"{prefix}Dx=0;{prefix}Dy=0;{prefix}Perimeter=0;")
        cells.append(f'<mxCell id="{edge["id"]}" style="endArrow=none;html=1;rounded=0;strokeColor={LINE};'
                     f'strokeWidth={edge["width"]};{anchors}" edge="1" parent="1" source="{edge["source"]}" '
                     f'target="{edge["target"]}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        # draw.io keeps a label on its line: x runs from -1 at the line's start to 1 at its end, plus a pixel offset
        (ax, ay), (bx, by) = edge["start"], edge["end"]
        length = (bx - ax) ** 2 + (by - ay) ** 2 or 1
        for end, text in edge["labels"]:
            cx, cy = centres[(i, end)]
            t = max(0.0, min(1.0, ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / length))
            offset_x, offset_y = cx - (ax + t * (bx - ax)), cy - (ay + t * (by - ay))
            # Without an explicit alignment draw.io puts the label's top left corner, not its centre, on the point
            cells.append(f'<mxCell id="{edge["id"]}-{"head-label" if end else "label"}" value={quoteattr(text)} '
                         f'style="edgeLabel;html=1;align=center;verticalAlign=middle;fontFamily=Arial;fontSize=11;'
                         f'labelBackgroundColor=none;" vertex="1" connectable="0" '
                         f'parent="{edge["id"]}"><mxGeometry x="{2 * t - 1:.4f}" relative="1" as="geometry">'
                         f'<mxPoint x="{offset_x:.2f}" y="{offset_y:.2f}" as="offset"/></mxGeometry></mxCell>')
    width, height = (float(n) for n in root.get("viewBox").split()[2:])
    drawio_path.write_text(
        f'<mxfile><diagram name="Conceptual ERD"><mxGraphModel dx="{width:.0f}" dy="{height:.0f}" grid="0" '
        f'page="1" pageWidth="{width:.0f}" pageHeight="{height:.0f}"><root>{"".join(cells)}</root>'
        f'</mxGraphModel></diagram></mxfile>\n', encoding="utf-8")


def relayout(entities, relationships, plantuml, seeds, workers, steps):
    """Anneal several seeds in parallel, render the three cheapest and keep the one with the fewest measured faults."""
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(anneal, range(1, seeds + 1), [steps] * seeds))
    best = None
    for rank, (cost, positions) in enumerate(sorted(results, key=lambda r: r[0])[:3]):
        candidate = HERE / f".candidate-{rank}.puml"
        candidate.write_text(overview_diagram(entities, relationships, positions), encoding="utf-8")
        render(plantuml, candidate)
        crossings, through = svg_quality(candidate.with_suffix(".svg"))
        print(f"candidate {rank}: cost {cost:.0f}, {crossings} crossings, {through} lines through boxes")
        if best is None or crossings + 3 * through < best[0]:
            best = (crossings + 3 * through, positions)
        candidate.unlink()
        candidate.with_suffix(".svg").unlink()
    LAYOUT.write_text(json.dumps({"positions": best[1]}, indent=1) + "\n", encoding="utf-8")


def main():
    """Read the tables, optionally search a new overview layout, write and render every diagram."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--plantuml", required=True, help="path to plantuml.jar")
    parser.add_argument("--drawio", default="drawio", help="draw.io desktop executable, which exports the overview")
    parser.add_argument("--relayout", action="store_true")
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--steps", type=int, default=150000)
    args = parser.parse_args()
    entities, relationships = read_model()
    if args.relayout:
        relayout(entities, relationships, args.plantuml, args.seeds, args.workers, args.steps)
    positions = json.loads(LAYOUT.read_text(encoding="utf-8"))["positions"]
    outputs = [(HERE / "conceptual.puml", overview_diagram(entities, relationships, positions), [])]
    outputs += [(HERE / f"conceptual-{slug}.puml", *area_diagram(title, title, entities, relationships))
                for title, slug, _ in AREAS]
    composites = [name for name, entity in entities.items() if entity["kind"] == "Composite"]
    for path, source, legs in outputs:
        path.write_text(source, encoding="utf-8", newline="\n")
        render(args.plantuml, path)
        if path.stem != "conceptual":
            inscribe_diamonds(path.with_suffix(".svg"), composites)
            label_composite_lines(path.with_suffix(".svg"), legs)
    # The Graphviz rendering of the overview gives the positions and the crossing count; the published SVG is the
    # draw.io export, whose 1 / M labels stay clear of the shapes
    graphviz = HERE / ".conceptual-graphviz.svg"
    exported = HERE / "conceptual.svg"
    exported.replace(graphviz)
    drawio_from_svg(graphviz, HERE / "conceptual.drawio")
    crossings, through = svg_quality(graphviz)
    graphviz.unlink()
    subprocess.run([args.drawio, "-x", "-f", "svg", "-o", str(exported), str(HERE / "conceptual.drawio")],
                   check=True, capture_output=True)
    # draw.io gives the exported SVG a random id; a fixed one keeps a regenerated file unchanged
    exported.write_text(re.sub(r"ge-svg-[\w-]+", "ge-svg-conceptual", exported.read_text(encoding="utf-8")),
                        encoding="utf-8", newline="\n")
    print(f"{len(entities)} entities, {len(relationships)} relationships; overview: {crossings} crossings, "
          f"{through} lines through boxes")


if __name__ == "__main__":
    main()
