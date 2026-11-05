"""Draw the system activity diagram from the activity diagrams of business-flows.md.

Every flow of docs/functional/business-flows.md becomes a frame of its own: an activity with only the lanes it uses,
in one lane order for every frame. No line runs from one frame to another. A flow hands its work over at a flow
final (⊗) named after the flows that take it, or at its activity final (◉), and a flow that takes work starts at an
initial node (●) named after the flows that give it. The second page is the system activity map: one box per flow,
the events that start flows on their own, and one arrow per pair of flows that a join connects. Each frame is also
written on its own to the flows folder.
Run: python docs/reports/activity-diagram/activity_diagram.py
     python docs/reports/activity-diagram/activity_diagram.py --split   (only splits the sheet already written)
"""

import heapq
import random
import re
import shutil
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from collections import defaultdict
from itertools import combinations, permutations
from pathlib import Path
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FLOWS_MD = ROOT / "docs" / "functional" / "business-flows.md"
DRAWIO = HERE / "system-activity-diagram.drawio"
SHEET_SVG = HERE / "system-activity-diagram.svg"
MAP_SVG = HERE / "system-activity-map.svg"
PDF = HERE / "system-activity-diagram.pdf"
README = HERE / "readme.md"
FLOWS_DIR = HERE / "flows"

LANE_ORDER = [
    "Customer",
    "Sales",
    "Head of Sales",
    "Accountant",
    "Administrator",
    "System",
    "Head of Department",
    "Tester",
    "Sample Delivery Staff",
    "Lab Head",
    "Subcontractor",
]
# node fill, node border, lane body
COLORS = {
    "Customer": ("#DBEAFE", "#1D4ED8", "#F5F8FF"),
    "Sales": ("#DCFCE7", "#15803D", "#F4FBF6"),
    "Head of Sales": ("#86EFAC", "#166534", "#F0FAF3"),
    "Accountant": ("#FEF08A", "#A16207", "#FFFDF2"),
    "Administrator": ("#CBD5E1", "#334155", "#F6F7F9"),
    "System": ("#FFFFFF", "#475569", "#F8FAFC"),
    "Head of Department": ("#E9D5FF", "#7E22CE", "#FBF7FF"),
    "Tester": ("#A5F3FC", "#0E7490", "#F2FDFF"),
    "Sample Delivery Staff": ("#FED7AA", "#C2410C", "#FFF8F2"),
    "Lab Head": ("#FBCFE8", "#BE185D", "#FFF6FA"),
    "Subcontractor": ("#D6C4B8", "#5D4037", "#FAF7F4"),
}

# A join is where business-flows.md says that one flow starts or continues another:
# (from flow, from node, to flow, to node, dashed, guard, why).
JOINS = [
    ("SF-08", "ready", "WF-01", "c1", False, "", "WF-01 starts from a catalog with priced parameters and packages."),
    ("SF-09", "c2", "WF-01", "c1", False, "", "WF-01 trigger: a customer submits a cart on the portal."),
    ("WF-01", "c1", "SF-07", "c1", True, "requested date or priority",
     "SF-07 trigger: a customer asks for earlier results; US-C22 asks while ordering."),
    ("WF-01", "s2", "SF-07", "s1", True, "estimate the return date",
     "SF-07 main path: Sales checks the estimated return date while quoting."),
    ("WF-01", "c2", "SF-02", "c1", True, "the customer wants to cancel",
     "SF-02 trigger: a customer wants to cancel an order; it starts from orders in each status."),
    ("SF-07", "cancel", "SF-02", "c3", False, "", "SF-07-E1: Sales handles a cancellation request for the unfulfillable part."),
    ("WF-01", "done", "WF-02", "c1", False, "", "WF-02 starts from a confirmed order whose test request is paid."),
    ("WF-02", "done", "WF-03", "queue", False, "",
     "WF-02 result: testing tasks wait in each department's queue; WF-03 trigger: a testing task enters the queue."),
    ("WF-02", "h2", "SF-11", "h1", True, "sample folders",
     "SF-11 trigger: a sample needs its folders; the head of department creates them."),
    ("WF-03", "queue", "SF-10", "q", True, "", "SF-10 trigger: testing work arrives."),
    ("WF-03", "wf04", "WF-04", "t1", False, "", "WF-04 trigger: a booked test starts."),
    ("WF-03", "dates", "SF-07", "s1", False, "", "WF-03-E2: SF-07 handles the committed return date."),
    ("SF-10", "date", "SF-07", "s1", False, "", "SF-10-E2: Sales records the customer's agreement to a new date."),
    ("WF-03", "outsource", "WF-05", "h1", False, "", "WF-03-E2: WF-05 handles an agreed subcontracted alternative."),
    ("WF-03", "outsource", "WF-05", "h0", False, "", "WF-05-A3: the head initiates an urgent outsourcing proposal."),
    ("SF-10", "outsource", "WF-05", "h1", False, "", "SF-10-E2: a proposed different way follows WF-05."),
    ("SF-07", "urgent", "SF-10", "slot", False, "", "SF-07-A1: accepted priority makes tests urgent; SF-10 owns priority order."),
    ("SF-05", "q", "SF-10", "slot", False, "", "SF-05: SF-10 owns queue order and rescheduling."),
    ("SF-11", "work", "WF-04", "f1", False, "", "SF-11: WF-04 owns saving and versioning result files."),
    ("WF-04", "wf06", "WF-06", "p1", False, "",
     "WF-06 trigger: every sample test of a test request is approved or cancelled."),
    ("WF-05", "done", "WF-06", "p1", False, "",
     "WF-05 result: the subcontractor's result is approved like any other result."),
    ("WF-04", "wf06", "SF-01", "a1", False, "", "SF-01 starts from orders with a paid advance whose testing is completed."),
    ("WF-06", "wf04", "WF-04", "h1", False, "", "WF-06-E2: the results go back to the head of department and are approved again."),
    ("WF-06", "issued", "SF-04", "start", False, "", "SF-04 trigger: the report of a sample's test request is issued."),
    ("WF-04", "done", "SF-03", "r1", True, "a mistake after completion",
     "SF-03 trigger: a person who can edit a result finds a mistake once its process is completed."),
    ("WF-06", "issued", "SF-03", "r1", True, "a mistake in the issued report",
     "SF-03 trigger: a person who can edit a report finds a mistake in an issued one."),
    ("WF-06", "c2", "SF-09", "c5", True, "", "SF-09-A4: the customer rates a completed order; the order completes on issue."),
]

# Where a supporting flow sits on the sheet: the core flow it stands beside, and its column
# (negative on the left of the core flows, positive on the right).
PLACEMENT = {
    "SF-08": ("WF-01", -1),
    "SF-06": ("WF-01", -2),
    "SF-09": ("WF-01", -1),
    "SF-07": ("WF-01", 1),
    "SF-02": ("WF-01", 2),
    "SF-11": ("WF-02", -1),
    "SF-10": ("WF-03", 1),
    "SF-05": ("WF-03", 2),
    "SF-01": ("WF-04", 1),
    "SF-03": ("WF-06", -1),
    "SF-04": ("WF-06", 1),
}

# Where each flow stands on the system activity map: (column, row).
MAP_POSITION = {
    "SF-06": (-1, 0), "SF-08": (0, 0), "SF-09": (1, 0),
    "WF-01": (0, 1), "SF-02": (2, 1),
    "WF-02": (0, 2), "SF-07": (2, 2),
    "SF-11": (-1, 3), "WF-03": (0, 3), "SF-10": (2, 3),
    "WF-04": (0, 4), "WF-05": (1, 4), "SF-05": (2, 4),
    "SF-01": (-1, 5), "WF-06": (0, 5),
    "SF-03": (-1, 6), "SF-04": (0, 6),
}
# The event that starts a flow on its own, named after its trigger: (label, column, row, flow).
MAP_EVENTS = [
    ("Accreditation event", -1, -1, "SF-06"),
    ("Laboratory setup", 0, -1, "SF-08"),
    ("Customer contact", 1, -1, "SF-09"),
    ("File administration", -2, 3, "SF-11"),
    ("Each day", -2, 5, "SF-01"),
    ("Plan change", 3, 3, "SF-10"),
    ("Machine event", 3, 4, "SF-05"),
]
MAP_LEGEND = (2, 6)

GRID = 10
SLOT_W = 240
LANE_PAD = 20
NODE_W = 200
TITLE_H = 40
HEADER_H = 30
PAD = 40
VGAP = 60
FRAME_GAP = 80
CHAR_W = 6.8
LINE_H = 15
SMALL = 20  # diameter of the initial and final nodes
MAP_BOX_W, MAP_GAP_X, MAP_GAP_Y, MAP_EVENT_H = 200, 80, 70, 40

LABEL_CHAR_W = 5.6
STEP, BEND, CROSS, NEAR, SHARE, HISTORY = 1.0, 4.0, 5000.0, 0.6, 12.0, 3.0
ATTEMPTS = 60
CLEAN_TRIES = 6

ARROW = re.compile(r"\s*(-->|-\.->)(?:\|([^|]*)\|)?\s*")
NODE_REF = re.compile(r"^(\w+)\s*(\(\[.*\]\)|\[.*\]|\{.*\})?$")
REFERENCE = re.compile(r"^((?:WF|SF)-\d\d) ")
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Node:
    def __init__(self, nid, lane, order):
        self.id, self.lane, self.order = nid, lane, order
        self.kind, self.label = "action", nid
        self.targets = []  # flows a flow final or activity final hands over to
        self.x = self.y = self.w = self.h = 0
        self.rank = 0


class Edge:
    def __init__(self, s, t, label="", dashed=False):
        self.s, self.t, self.label, self.dashed = s, t, label, dashed
        self.points = []
        self.group = None


class Flow:
    def __init__(self, fid, name, trigger):
        self.id, self.name, self.trigger = fid, name, trigger
        self.nodes, self.edges = {}, []
        self.lanes = []
        self.width = self.height = 0
        self.x = self.y = 0
        self.crossings = 0
        self.failures = []


def canonical_lane(name):
    for lane in LANE_ORDER:
        if lane.lower() == name.lower():
            return lane
    raise SystemExit(f"Lane {name!r} is not an actor of the use case diagram")


def read_label(shape):
    if shape.startswith("(["):
        kind, text = "state", shape[2:-2]
    elif shape.startswith("{"):
        kind, text = "decision", shape[1:-1]
    else:
        kind, text = "action", shape[1:-1]
    text = text.strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1]
    return kind, text


def read_flows():
    text = FLOWS_MD.read_text(encoding="utf-8")
    flows = {}
    section = re.compile(r"^## ((?:WF|SF)-\d\d) (.+?)\n(.*?)```mermaid\n(.*?)```", re.S | re.M)
    for fid, name, body, code in section.findall(text):
        trigger = re.search(r"^- \*\*Trigger:\*\* (.+)$", body, re.M).group(1).strip()
        flow = Flow(fid, name.strip(), trigger[0].upper() + trigger[1:])
        lane = None
        for raw in code.splitlines():
            line = raw.strip()
            if not line or line.startswith("flowchart"):
                continue
            sub = re.match(r'subgraph \w+ \["(.+)"\]$', line)
            if sub:
                lane = canonical_lane(sub.group(1))
                continue
            if line == "end":
                lane = None
                continue
            parts = ARROW.split(line)
            ids = []
            for ref in parts[0::3]:
                match = NODE_REF.match(ref.strip())
                if not match:
                    raise SystemExit(f"{fid}: cannot read {ref!r}")
                nid, shape = match.groups()
                if nid not in flow.nodes:
                    flow.nodes[nid] = Node(nid, lane or "System", len(flow.nodes))
                if shape:
                    flow.nodes[nid].kind, flow.nodes[nid].label = read_label(shape)
                ids.append(nid)
            for arrow, label, s, t in zip(parts[1::3], parts[2::3], ids, ids[1:]):
                flow.edges.append(Edge(s, t, (label or "").strip(), arrow == "-.->"))
        flows[fid] = flow
    return flows


def flow_key(fid):
    return (fid[:2] != "WF", fid)


def transform(flows):
    """Turn the references to other flows into flow finals and initial nodes, outcomes into activity finals."""
    preds = {f.id: defaultdict(list) for f in flows.values()}
    succs = {f.id: defaultdict(list) for f in flows.values()}
    for f in flows.values():
        for e in f.edges:
            preds[f.id][e.t].append(e.s)
            succs[f.id][e.s].append(e.t)
    original = {(f.id, n.id): n.label for f in flows.values() for n in f.nodes.values()}

    for j in JOINS:
        for fid, nid in ((j[0], j[1]), (j[2], j[3])):
            if nid not in flows[fid].nodes:
                raise SystemExit(f"Join names {fid} {nid}, which business-flows.md does not have")

    for f in flows.values():
        for n in f.nodes.values():
            if REFERENCE.match(n.label) and not succs[f.id][n.id]:
                n.kind = "flowfinal"
            elif n.kind == "state" and not succs[f.id][n.id]:
                n.kind = "final"

    def source_label(fid, nid):
        node = flows[fid].nodes[nid]
        if node.kind == "flowfinal":
            ps = preds[fid][nid]
            return original[(fid, ps[0])] if len(ps) == 1 else None
        return original[(fid, nid)]

    for f in flows.values():
        handover = {}
        for j in [j for j in JOINS if j[0] == f.id]:
            _, src, dst_flow, _, dashed, guard, _ = j
            node = f.nodes[src]
            if node.kind in ("flowfinal", "final"):
                if dst_flow not in node.targets:
                    node.targets.append(dst_flow)
                continue
            key = (src, dashed, guard)
            if key not in handover:
                out = Node(f"out_{src}_{len(handover)}", node.lane, len(f.nodes))
                out.kind = "flowfinal"
                f.nodes[out.id] = out
                f.edges.append(Edge(src, out.id, guard, dashed))
                handover[key] = out
            if dst_flow not in handover[key].targets:
                handover[key].targets.append(dst_flow)
        for n in f.nodes.values():
            if n.kind == "flowfinal":
                targets = n.targets or [REFERENCE.match(n.label).group(1)]
                n.label = "→ " + ", ".join(sorted(targets, key=flow_key))
            elif n.kind == "final" and n.targets:
                n.label = f"{n.label} → " + ", ".join(sorted(n.targets, key=flow_key))

        incoming = defaultdict(list)
        for j in JOINS:
            if j[2] == f.id:
                incoming[j[3]].append(j)
        for dst, joins in incoming.items():
            sources = sorted({j[0] for j in joins}, key=flow_key)
            label = source_label(joins[0][0], joins[0][1]) if len(joins) == 1 else None
            start = Node(f"in_{dst}", f.nodes[dst].lane, len(f.nodes))
            start.kind = "initial"
            start.label = f"{sources[0]}: {label}" if label else ", ".join(sources)
            f.nodes[start.id] = start
            f.edges.append(Edge(start.id, dst))

        has_in = {e.t for e in f.edges}
        starts = sorted((n for n in f.nodes.values() if n.id not in has_in and n.kind != "initial"),
                        key=lambda n: n.order)
        if starts:
            trigger = Node("trigger", starts[0].lane, len(f.nodes))
            trigger.kind, trigger.label = "initial", f.trigger
            f.nodes[trigger.id] = trigger
            for n in starts:
                f.edges.append(Edge(trigger.id, n.id))

        for n in list(f.nodes.values()):
            into = [e for e in f.edges if e.t == n.id]
            if n.kind in ("flowfinal", "final") and len(into) > 3:
                bar = Node(f"join_{n.id}", n.lane, len(f.nodes))
                bar.kind, bar.label = "join", ""
                f.nodes[bar.id] = bar
                for e in into:
                    e.t = bar.id
                f.edges.append(Edge(bar.id, n.id))
        for n in list(f.nodes.values()):
            if n.kind in ("flowfinal", "final"):
                into = [e for e in f.edges if e.t == n.id]
                lanes = sorted({f.nodes[e.s].lane for e in into}, key=LANE_ORDER.index)
                for k, lane in enumerate(lanes[1:], 1):
                    copy = Node(f"{n.id}_{k}", lane, len(f.nodes))
                    copy.kind, copy.label, copy.targets = n.kind, n.label, list(n.targets)
                    f.nodes[copy.id] = copy
                    for e in into:
                        if f.nodes[e.s].lane == lane:
                            e.t = copy.id
        for n in f.nodes.values():
            if n.kind in ("flowfinal", "final", "join"):
                lanes = {f.nodes[e.s].lane for e in f.edges if e.t == n.id}
                if len(lanes) == 1:
                    n.lane = lanes.pop()
        for i, e in enumerate(f.edges):
            shared = f.nodes[e.s].kind in ("decision", "initial")
            e.group = f"{f.id}:{e.s}" if shared else f"{f.id}:e{i}"
        f.lanes = [lane for lane in LANE_ORDER if any(n.lane == lane for n in f.nodes.values())]


def wrap(text, width):
    chars = max(8, int(width / CHAR_W))
    return textwrap.wrap(text, chars) or [""]


def up(value, step=20):
    return int(-(-value // step) * step)


def size_nodes(f):
    for n in f.nodes.values():
        if n.kind == "decision":
            lines = wrap(n.label, NODE_W * 0.62)
            n.w, n.h = NODE_W, max(80, up(len(lines) * LINE_H * 1.9 + 24))
        elif n.kind in ("action", "state"):
            lines = wrap(n.label, NODE_W - 16)
            n.w, n.h = NODE_W, max(40, up(len(lines) * LINE_H + 14))
        elif n.kind == "join":
            lines = []
            n.w, n.h = NODE_W - 20, GRID
        else:
            lines = wrap(n.label, NODE_W - 10) if n.label else []
            n.w, n.h = NODE_W, up(SMALL + 8 + len(lines) * 14)
        n.lines = len(lines)


def rank_nodes(f):
    order = sorted(f.nodes.values(), key=lambda n: n.order)
    succ, pred = defaultdict(list), defaultdict(list)
    for e in f.edges:
        succ[e.s].append(e.t)
    roots = [n.id for n in order if n.kind == "initial"] + [n.id for n in order if not any(e.t == n.id for e in f.edges)]
    state, back = {}, set()
    for root in roots + [n.id for n in order]:
        if root in state:
            continue
        stack = [(root, iter(succ[root]))]
        state[root] = 1
        while stack:
            u, it = stack[-1]
            v = next(it, None)
            if v is None:
                state[u] = 2
                stack.pop()
            elif state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                state[v] = 1
                stack.append((v, iter(succ[v])))
    forward = [(e.s, e.t) for e in f.edges if (e.s, e.t) not in back]
    for s, t in forward:
        pred[t].append(s)
    topo, seen = [], set()

    def visit(v):
        stack = [(v, iter(pred[v]))]
        while stack:
            u, it = stack[-1]
            w = next(it, None)
            if w is None:
                stack.pop()
                if u not in seen:
                    seen.add(u)
                    topo.append(u)
            elif w not in seen:
                stack.append((w, iter(pred[w])))

    for n in order:
        visit(n.id)
    rank = {}
    for v in topo:
        if f.nodes[v].kind != "initial":
            rank[v] = max([0] + [rank[u] + 1 for u in pred[v] if u in rank])
    for v in topo:
        if f.nodes[v].kind == "initial":
            rank[v] = max(0, min(rank[t] for t in succ[v]) - 1)
    if any(r == 0 for v, r in rank.items() if f.nodes[v].kind != "initial" and any(
            f.nodes[u].kind == "initial" for u in pred[v])):
        rank = {v: r + (f.nodes[v].kind != "initial") for v, r in rank.items()}
    for v, r in rank.items():
        f.nodes[v].rank = r
    f.forward = forward


def assign_slots(group, centre_of, count, wanted, part):
    """Put the nodes of one lane and rank in increasing slots, each as near as it can be to where it is wanted."""
    ordered = sorted(group, key=lambda n: (part[n.id], wanted[n.id]))
    best = None
    for chosen in combinations(range(count), len(ordered)):
        cost = sum(abs(centre_of(j) - wanted[n.id]) for j, n in zip(chosen, ordered))
        if best is None or cost < best[0]:
            best = (cost, chosen)
    return {n.id: j for j, n in zip(best[1], ordered)}


def components(f):
    """Index of the connected part of each node, leaving out the lines from initial nodes."""
    parent = {nid: nid for nid in f.nodes}

    def root(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for e in f.edges:
        if f.nodes[e.s].kind != "initial":
            parent[root(e.s)] = root(e.t)
    for e in f.edges:
        if f.nodes[e.s].kind == "initial" and root(e.s) == e.s:
            parent[e.s] = root(e.t)
    first = {}
    for n in sorted(f.nodes.values(), key=lambda n: n.order):
        first.setdefault(root(n.id), len(first))
    return {nid: first[root(nid)] for nid in f.nodes}


def place_nodes(f):
    part = components(f)
    groups = defaultdict(list)
    for n in sorted(f.nodes.values(), key=lambda n: (part[n.id], n.order)):
        groups[(n.lane, n.rank)].append(n)
    slots = {lane: max(len(g) for (l, _), g in groups.items() if l == lane) for lane in f.lanes}
    f.lane_x, f.lane_w, x = {}, {}, 0
    for lane in f.lanes:
        f.lane_x[lane], f.lane_w[lane] = x, slots[lane] * SLOT_W + 2 * LANE_PAD
        x += f.lane_w[lane]
    f.width = x

    def centre(lane, j):
        return f.lane_x[lane] + LANE_PAD + j * SLOT_W + SLOT_W // 2

    slot = {n.id: j for g in groups.values() for j, n in enumerate(g)}
    above, below = defaultdict(list), defaultdict(list)
    for s_, t in f.forward:
        below[s_].append(t)
        above[t].append(s_)

    def cx(nid):
        return centre(f.nodes[nid].lane, slot[nid])

    ranks = sorted({n.rank for n in f.nodes.values()})
    for sweep in range(8):
        downward = sweep % 2 == 0
        for r in ranks if downward else reversed(ranks):
            for lane in f.lanes:
                group = groups.get((lane, r))
                if not group:
                    continue
                wanted = {}
                for n in group:
                    near = (above if downward else below)[n.id] or (below if downward else above)[n.id]
                    wanted[n.id] = sum(cx(m) for m in near) / len(near) if near else cx(n.id)
                slot.update(assign_slots(group, lambda j, lane=lane: centre(lane, j), slots[lane], wanted, part))
    rows = defaultdict(list)
    for n in f.nodes.values():
        rows[n.rank].append(n)
    top, middle, y = {}, {}, PAD
    for r in sorted(rows):
        height = max(n.h for n in rows[r])
        top[r], middle[r] = (y, height), y + height / 2
        y += height + VGAP
    f.height = y - VGAP + PAD

    def score():
        where = {nid: (cx(nid), middle[n.rank]) for nid, n in f.nodes.items()}
        lines = [(where[e.s], where[e.t], e.s, e.t) for e in f.edges]
        crossings = sum(1 for i, (a, b, s1, t1) in enumerate(lines) for c, d, s2, t2 in lines[i + 1:]
                        if not {s1, t1} & {s2, t2} and segments_cross(a, b, c, d))
        hits = 0
        for a, b, s1, t1 in lines:
            for nid, n in f.nodes.items():
                if nid not in (s1, t1):
                    x0, y0 = where[nid][0] - n.w / 2, where[nid][1] - n.h / 2
                    hits += segment_hits_box(a, b, (x0, y0, x0 + n.w, y0 + n.h))
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b, _, _ in lines)
        return crossings * 100 + hits * 30 + length / 100

    best = score()
    for _ in range(6):
        improved = False
        for (lane, r), group in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if slots[lane] == 1:
                continue
            current = {n.id: slot[n.id] for n in group}
            for chosen in permutations(range(slots[lane]), len(group)):
                if any(part[a.id] < part[b.id] and ja > jb
                       for a, ja in zip(group, chosen) for b, jb in zip(group, chosen)):
                    continue
                for n, j in zip(group, chosen):
                    slot[n.id] = j
                value = score()
                if value < best - 1e-9:
                    best, current, improved = value, {n.id: slot[n.id] for n in group}, True
            slot.update(current)
        if not improved:
            break
    for n in f.nodes.values():
        height = top[n.rank][1]
        n.x = cx(n.id) - n.w // 2
        n.y = top[n.rank][0] + (height - n.h) // 2


def segments_cross(a, b, c, d):
    def side(p, q, r):
        value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (value > 1e-9) - (value < -1e-9)

    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def segment_hits_box(a, b, box):
    x0, y0, x1, y1 = box
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return 0
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return 1 if t0 < t1 else 0


def ports(n):
    """Connection points of a node: (x, y, direction outward, penalty) in grid units."""
    gx, gy, gw, gh = n.x // GRID, n.y // GRID, n.w // GRID, n.h // GRID
    cx = gx + gw // 2
    if n.kind == "decision":
        cy = gy + gh // 2
        return [(cx, gy, (0, -1), 0), (cx, gy + gh, (0, 1), 0), (gx, cy, (-1, 0), 0), (gx + gw, cy, (1, 0), 0)]
    if n.kind == "join":
        return [(cx + o, gy, (0, -1), abs(o) // 3) for o in (0, -3, 3, -6, 6, -8, 8)] + [(cx, gy + gh, (0, 1), 0)]
    if n.kind == "initial":
        top = gy + gh - SMALL // GRID
        cy = top + 1
        return [(cx, gy + gh, (0, 1), 0), (cx - 1, cy, (-1, 0), 1), (cx + 1, cy, (1, 0), 1)]
    if n.kind in ("final", "flowfinal"):
        return [(cx, gy, (0, -1), 0), (cx - 1, gy + 1, (-1, 0), 1), (cx + 1, gy + 1, (1, 0), 1)]
    result = []
    for offset, penalty in ((0, 0), (-3, 1), (3, 1), (-6, 2), (6, 2), (-8, 3), (8, 3)):
        result.append((cx + offset, gy, (0, -1), penalty))
        result.append((cx + offset, gy + gh, (0, 1), penalty))
    middle = gy + gh // 2
    sides = [(middle, 0)] + ([(gy + 1, 2), (gy + gh - 1, 2)] if gh >= 4 else [])
    for yy, penalty in sides:
        result.append((gx, yy, (-1, 0), penalty))
        result.append((gx + gw, yy, (1, 0), penalty))
    return result


def label_width(n):
    longest = max((len(s) for s in wrap(n.label, NODE_W - 10)), default=0)
    return min(NODE_W, up(longest * CHAR_W + 12))


def obstacles(n):
    """Grid boxes a node and its label cover, as (x0, y0, x1, y1) inclusive."""
    gx, gy, gw, gh = n.x // GRID, n.y // GRID, n.w // GRID, n.h // GRID
    if n.kind not in ("initial", "final", "flowfinal"):
        return [(gx, gy, gx + gw, gy + gh)]
    cx, r = gx + gw // 2, SMALL // GRID // 2
    half = label_width(n) // GRID // 2
    if n.kind == "initial":
        circle = (cx - r, gy + gh - 2 * r, cx + r, gy + gh)
        text = (cx - half, gy, cx + half, gy + gh - 2 * r - 1)
    else:
        circle = (cx - r, gy, cx + r, gy + 2 * r)
        text = (cx - half, gy + 2 * r + 1, cx + half, gy + gh)
    return [circle] + ([text] if n.label and text[3] >= text[1] else [])


class Router:
    def __init__(self, width, height, nodes, history=None):
        self.W, self.H = width // GRID, height // GRID
        self.history = history or {}
        self.events = []
        self.length = 0.0
        self.blocked = set()
        for n in nodes:
            for x0, y0, x1, y1 in obstacles(n):
                for x in range(x0 - 1, x1 + 2):
                    for y in range(y0 - 1, y1 + 2):
                        self.blocked.add((x, y))
        self.occ = {}
        self.used = defaultdict(dict)  # node id -> port index -> group
        self.crossings = 0

    def free_ports(self, node, group, outgoing, banned=None):
        result = []
        for i, (x, y, d, penalty) in enumerate(ports(node)):
            if d == banned:
                continue
            owner = self.used[node.id].get(i)
            if owner is not None and not (outgoing and owner == group):
                continue
            if owner is not None:
                penalty += SHARE
            sx, sy = x + 2 * d[0], y + 2 * d[1]
            if not (0 <= sx <= self.W and 0 <= sy <= self.H) or (sx, sy) in self.blocked:
                continue
            o = self.occ.get((sx, sy))
            if o is not None and o[0] != group:
                continue
            result.append((i, x, y, d, penalty, sx, sy))
        return result

    def route(self, src, dst, group):
        forward = dst.rank > src.rank
        starts = self.free_ports(src, group, True, (0, -1) if forward else None)
        goals = {}
        for i, x, y, d, penalty, sx, sy in self.free_ports(dst, group, False, (0, 1) if forward else None):
            goals.setdefault((sx, sy), []).append((i, x, y, d, penalty))
        if not starts or not goals:
            return None
        goal_points = list(goals)

        def h(x, y):
            return min(abs(x - gx) + abs(y - gy) for gx, gy in goal_points) * STEP

        heap, best, parent = [], {}, {}
        for i, x, y, d, penalty, sx, sy in starts:
            state = (sx, sy, d)
            g = penalty + 2 * STEP
            if g < best.get(state, 1e18):
                best[state] = g
                parent[state] = ("start", i, x, y)
                heapq.heappush(heap, (g + h(sx, sy), g, state))
        finish = None
        while heap:
            _, g, state = heapq.heappop(heap)
            if g > best.get(state, 1e18):
                continue
            x, y, d = state
            if (x, y) in goals:
                for i, px, py, pd, penalty in goals[(x, y)]:
                    inward = (-pd[0], -pd[1])
                    total = g + penalty + 2 * STEP + (0 if d == inward else BEND)
                    if d == (-inward[0], -inward[1]):
                        continue
                    if finish is None or total < finish[0]:
                        finish = (total, state, i, px, py)
                if finish and finish[0] <= g + 1e-9:
                    break
                continue
            if finish and g >= finish[0]:
                break
            here = self.occ.get((x, y))
            crossing_here = here is not None and here[0] != group and here[1] in "HV"
            for nd in DIRS:
                if nd == (-d[0], -d[1]) or (crossing_here and nd != d):
                    continue
                nx, ny = x + nd[0], y + nd[1]
                if not (0 <= nx <= self.W and 0 <= ny <= self.H):
                    continue
                if (nx, ny) in self.blocked and (nx, ny) not in goals:
                    continue
                cost = STEP + (BEND if nd != d else 0) + self.history.get((nx, ny), 0)
                o = self.occ.get((nx, ny))
                if o is not None:
                    orient = o[1]
                    across = (orient == "H" and nd[1] != 0) or (orient == "V" and nd[0] != 0)
                    if o[0] == group:
                        if across:
                            continue
                    elif across:
                        if (nx, ny) in goals:
                            continue
                        cost += CROSS
                    else:
                        continue
                for ax, ay in ((nx + 1, ny), (nx - 1, ny), (nx, ny + 1), (nx, ny - 1)):
                    o2 = self.occ.get((ax, ay))
                    if o2 is not None and o2[0] != group:
                        cost += NEAR
                        break
                ns = (nx, ny, nd)
                ng = g + cost
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    parent[ns] = state
                    heapq.heappush(heap, (ng + h(nx, ny), ng, ns))
        if finish is None:
            return None
        total, state, end_port, ex, ey = finish
        path = []
        while True:
            path.append((state[0], state[1]))
            p = parent[state]
            if p[0] == "start":
                start_port, sx, sy = p[1], p[2], p[3]
                break
            state = p
        path.reverse()
        points = [(sx, sy)] + path + [(ex, ey)]
        self.used[src.id][start_port] = group
        self.used[dst.id][end_port] = group
        self.length += total
        self.last_ports = (start_port, end_port)
        return self.commit(points, group)

    def commit(self, points, group):
        cells = [points[0]]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            dx = (x1 > x0) - (x1 < x0)
            dy = (y1 > y0) - (y1 < y0)
            x, y = x0, y0
            while (x, y) != (x1, y1):
                x, y = x + dx, y + dy
                cells.append((x, y))
        for i, cell in enumerate(cells):
            if i == 0 or i == len(cells) - 1:
                orient = "C"
            else:
                a, b = cells[i - 1], cells[i + 1]
                if a[1] == b[1]:
                    orient = "H"
                elif a[0] == b[0]:
                    orient = "V"
                else:
                    orient = "C"
            o = self.occ.get(cell)
            if o is not None and o[0] != group:
                self.crossings += 1
                self.events.append((cell, o[0], group))
                self.occ[cell] = ("#", "X")
            elif o is None or o[0] != group:
                self.occ[cell] = (group, orient)
            elif o[1] != orient:
                self.occ[cell] = (group, "C")
        corners = [cells[0]]
        for i in range(1, len(cells) - 1):
            a, b, c = cells[i - 1], cells[i], cells[i + 1]
            if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
                corners.append(b)
        corners.append(cells[-1])
        return [(x * GRID, y * GRID) for x, y in corners]


def route_edges(width, height, nodes, edges, seed_order):
    best = None
    order = list(seed_order)
    rng = random.Random(7)
    history = defaultdict(float)
    clean = 0
    for attempt in range(ATTEMPTS):
        router = Router(width, height, nodes.values(), history)
        failures, results, cells = [], {}, {}
        for i in order:
            e = edges[i]
            points = router.route(nodes[e.s], nodes[e.t], e.group)
            if points is None:
                failures.append(i)
            else:
                results[i] = (points, router.last_ports)
                cells[e.group] = cells.get(e.group, []) + [i]
        score = (len(failures), router.crossings, router.length)
        if best is None or score < best[0]:
            best = (score, results, failures, router.crossings)
        if not failures and router.crossings == 0:
            clean += 1
            if clean >= CLEAN_TRIES:
                break
            rng.shuffle(order)
            continue
        bad = set(failures)
        for cell, first, second in router.events:
            for g in (first, second):
                bad.update(cells.get(g, []))
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    history[(cell[0] + dx, cell[1] + dy)] += HISTORY
        order = [i for i in order if i in bad] + [i for i in order if i not in bad]
        if attempt % 3 == 2:
            rng.shuffle(order)
    score, results, failures, crossings = best
    for i, (points, used) in results.items():
        edges[i].points, edges[i].ports = points, used
    if not failures and not crossings:
        polish(width, height, nodes, edges)
    return crossings, failures


def cost_of(points):
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(points, points[1:])) / GRID
    return length * STEP + (len(points) - 2) * BEND


def polish(width, height, nodes, edges):
    """Route each line again with every other line in place, keeping the new path when it is shorter."""
    for _ in range(2):
        changed = False
        for i, e in enumerate(edges):
            router = Router(width, height, nodes.values())
            for j, other in enumerate(edges):
                if j != i and other.points:
                    router.used[other.s][other.ports[0]] = other.group
                    router.used[other.t][other.ports[1]] = other.group
                    router.commit([(x // GRID, y // GRID) for x, y in other.points], other.group)
            router.crossings = 0
            points = router.route(nodes[e.s], nodes[e.t], e.group)
            if points and router.crossings == 0 and cost_of(points) < cost_of(e.points) - 0.5:
                e.points, e.ports, changed = points, router.last_ports, True
        if not changed:
            break


def layout_flow(f):
    size_nodes(f)
    rank_nodes(f)
    place_nodes(f)

    def length(i):
        e = f.edges[i]
        a, b = f.nodes[e.s], f.nodes[e.t]
        same = a.lane == b.lane and b.rank == a.rank + 1
        return (not same, abs(a.x - b.x) + abs(a.y - b.y))

    order = sorted(range(len(f.edges)), key=length)
    f.crossings, failures = route_edges(f.width, f.height, f.nodes, f.edges, order)
    f.failures = [f"{f.edges[i].s} -> {f.edges[i].t}" for i in failures]
    placed = []
    f.warnings = []
    for e in f.edges:
        if e.label and e.points:
            e.label_at, clash = place_label(e, f, placed)
            if clash:
                f.warnings.append(f"label {e.label!r} of {e.s} -> {e.t} touches a shape, a line or a label")


def point_at(points, distance):
    walked = 0
    for a, b in zip(points, points[1:]):
        seg = abs(b[0] - a[0]) + abs(b[1] - a[1])
        if walked + seg >= distance and seg:
            t = (distance - walked) / seg
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        walked += seg
    return points[-1]


def overlaps(r1, r2):
    return r1[0] < r2[2] and r2[0] < r1[2] and r1[1] < r2[3] and r2[1] < r1[3]


def place_label(e, f, placed):
    """Where a line's label touches no shape, other line or label; decisions label near the start.

    A long label that finds no free place on one line is tried on two lines.
    """
    words = e.label.split()
    options = [[e.label]]
    if len(words) > 1 and len(e.label) > 12:
        cut = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(e.label) / 2))
        options.append([" ".join(words[:cut]), " ".join(words[cut:])])
    best = None
    for lines in options:
        result = label_spot(e, f, placed, lines)
        if best is None or result[0] < best[0]:
            best = result
        if best[0] == 0:
            break
    clash, at, box, offset, lines = best
    placed.append(box)
    e.label_offset, e.label_lines = offset, lines
    return at, clash


def label_spot(e, f, placed, text_lines):
    total = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(e.points, e.points[1:]))
    width = max(len(t) for t in text_lines) * LABEL_CHAR_W + 8
    height = 13 * len(text_lines) + 2
    shapes = [(x0 * GRID - 2, y0 * GRID - 2, x1 * GRID + 2, y1 * GRID + 2)
              for n in f.nodes.values() for x0, y0, x1, y1 in obstacles(n)]
    lines = []
    for other in f.edges:
        if other is not e and other.points:
            for a, b in zip(other.points, other.points[1:]):
                lines.append((min(a[0], b[0]) - 1, min(a[1], b[1]) - 1, max(a[0], b[0]) + 1, max(a[1], b[1]) + 1))
    distances = list(range(20, int(total) - 9, 5)) or [total / 2]
    if f.nodes[e.s].kind != "decision":
        distances.sort(key=lambda d: abs(d - total / 2))
    candidates = [(d, 0, 0) for d in distances]
    for d in distances:
        a, b = segment_at(e.points, d)
        if a[0] == b[0]:
            candidates += [(d, width / 2 + 4, 0), (d, -width / 2 - 4, 0)]
        else:
            candidates += [(d, 0, -height / 2 - 2), (d, 0, height / 2 + 2)]
    best = None
    for d, dx, dy in candidates:
        x, y = point_at(e.points, d)
        x, y = x + dx, y + dy
        box = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        inside = 0 <= box[0] and box[2] <= f.width and 0 <= box[1] and box[3] <= f.height
        clash = (sum(overlaps(box, r) for r in shapes) * 3 + sum(overlaps(box, r) for r in lines)
                 + sum(overlaps(box, r) for r in placed) * 3 + (0 if inside else 5))
        if best is None or clash < best[0]:
            best = (clash, d, box, dx, dy)
        if clash == 0:
            break
    clash, d, box, dx, dy = best
    return clash, (d / total if total else 0.5), box, (dx, dy), text_lines


def segment_at(points, distance):
    walked = 0
    for a, b in zip(points, points[1:]):
        seg = abs(b[0] - a[0]) + abs(b[1] - a[1])
        if walked + seg >= distance and seg:
            return a, b
        walked += seg
    return points[-2], points[-1]


def place_frames(flows):
    core = [fid for fid in sorted(flows, key=flow_key) if fid.startswith("WF")]
    columns = defaultdict(list)
    for fid in core:
        columns[0].append(fid)
    for fid, (_, column) in PLACEMENT.items():
        columns[column].append(fid)
    width = {c: max(flows[fid].width + 0 for fid in ids) for c, ids in columns.items()}
    left = {0: 0}
    for c in sorted(k for k in columns if k > 0):
        left[c] = left[c - 1] + width[c - 1] + FRAME_GAP
    for c in sorted((k for k in columns if k < 0), reverse=True):
        left[c] = left[c + 1] - FRAME_GAP - width[c]
    shift = -min(left.values())
    y = 0
    top = {}
    for fid in core:
        f = flows[fid]
        f.x = shift + left[0] + (width[0] - f.width) // 2
        f.y = y
        top[fid] = y
        y += f.height + TITLE_H + HEADER_H + FRAME_GAP
    bottom = defaultdict(lambda: -FRAME_GAP)
    for fid, (home, column) in PLACEMENT.items():
        f = flows[fid]
        f.y = max(top[home], bottom[column] + FRAME_GAP)
        f.x = shift + left[column] + (width[column] - f.width if column < 0 else 0)
        bottom[column] = f.y + f.height + TITLE_H + HEADER_H


def style_for(n):
    fill, stroke, _ = COLORS[n.lane]
    base = "html=0;fontSize=12;fontFamily=Helvetica;fontColor=#111827;"
    if n.kind == "decision":
        return f"rhombus;spacingLeft=38;spacingRight=38;{base}fillColor={fill};strokeColor={stroke};"
    if n.kind == "state":
        return f"rounded=1;arcSize=50;strokeWidth=2.5;{base}fillColor={fill};strokeColor={stroke};"
    dashed = "dashed=1;dashPattern=5 3;" if n.lane == "System" else ""
    return f"rounded=1;arcSize=18;{dashed}{base}fillColor={fill};strokeColor={stroke};"


def cell(cid, value, style, parent, x, y, w, h, vertex=True):
    return (f'<mxCell id={quoteattr(cid)} value={quoteattr(value)} style={quoteattr(style)} vertex="1" '
            f'parent={quoteattr(parent)}><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def edge_cell(cid, e, parent, src, dst, ox, oy):
    (sx, sy), (tx, ty) = e.points[0], e.points[-1]

    def rel(node, px, py):
        return (px - node.x) / node.w, (py - node.y) / node.h

    ex, ey = rel(src, sx, sy)
    nx, ny = rel(dst, tx, ty)
    dashed = "dashed=1;dashPattern=6 4;" if e.dashed else ""
    style = (f"edgeStyle=none;rounded=1;arcSize=12;html=0;endArrow=block;endFill=1;endSize=6;strokeColor=#4B5563;"
             f"strokeWidth=1.4;{dashed}exitX={ex:.5f};exitY={ey:.5f};exitDx=0;exitDy=0;exitPerimeter=0;"
             f"entryX={nx:.5f};entryY={ny:.5f};entryDx=0;entryDy=0;entryPerimeter=0;fontSize=10;"
             f"fontFamily=Helvetica;fontColor=#374151;labelBackgroundColor=#FFFFFF;")
    points = "".join(f'<mxPoint x="{x + ox}" y="{y + oy}"/>' for x, y in e.points[1:-1])
    geometry_x = f' x="{2 * e.label_at - 1:.4f}"' if e.label else ""
    offset = getattr(e, "label_offset", (0, 0))
    if e.label and offset != (0, 0):
        points_xml_offset = f'<mxPoint x="{offset[0]:.0f}" y="{offset[1]:.0f}" as="offset"/>'
    else:
        points_xml_offset = ""
    value = "\n".join(getattr(e, "label_lines", [e.label]))
    return (f'<mxCell id={quoteattr(cid)} value={quoteattr(value)} style={quoteattr(style)} edge="1" '
            f'parent={quoteattr(parent)} source={quoteattr(src.cid)} target={quoteattr(dst.cid)}>'
            f'<mxGeometry relative="1"{geometry_x} as="geometry">{points_xml_offset}'
            f'{"<Array as=" + chr(34) + "points" + chr(34) + ">" + points + "</Array>" if points else ""}'
            f"</mxGeometry></mxCell>")


def frame_cells(f):
    fid = "f_" + f.id.replace("-", "")
    total_h = TITLE_H + HEADER_H + f.height
    out = [cell(fid, f"{f.id} {f.name}",
                "swimlane;startSize=40;container=1;collapsible=0;html=0;fillColor=#1F2937;fontColor=#FFFFFF;"
                "strokeColor=#1F2937;strokeWidth=2;swimlaneFillColor=#FFFFFF;fontStyle=1;fontSize=15;"
                "fontFamily=Helvetica;align=left;spacingLeft=12;",
                "1", f.x, f.y, f.width, total_h)]
    for i, lane in enumerate(f.lanes):
        out.append(cell(f"{fid}_lane{i}", lane,
                        "swimlane;startSize=30;container=0;collapsible=0;html=0;fillColor=#F3F4F6;"
                        f"swimlaneFillColor={COLORS[lane][2]};strokeColor=#9CA3AF;fontStyle=1;fontSize=12;"
                        "fontFamily=Helvetica;fontColor=#111827;",
                        fid, f.lane_x[lane], TITLE_H, f.lane_w[lane], HEADER_H + f.height))
    oy = TITLE_H + HEADER_H
    for n in sorted(f.nodes.values(), key=lambda n: n.order):
        n.cid = f"{fid}_{n.id}"
        out.extend(node_cells(n, fid, 0, oy))
    for i, e in enumerate(f.edges):
        if e.points:
            out.append(edge_cell(f"{fid}_e{i}", e, fid, f.nodes[e.s], f.nodes[e.t], 0, oy))
    return out


def text_of(n):
    """The node's label broken into the lines its size was measured with."""
    if n.kind == "decision":
        return "\n".join(wrap(n.label, NODE_W * 0.62))
    if n.kind in ("action", "state"):
        return "\n".join(wrap(n.label, NODE_W - 16))
    return "\n".join(wrap(n.label, NODE_W - 10)) if n.label else ""


def node_cells(n, parent, ox, oy):
    text = text_of(n)
    x, y = n.x + ox, n.y + oy
    if n.kind in ("action", "state", "decision"):
        return [cell(n.cid, text, style_for(n), parent, x, y, n.w, n.h)]
    if n.kind == "join":
        return [cell(n.cid, "", "rounded=0;html=0;fillColor=#111827;strokeColor=#111827;", parent, x, y, n.w, n.h)]
    cx = n.x + n.w // 2
    width = label_width(n)
    label = (f"text;html=0;align=center;fontSize=11;fontFamily=Helvetica;fontColor=#111827;"
             f"spacing=0;verticalAlign={'bottom' if n.kind == 'initial' else 'top'};")
    if n.kind == "initial":
        circle_y = n.y + n.h - SMALL
        shape = "ellipse;html=0;fillColor=#111827;strokeColor=#111827;"
        label_box = (cx - width // 2, n.y, width, n.h - SMALL - GRID)
    else:
        circle_y = n.y
        shape = ("shape=endState;html=0;fillColor=#111827;strokeColor=#111827;" if n.kind == "final"
                 else "shape=sumEllipse;perimeter=ellipsePerimeter;html=0;fillColor=#FFFFFF;strokeColor=#111827;"
                      "strokeWidth=1.5;")
        label_box = (cx - width // 2, n.y + SMALL + GRID, width, n.h - SMALL - GRID)
    n.x, n.y, n.w, n.h = cx - SMALL // 2, circle_y, SMALL, SMALL
    cells = [cell(n.cid, "", shape, parent, n.x + ox, n.y + oy, SMALL, SMALL)]
    if n.label and label_box[3] > 0:
        cells.append(cell(n.cid + "_label", text, label, parent, label_box[0] + ox, label_box[1] + oy,
                          label_box[2], label_box[3]))
    return cells


def build_map(flows):
    """Lay out and route the system activity map: the flows, their events and the legend."""
    missing = sorted(set(flows) - set(MAP_POSITION), key=flow_key)
    if missing:
        raise SystemExit(f"No place on the system activity map for {', '.join(missing)}")
    own = {fid for fid, f in flows.items() if "trigger" in f.nodes}
    evented = {event[3] for event in MAP_EVENTS}
    if own != evented:
        raise SystemExit(f"Flows that start on their own {sorted(own, key=flow_key)} differ from the map events "
                         f"{sorted(evented, key=flow_key)}")
    nodes = {}
    for fid, (column, row) in MAP_POSITION.items():
        n = Node(fid, "System", len(nodes))
        n.kind, n.role, n.col, n.rank = "action", "core" if fid.startswith("WF") else "support", column, row
        n.label = flows[fid].name
        n.w, n.h = MAP_BOX_W, up(map_text_height(n.label) + 16)
        nodes[fid] = n
    for i, (label, column, row, fid) in enumerate(MAP_EVENTS):
        n = Node(f"event{i}", "System", len(nodes))
        n.kind, n.role, n.col, n.rank, n.label, n.flow = "action", "event", column, row, label, fid
        n.w, n.h = up(len(label) * 7.2 + 32), MAP_EVENT_H
        nodes[n.id] = n
    legend = Node("legend", "System", len(nodes))
    legend.kind, legend.role, legend.col, legend.rank = "action", "legend", MAP_LEGEND[0], MAP_LEGEND[1]
    legend.w, legend.h = 440, 120

    cols = sorted({n.col for n in nodes.values()})
    rows = sorted({n.rank for n in nodes.values()})
    col_w = {c: max(n.w for n in nodes.values() if n.col == c) for c in cols}
    row_h = {r: max(n.h for n in nodes.values() if n.rank == r) for r in rows}
    left, x = {}, PAD
    for c in cols:
        left[c] = x
        x += col_w[c] + MAP_GAP_X
    top, y = {}, PAD
    for r in rows:
        top[r] = y
        y += row_h[r] + MAP_GAP_Y
    for n in nodes.values():
        n.x = up(left[n.col] + (col_w[n.col] - n.w) / 2, GRID)
        n.y = up(top[n.rank] + (row_h[n.rank] - n.h) / 2, GRID)
    legend.x, legend.y = left[MAP_LEGEND[0]], top[MAP_LEGEND[1]]
    nodes[legend.id] = legend
    width = x - MAP_GAP_X + PAD + 120
    height = max(y - MAP_GAP_Y, legend.y + legend.h) + PAD

    pairs = {}
    for j in JOINS:
        key = (j[0], j[2])
        pairs[key] = pairs.get(key, True) and j[4]
    edges = []
    for (s, t), dashed in sorted(pairs.items(), key=lambda kv: (flow_key(kv[0][0]), flow_key(kv[0][1]))):
        e = Edge(s, t, "", dashed)
        e.group = f"map:{s}>{t}"
        edges.append(e)
    for n in nodes.values():
        if n.role == "event":
            e = Edge(n.id, n.flow)
            e.group = f"map:{n.id}"
            edges.append(e)
    order = sorted(range(len(edges)), key=lambda i: abs(nodes[edges[i].s].x - nodes[edges[i].t].x)
                   + abs(nodes[edges[i].s].y - nodes[edges[i].t].y))
    crossings, failures = route_edges(width, height, nodes, edges, order)
    return nodes, edges, crossings, [f"{edges[i].s} -> {edges[i].t}" for i in failures]


MAP_STYLE = {
    "core": "fillColor=#DBEAFE;strokeColor=#1D4ED8;strokeWidth=2;",
    "support": "fillColor=#F1F5F9;strokeColor=#64748B;strokeWidth=1.5;",
    "event": "fillColor=#1F2937;strokeColor=#1F2937;",
}
MAP_TEXT = "text;html=0;align=center;verticalAlign=top;spacing=0;fontSize=12;fontFamily=Helvetica;fontColor=#0F172A;"


def map_text_height(name):
    """Height of a flow box's ID line and wrapped name."""
    return 18 + 16 * len(wrap(name, MAP_BOX_W - 20))


def map_cells(nodes, edges):
    out = []
    for n in nodes.values():
        n.cid = "m_" + n.id.replace("-", "")
        if n.role == "legend":
            out.extend(legend_cells(n))
        elif n.role == "event":
            out.append(cell(n.cid, n.label, "rounded=1;arcSize=50;html=0;fontColor=#FFFFFF;fontStyle=1;fontSize=12;"
                            f"fontFamily=Helvetica;{MAP_STYLE['event']}", "1", n.x, n.y, n.w, n.h))
        else:
            lines = wrap(n.label, MAP_BOX_W - 20)
            top = n.y + (n.h - map_text_height(n.label)) / 2
            out.append(cell(n.cid, "", f"rounded=1;arcSize=12;html=0;{MAP_STYLE[n.role]}", "1", n.x, n.y, n.w, n.h))
            out.append(cell(n.cid + "_id", n.id, MAP_TEXT + "fontStyle=1;", "1", n.x, top, n.w, 16))
            out.append(cell(n.cid + "_name", "\n".join(lines), MAP_TEXT, "1", n.x + 10, top + 18, n.w - 20,
                            16 * len(lines)))
    for i, e in enumerate(edges):
        if e.points:
            out.append(edge_cell(f"m_e{i}", e, "1", nodes[e.s], nodes[e.t], 0, 0))
    return out


def legend_cells(n):
    out = []
    items = [("core", "Core flow, WF-01 to WF-06"), ("support", "Supporting flow, SF-01 to SF-11"),
             ("event", "Event that starts a flow on its own"), ("dashed", "Taken only when it happens")]
    for k, (role, text) in enumerate(items):
        y = n.y + k * 30
        if role == "dashed":
            point = "ellipse;html=0;fillColor=none;strokeColor=none;"
            out.append(cell(f"m_legend{k}a", "", point, "1", n.x - 1, y + 9, 2, 2))
            out.append(cell(f"m_legend{k}b", "", point, "1", n.x + 39, y + 9, 2, 2))
            out.append(f'<mxCell id="m_legend{k}" value="" style="edgeStyle=none;html=0;endArrow=block;endFill=1;endSize=6;'
                       'strokeColor=#4B5563;strokeWidth=1.4;dashed=1;dashPattern=6 4;exitX=0.5;exitY=0.5;entryX=0.5;'
                       f'entryY=0.5;" edge="1" parent="1" source="m_legend{k}a" target="m_legend{k}b">'
                       '<mxGeometry relative="1" as="geometry"/></mxCell>')
        else:
            arc = "arcSize=50;" if role == "event" else "arcSize=20;"
            out.append(cell(f"m_legend{k}", "", f"rounded=1;{arc}html=0;{MAP_STYLE[role]}", "1", n.x, y, 40, 20))
        out.append(cell(f"m_legend{k}_text", text, "text;html=0;align=left;verticalAlign=middle;fontSize=12;"
                        "fontFamily=Helvetica;fontColor=#334155;", "1", n.x + 52, y, 360, 20))
    return out


def write_drawio(flows, map_nodes, map_edges):
    sheet = []
    for fid in sorted(flows, key=flow_key):
        sheet.extend(frame_cells(flows[fid]))
    pages = [("system-activity", "System activity diagram", sheet),
             ("system-activity-map", "System activity map", map_cells(map_nodes, map_edges))]
    body = []
    for pid, name, cells in pages:
        body.append(f'<diagram id="{pid}" name="{name}"><mxGraphModel grid="0" gridSize="10" guides="1" tooltips="1" '
                    'connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0" background="#FFFFFF">'
                    '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram>")
    DRAWIO.write_text('<mxfile host="Electron" type="device">' + "".join(body) + "</mxfile>\n", encoding="utf-8")


def verify():
    """Measure the written file: lines that cross, lines that cut a shape, lines that run along another line."""
    problems = []
    tree = ET.parse(DRAWIO)
    for diagram in tree.getroot().iter("diagram"):
        boxes, parents, edges = {}, {}, []
        for c in diagram.iter("mxCell"):
            parents[c.get("id")] = c.get("parent")
            g = c.find("mxGeometry")
            if c.get("vertex") == "1":
                boxes[c.get("id")] = (float(g.get("x", 0)), float(g.get("y", 0)), float(g.get("width", 0)),
                                      float(g.get("height", 0)), c.get("style") or "")
            elif c.get("edge") == "1":
                edges.append(c)

        def origin(cid):
            x = y = 0.0
            p = parents.get(cid)
            while p in boxes:
                x += boxes[p][0]
                y += boxes[p][1]
                p = parents.get(p)
            return x, y

        shapes = {}
        for cid, (x, y, w, h, style) in boxes.items():
            if style.startswith("swimlane"):
                continue
            ox, oy = origin(cid)
            shapes[cid] = (x + ox, y + oy, w, h)
        lines = []
        for c in edges:
            style = c.get("style")
            values = dict(re.findall(r"(\w+)=([^;]+)", style))
            s, t = shapes[c.get("source")], shapes[c.get("target")]
            ox, oy = origin(c.get("id"))
            start = (s[0] + s[2] * float(values["exitX"]), s[1] + s[3] * float(values["exitY"]))
            end = (t[0] + t[2] * float(values["entryX"]), t[1] + t[3] * float(values["entryY"]))
            mids = [(float(p.get("x")) + ox, float(p.get("y")) + oy) for p in c.iter("mxPoint") if p.get("as") != "offset"]
            name = f"{c.get('source')} > {c.get('target')}"
            lines.append((name, c.get("source"), c.get("target"), [start] + mids + [end]))
        segments = [(lid, src, tgt, a, b) for lid, src, tgt, pts in lines for a, b in zip(pts, pts[1:])]
        for i in range(len(segments)):
            l1, s1, t1, a, b = segments[i]
            for j in range(i + 1, len(segments)):
                l2, s2, t2, c, d = segments[j]
                if l1 == l2:
                    continue
                kind = meet(a, b, c, d)
                if kind == "cross":
                    problems.append(f"{diagram.get('name')}: {l1} crosses {l2}")
                elif kind == "overlap" and s1 != s2:
                    problems.append(f"{diagram.get('name')}: {l1} runs along {l2}")
        for lid, src, tgt, pts in lines:
            for a, b in zip(pts, pts[1:]):
                for cid, (x, y, w, h) in shapes.items():
                    if cid in (src, tgt) or cid in (src + "_label", tgt + "_label"):
                        continue
                    if cuts(a, b, (x + 1, y + 1, w - 2, h - 2)):
                        problems.append(f"{diagram.get('name')}: {lid} cuts {cid}")
    return problems


def meet(a, b, c, d):
    horizontal1, horizontal2 = a[1] == b[1], c[1] == d[1]
    if horizontal1 == horizontal2:
        if horizontal1 and a[1] == c[1]:
            lo, hi = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
            return "overlap" if hi - lo > 1 else None
        if not horizontal1 and a[0] == c[0]:
            lo, hi = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
            return "overlap" if hi - lo > 1 else None
        return None
    if horizontal1:
        (h1, h2), (v1, v2) = (a, b), (c, d)
    else:
        (h1, h2), (v1, v2) = (c, d), (a, b)
    x, y = v1[0], h1[1]
    inside_h = min(h1[0], h2[0]) < x < max(h1[0], h2[0])
    inside_v = min(v1[1], v2[1]) < y < max(v1[1], v2[1])
    return "cross" if inside_h and inside_v else None


def cuts(a, b, box):
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return False
    if a[1] == b[1]:
        return y < a[1] < y + h and min(a[0], b[0]) < x + w and max(a[0], b[0]) > x
    return x < a[0] < x + w and min(a[1], b[1]) < y + h and max(a[1], b[1]) > y


def drawio_command():
    for name in ("drawio", "draw.io"):
        found = shutil.which(name)
        if found:
            return found
    default = Path("C:/Program Files/draw.io/draw.io.exe")
    return str(default) if default.exists() else None


def export():
    exe = drawio_command()
    commands = [
        ["-x", "-f", "svg", "-p", "1", "-o", SHEET_SVG.name, DRAWIO.name],
        ["-x", "-f", "svg", "-p", "2", "-o", MAP_SVG.name, DRAWIO.name],
        ["-x", "-f", "pdf", "-a", "-o", PDF.name, DRAWIO.name],
    ]
    if not exe:
        print("draw.io desktop not found; export with:")
        for c in commands:
            print("  drawio " + " ".join(c))
        return
    for c in commands:
        subprocess.run([exe, *c], cwd=HERE, check=True, capture_output=True)


def split_flows():
    """Write each frame of the sheet in DRAWIO as a file of its own, moved to the origin; return the files."""
    sheet = next(d for d in ET.parse(DRAWIO).getroot().iter("diagram") if d.get("id") == "system-activity")
    cells = list(sheet.find("mxGraphModel/root"))
    parent = {c.get("id"): c.get("parent") for c in cells}

    def frame_of(cid):
        while cid in parent and parent[cid] != "1":
            cid = parent[cid]
        return cid

    FLOWS_DIR.mkdir(exist_ok=True)
    written = []
    for frame in (c for c in cells if c.get("parent") == "1" and c.get("id", "").startswith("f_")):
        fid, name = frame.get("value").split(" ", 1)
        frame.find("mxGeometry").set("x", "0")
        frame.find("mxGeometry").set("y", "0")
        body = "".join(ET.tostring(c, encoding="unicode") for c in cells
                       if c.get("id") == frame.get("id") or (parent.get(c.get("id")) not in (None, "0", "1")
                                                            and frame_of(c.get("id")) == frame.get("id")))
        path = FLOWS_DIR / f"{fid.lower()}.drawio"
        path.write_text(f'<mxfile host="Electron" type="device"><diagram id={quoteattr(fid)} name={quoteattr(fid + " " + name)}>'
                        '<mxGraphModel grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
                        'page="0" pageScale="1" math="0" shadow="0" background="#FFFFFF"><root><mxCell id="0"/>'
                        f'<mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram></mxfile>\n', encoding="utf-8")
        written.append(path)
    for old in FLOWS_DIR.iterdir():
        if old.suffix in (".drawio", ".svg") and old.with_suffix(".drawio") not in written:
            old.unlink()
    return written


def export_flows(files):
    exe = drawio_command()
    if not exe:
        print("draw.io desktop not found; export each flow with:")
        print(f"  drawio -x -f svg -o <flow>.svg <flow>.drawio   (in {FLOWS_DIR.relative_to(ROOT).as_posix()})")
        return
    for path in files:
        subprocess.run([exe, "-x", "-f", "svg", "-o", path.with_suffix(".svg").name, path.name],
                       cwd=FLOWS_DIR, check=True, capture_output=True)


def write_readme(flows):
    def node_text(fid, nid):
        return f"{fid}: {ORIGINAL[(fid, nid)]}"

    rows = "\n".join(f"| {node_text(j[0], j[1])} | {node_text(j[2], j[3])} | {j[6]} |" for j in JOINS)
    files = "\n".join(f"| {fid} {flows[fid].name} | [{fid.lower()}.svg](flows/{fid.lower()}.svg) "
                      f"| [{fid.lower()}.drawio](flows/{fid.lower()}.drawio) |" for fid in sorted(flows, key=flow_key))
    README.write_text(README_TEMPLATE.format(joins=rows, flows=files), encoding="utf-8")


README_TEMPLATE = """# System activity diagram

All 17 business flows of [Business flows](../../functional/business-flows.md), WF-01 to WF-06 and SF-01 to SF-11, on one sheet. Each flow is a frame of its own: an activity with its steps, decisions and lanes as business-flows.md draws them. [activity_diagram.py](activity_diagram.py) reads those Mermaid diagrams and draws this one, so a change to a flow is made in business-flows.md and the diagram is generated again. It is drawn with draw.io, not Mermaid, because Mermaid cannot keep the lanes of 17 frames in one order without crossing lines.

![System activity diagram](system-activity-diagram.svg)

## Files

- [system-activity-diagram.drawio](system-activity-diagram.drawio): the sheet and the system activity map, generated by the script
- [system-activity-diagram.svg](system-activity-diagram.svg), [system-activity-map.svg](system-activity-map.svg) and [system-activity-diagram.pdf](system-activity-diagram.pdf): their exports
- [flows](#flows): each frame of the sheet as a diagram of its own, split from the sheet by the script
- [activity_diagram.py](activity_diagram.py): reads business-flows.md, writes the diagram, this document and the exports

After changing a flow in business-flows.md, regenerate everything with:

```bash
python docs/reports/activity-diagram/activity_diagram.py
```

The script exports with draw.io desktop when it finds it. It stops with an error, after writing the files, when a line crosses another line, runs along another line or cuts a shape; a correct diagram has none. After editing the sheet by hand, split it into the flow files again without redrawing it:

```bash
python docs/reports/activity-diagram/activity_diagram.py --split
```

## Flows

| Flow | SVG | draw.io |
| --- | --- | --- |
{flows}

## Reading the diagram

- A frame is one flow and one activity. Its title is the flow's ID and name in business-flows.md.
- A frame has a lane for each actor it uses, always in this order: Customer, Sales, Head of Sales, Accountant, Administrator, System, Head of Department, Tester, Sample Delivery Staff, Lab Head, Subcontractor. The actors are those of the [use case diagram](../use-case-diagram/readme.md). System holds the steps the software takes, which business-flows.md draws outside every lane.
- A rounded box is an action; a dashed one is an action of the system. A box with a bold border is a state the flow passes. A diamond is a decision, its outgoing lines labelled with its outcomes.
- Words in square brackets at the start of an action are its condition, such as [folder owner] or [report edit permission].
- An initial node (●) starts the flow. Its label is the flow's trigger, or the flows and steps whose work it takes. An initial node has no line coming in, so no line runs from one frame to another.
- A flow final (⊗) ends one path and names the flows that take the work over. An activity final (◉) ends the flow with its outcome, followed by the flows that take the work over, if any.
- A dashed line is a path that happens only when its label says so, or a dashed line of business-flows.md.

## System activity map

How the flows connect, without their steps:

- A box is a flow: blue for the core flows WF-01 to WF-06, grey for the supporting flows.
- A dark event starts a flow that also starts on its own, beside the flows that lead to it. It is named after the flow's trigger in business-flows.md.
- An arrow joins two flows that a join below connects. It is dashed when every such join is dashed.

![System activity map](system-activity-map.svg)

## Joins between flows

Each join is drawn as a flow final or activity final in the first flow and an initial node in the second.

| From | To | Why |
| --- | --- | --- |
{joins}

## Differences from business-flows.md

- A node that only names another flow, such as "WF-04 Result entry and approval", is a flow final.
- A state that ends a path is an activity final with the state as its label. A final reached from several lanes is drawn once in each of them.
- The steps that all lead to "Ready for testing and reports" in SF-08 meet at a join bar first, since that outcome needs all of them.
- The initial nodes are added: one for each trigger and one for each step another flow leads to.
- Two nodes that name another flow but lead on stay as steps: "WF-06: review, approve, digitally sign when enabled, store PDF and issue" in SF-03 and "WF-04 saves and versions files" in SF-11.

## Related documents

- [Business flows](../../functional/business-flows.md)
- [Use case diagram](../use-case-diagram/readme.md)
- [Reports](../readme.md)
"""

ORIGINAL = {}


def main():
    flows = read_flows()
    for f in flows.values():
        for n in f.nodes.values():
            ORIGINAL[(f.id, n.id)] = n.label
    if "--split" in sys.argv:
        files = split_flows()
        write_readme(flows)
        export_flows(files)
        print(f"Wrote {len(files)} flows to {FLOWS_DIR.name}/ and {README.name}.")
        return
    missing = [fid for fid in flows if fid not in PLACEMENT and not fid.startswith("WF")]
    if missing:
        raise SystemExit(f"No place on the sheet for {', '.join(missing)}")
    transform(flows)
    map_nodes, map_edges, map_crossings, map_failures = build_map(flows)
    for f in flows.values():
        layout_flow(f)
    place_frames(flows)
    write_drawio(flows, map_nodes, map_edges)
    write_readme(flows)
    for fid in sorted(flows, key=flow_key):
        f = flows[fid]
        status = "ok" if not f.crossings and not f.failures else f"{f.crossings} crossings, unrouted {f.failures}"
        print(f"{fid}: {len(f.lanes)} lanes, {len(f.nodes)} nodes, {len(f.edges)} lines, {status}")
        for w in f.warnings:
            print(f"  {w}")
    print(f"System activity map: {len(map_edges)} lines, "
          + ("ok" if not map_crossings and not map_failures else f"{map_crossings} crossings, unrouted {map_failures}"))
    problems = verify()
    for p in problems:
        print(p)
    files = split_flows()
    if "--no-export" not in sys.argv:
        export()
        export_flows(files)
    if problems or map_failures or any(f.failures for f in flows.values()):
        raise SystemExit(f"{len(problems)} problems in {DRAWIO.name}")
    print(f"Wrote {DRAWIO.name}, {README.name} and the exports; no line crosses, runs along another or cuts a shape.")


if __name__ == "__main__":
    main()
