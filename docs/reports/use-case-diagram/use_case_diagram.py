"""Draw the MediLab use case diagram from the tables of readme.md next to this script.

The diagram is a "peacock" layout: actors on the two edges of the system box, each actor a horizontal band of its
root use cases in two columns, and the children of a root use case fanned out beside it.
Run: python docs/reports/use-case-diagram/use_case_diagram.py [output.drawio]
"""

import heapq
import math
import re
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
README = HERE / "readme.md"
OUTPUT = HERE / "medilab-use-case.drawio"
SYSTEM_NAME = (
    "MediLab: Laboratory Information Management Subsystem for a Contract Testing Laboratory on the Odoo Platform"
)
LEFT_ACTORS = ["Internal User", "Sales", "Head of Sales", "System", "Administrator"]
RIGHT_ACTORS = [
    "Customer",
    "Sample Delivery Staff",
    "Accountant",
    "Lab Head",
    "Head of Department",
    "Tester",
    "Subcontractor",
]

GRID = 10
ITEM_GAP = GRID  # between two ellipses of a fan, and between two single use cases
CLUSTER_GAP = 2 * GRID  # between two blocks
UC_WIDTH = 110
UC_HEIGHT = 40
CHAR_WIDTH = 7  # width of a 12 px Helvetica character, rounded up so a line never wraps a third time
TEXT_SPACING = 10  # free space left and right of the text inside an ellipse, so it stays inside the curve
FAN_GAP = 80  # from the parent lane to the child lane
COLUMN_GAP = 140
SYSTEM_X = 240
SYSTEM_PADDING = 40
ACTOR_OFFSET = 130  # from the system box to an actor
ACTOR_MIN_PITCH = 120  # actor body and label
ACTOR_LABEL_GAP = 20  # a straight actor generalization starts this far below the actor
OUTER_LANE = 60  # first lane of actor generalizations between actors that are not adjacent
PARENT_LANE_STEP = 30  # each parent actor has a lane of its own
LOOP_STEP = 20
BOTTOM_LOOP_GAP = 40
ARC_FLAT = 150  # children within three rows of their parent keep a straight column
ARC_RADIUS = 440  # further children bend toward the parent on this circle
BEND_PENALTY = 60  # a bend costs as much as 60 px of length
LINE_MARGIN = 5  # clearance between a line and an ellipse
LINE_SPACING = 8  # clearance between two lines that share no end
SAME_ORIGIN_ANGLE = 3  # degrees between two lines that leave the same actor
CROSSING_PENALTY = 400
CROSSING_MIN_ANGLE = 30  # degrees; a forced crossing must be close to perpendicular
DETOUR_REPORT = 40

FILL = "fillColor=#7ACFF5;strokeColor=#000000;"
STYLES = {
    "System": "rounded=0;html=0;verticalAlign=top;fontStyle=1;fillColor=#FFFFFF;",
    "Actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=0;" + FILL,
    "UseCase": "ellipse;html=0;" + FILL,
    "Association": "endArrow=none;html=1;rounded=0;",
    "Generalization": "endArrow=block;endFill=0;endSize=12;html=1;rounded=0;",
}


def table_rows(lines):
    """Cells of the Markdown table rows in `lines`, without the header and separator rows."""
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines if line.startswith("|")]
    return rows[2:]


def read_model(path):
    """Actors with their parent actor, and use cases as (name, actor, parent use case), from the readme tables."""
    sections, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"(#{2,3}) (.+)", line)
        if heading:
            current = heading.group(2) if heading.group(1) == "##" else f"Use cases/{heading.group(2)}"
            sections[current] = []
        elif current:
            sections[current].append(line)
    actors = {row[0]: row[1] for row in table_rows(sections["Actors"])}
    use_cases = [
        (row[0], key.split("/", 1)[1], row[1])
        for key, lines in sections.items()
        if key.startswith("Use cases/")
        for row in table_rows(lines)
    ]
    return actors, use_cases


def check_model(actors, use_cases):
    """Stop when the tables do not form one diagram the layout supports."""
    names = Counter(name for name, _, _ in use_cases)
    roots = {(name, actor) for name, actor, parent in use_cases if not parent}
    errors = [f"use case named twice: {name}" for name, count in names.items() if count > 1]
    errors += [
        f"{name}: parent {parent} is not a root use case of {actor}"
        for name, actor, parent in use_cases
        if parent and (parent, actor) not in roots
    ]
    errors += [
        f"{actor}: unknown parent actor {parent}" for actor, parent in actors.items() if parent and parent not in actors
    ]
    errors += [f"{actor}: no use cases" for actor in actors if not any(owner == actor for _, owner, _ in use_cases)]
    placed = LEFT_ACTORS + RIGHT_ACTORS
    if sorted(placed) != sorted(actors):
        errors.append(f"LEFT_ACTORS and RIGHT_ACTORS must list the actors of the table: {sorted(actors)}")
    if errors:
        sys.exit("Tables are inconsistent:\n" + "\n".join(errors))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def snap(value):
    return round(value / GRID) * GRID


def wrap_label(name):
    """(width, label) of the smallest ellipse on the grid that holds `name` on at most two lines. The label carries
    its own line breaks: plain-text labels export to SVG as text, without an image per label."""
    width = UC_WIDTH
    while True:
        capacity = (width - 2 * TEXT_SPACING - 4) / CHAR_WIDTH
        lines = [""]
        for word in name.split():
            candidate = f"{lines[-1]} {word}".strip()
            if len(candidate) > capacity and lines[-1]:
                lines.append(word)
            else:
                lines[-1] = candidate
        if len(lines) <= 2:
            return width, "\n".join(lines)
        width += GRID


def vertex(node_id, name, style, x, y, width, height):
    return (
        f'<mxCell id="{node_id}" value={quoteattr(name)} style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry"/></mxCell>'
    )


def edge(edge_id, style, source, target, points=()):
    waypoints = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
    array = f'<Array as="points">{waypoints}</Array>' if waypoints else ""
    return (
        f'<mxCell id="{edge_id}" style="{style}" edge="1" parent="1" source="{source}" target="{target}">'
        f'<mxGeometry relative="1" as="geometry">{array}</mxGeometry></mxCell>'
    )


def segment_hits(start, end, box, margin=LINE_MARGIN):
    """Whether segment start→end enters the ellipse inscribed in `box`, widened by `margin`."""
    x, y, width, height = box
    radius_x, radius_y = width / 2 + margin, height / 2 + margin
    center_x, center_y = x + width / 2, y + height / 2
    origin_x, origin_y = (start[0] - center_x) / radius_x, (start[1] - center_y) / radius_y
    delta_x, delta_y = (end[0] - start[0]) / radius_x, (end[1] - start[1]) / radius_y
    length = delta_x**2 + delta_y**2
    t = 0 if not length else max(0, min(1, -(origin_x * delta_x + origin_y * delta_y) / length))
    return (origin_x + t * delta_x) ** 2 + (origin_y + t * delta_y) ** 2 < 1


def crossing(first_start, first_end, second_start, second_end):
    """Intersection of two segments that do not merely touch at an end, or None."""
    first_x, first_y = first_end[0] - first_start[0], first_end[1] - first_start[1]
    second_x, second_y = second_end[0] - second_start[0], second_end[1] - second_start[1]
    denominator = first_x * second_y - first_y * second_x
    if abs(denominator) < 1e-9:
        return None
    offset_x, offset_y = second_start[0] - first_start[0], second_start[1] - first_start[1]
    first_ratio = (offset_x * second_y - offset_y * second_x) / denominator
    second_ratio = (offset_x * first_y - offset_y * first_x) / denominator
    if 1e-6 < first_ratio < 1 - 1e-6 and 1e-6 < second_ratio < 1 - 1e-6:
        return first_start[0] + first_ratio * first_x, first_start[1] + first_ratio * first_y
    return None


def point_segment_distance(point, start, end):
    delta_x, delta_y = end[0] - start[0], end[1] - start[1]
    length = delta_x**2 + delta_y**2
    ratio = (
        0
        if not length
        else max(0, min(1, ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / length))
    )
    return math.dist(point, (start[0] + ratio * delta_x, start[1] + ratio * delta_y))


def boxes_overlap(first, second):
    return first[0] <= second[2] and second[0] <= first[2] and first[1] <= second[3] and second[1] <= first[3]


def segment_bounds(start, end, margin=0):
    return (
        min(start[0], end[0]) - margin,
        min(start[1], end[1]) - margin,
        max(start[0], end[0]) + margin,
        max(start[1], end[1]) + margin,
    )


def angle_between(first_start, first_end, second_start, second_end):
    return abs(
        math.atan2(first_end[1] - first_start[1], first_end[0] - first_start[0])
        - math.atan2(second_end[1] - second_start[1], second_end[0] - second_start[0])
    )


def column_height(blocks):
    """Height of a column that stacks `blocks` as (name, children) the way `stack` does."""
    height, previous = 0, None
    for _, children in blocks:
        if previous:
            height += ITEM_GAP if previous == "single" and not children else CLUSTER_GAP
        height += (UC_HEIGHT + ITEM_GAP) * len(children) - ITEM_GAP if children else UC_HEIGHT
        previous = "cluster" if children else "single"
    return height


def split_band(blocks):
    """(near column, inner column) of an actor's root use cases, in table order. The smallest blocks stay next to
    the actor and leave gaps for the lines to the inner column, which takes the largest blocks; the cut between them
    gives the lowest band. A band without fans keeps one column."""
    if all(not children for _, children in blocks):
        return blocks, []
    by_size = sorted(blocks, key=lambda block: len(block[1]))
    best = None
    for cut in range(len(blocks)):
        near_names = {name for name, _ in by_size[:cut]}
        near = [block for block in blocks if block[0] in near_names]
        inner = [block for block in blocks if block[0] not in near_names]
        height = max(column_height(near), column_height(inner))
        if best is None or height < best[0]:
            best = height, near, inner
    return best[1], best[2]


def peacock(actors, use_cases):
    """mxCells of the peacock layout, and the check report."""
    actor_id = {name: f"actor-{slug(name)}" for name in actors}
    use_case_id = {name: f"uc-{slug(name)}" for name, _, _ in use_cases}
    label = {node_id: name for name, node_id in list(actor_id.items()) + list(use_case_id.items())}
    children = {use_case_id[name]: [] for name, _, parent in use_cases if not parent}
    for name, _, parent in use_cases:
        if parent:
            children[use_case_id[parent]].append(use_case_id[name])
    roots_of = {
        actor: [use_case_id[name] for name, owner, parent in use_cases if owner == actor and not parent]
        for actor in actors
    }
    associations = [(actor_id[actor], root) for actor, roots in roots_of.items() for root in roots]
    actor_parents = [(actor_id[actor], actor_id[parent]) for actor, parent in actors.items() if parent]

    column_width = 2 * UC_WIDTH + FAN_GAP

    def column_lanes(index):
        """(parent lane x, child lane x) of column `index` from the left; fans open toward the middle."""
        base = SYSTEM_X + SYSTEM_PADDING + index * (column_width + COLUMN_GAP)
        left_lane, right_lane = base, base + UC_WIDTH + FAN_GAP
        return (left_lane, right_lane) if index < 2 else (right_lane, left_lane)

    bands = {"left": LEFT_ACTORS, "right": RIGHT_ACTORS}
    columns = {"left": (column_lanes(0), column_lanes(1)), "right": (column_lanes(3), column_lanes(2))}
    system_width = 4 * column_width + 3 * COLUMN_GAP + 2 * SYSTEM_PADDING
    geometry, text = {}, dict(label)

    def place(node_id, lane_x, top):
        width, text[node_id] = wrap_label(label[node_id])
        geometry[node_id] = (snap(lane_x + (UC_WIDTH - width) / 2), top, width, UC_HEIGHT)
        return top + UC_HEIGHT

    def stack(roots, lanes, top):
        """Stack root use cases and their fans down one column from `top`; return the bottom."""
        parent_lane, child_lane = lanes
        y, previous = top, None
        for root in roots:
            child_ids = children[root]
            if previous:
                y += ITEM_GAP if previous == "single" and not child_ids else CLUSTER_GAP
            if not child_ids:
                y = place(root, parent_lane, y)
                previous = "single"
                continue
            for child in child_ids:
                y = place(child, child_lane, y) + ITEM_GAP
            y -= ITEM_GAP
            # The parent is level with the middle child; with an even count the extra child is above
            level_y = geometry[child_ids[len(child_ids) // 2]][1]
            place(root, parent_lane, level_y)
            for child in child_ids:
                x, child_y, width, height = geometry[child]
                distance = abs(child_y - level_y)
                if distance > ARC_FLAT:
                    inset = snap(
                        math.sqrt(ARC_RADIUS**2 - ARC_FLAT**2)
                        - math.sqrt(ARC_RADIUS**2 - min(distance, ARC_RADIUS) ** 2)
                    )
                    geometry[child] = (x - inset if parent_lane < child_lane else x + inset, child_y, width, height)
            previous = "cluster"
        return y

    actor_center, side_bottoms = {}, []
    actor_x = {"left": SYSTEM_X - ACTOR_OFFSET, "right": SYSTEM_X + system_width + ACTOR_OFFSET - 30}
    for side, names in bands.items():
        near_lanes, far_lanes = columns[side]
        y = SYSTEM_PADDING
        for actor in names:
            near, far = split_band([(root, children[root]) for root in roots_of[actor]])
            bottom = max(
                stack([root for root, _ in near], near_lanes, y), stack([root for root, _ in far], far_lanes, y)
            )
            bottom = max(bottom, y + ACTOR_MIN_PITCH - CLUSTER_GAP)
            top = snap((y + bottom) / 2 - 30)
            geometry[actor_id[actor]] = (actor_x[side], top, 30, 60)
            actor_center[actor_id[actor]] = top + 30
            y = bottom + CLUSTER_GAP
        side_bottoms.append(y - CLUSTER_GAP)
    system_height = max(side_bottoms) + SYSTEM_PADDING
    bottom_loop = system_height + BOTTOM_LOOP_GAP

    use_case_boxes = {node_id: box for node_id, box in geometry.items() if node_id.startswith("uc-")}
    ellipses = list(use_case_boxes.items())
    overlaps = [
        (label[a], label[b])
        for index, (a, (ax, ay, aw, ah)) in enumerate(ellipses)
        for b, (bx, by, bw, bh) in ellipses[index + 1 :]
        if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah
    ]
    if overlaps:
        sys.exit(f"Use cases overlap: {overlaps}")

    cells = [vertex("system", SYSTEM_NAME, STYLES["System"], SYSTEM_X, 0, system_width, system_height)]
    for node_id, (x, y, width, height) in geometry.items():
        cells.append(
            vertex(
                node_id,
                text[node_id],
                STYLES["Actor" if node_id.startswith("actor-") else "UseCase"],
                x,
                y,
                width,
                height,
            )
        )

    # Association routing: a line never cuts an ellipse or a fan and never runs along another line; it stays
    # straight when it can, and otherwise bends as little as possible through the gaps between blocks.
    use_case_bounds = {
        node_id: (x, y, x + width, y + height) for node_id, (x, y, width, height) in use_case_boxes.items()
    }
    center = {node_id: (x + width / 2, y + height / 2) for node_id, (x, y, width, height) in geometry.items()}
    fans = [
        (center[child], center[parent], segment_bounds(center[child], center[parent]))
        for parent, child_ids in children.items()
        for child in child_ids
    ]
    placed = []

    def segment_crossings(start, end, actor, use_case, allow_crossing=False):
        """Crossings of segment start→end with placed lines, or None when the segment breaks a rule."""
        crossings = 0
        target = use_case_boxes[use_case]
        bounds = segment_bounds(start, end, LINE_MARGIN)
        for node_id, box in use_case_boxes.items():
            if (
                node_id != use_case
                and boxes_overlap(bounds, use_case_bounds[node_id])
                and segment_hits(start, end, box)
            ):
                return None
        for child, parent, fan_bounds in fans:
            if boxes_overlap(bounds, fan_bounds):
                point = crossing(start, end, child, parent)
                if point and not segment_hits(point, point, target, 0):
                    return None
        origin = center[actor]
        near = segment_bounds(start, end, LINE_SPACING)
        for placed_start, placed_end, placed_bounds, _, placed_use_case in placed:
            if not boxes_overlap(near, placed_bounds):
                continue
            if start == origin == placed_start:
                angle = angle_between(start, end, placed_start, placed_end)
                if min(angle, 2 * math.pi - angle) < math.radians(SAME_ORIGIN_ANGLE):
                    return None
                continue
            point = crossing(start, end, placed_start, placed_end)
            if point and not (
                segment_hits(point, point, target, 0) or segment_hits(point, point, use_case_boxes[placed_use_case], 0)
            ):
                angle = angle_between(start, end, placed_start, placed_end) % math.pi
                if not allow_crossing or min(angle, math.pi - angle) < math.radians(CROSSING_MIN_ANGLE):
                    return None
                crossings += 1
                continue
            if end != placed_end and (
                min(
                    point_segment_distance(start, placed_start, placed_end),
                    point_segment_distance(end, placed_start, placed_end),
                    point_segment_distance(placed_start, start, end),
                    point_segment_distance(placed_end, start, end),
                )
                < LINE_SPACING
            ):
                return None
        return crossings

    column_bases = [SYSTEM_X + SYSTEM_PADDING + index * (column_width + COLUMN_GAP) for index in range(4)]

    def channel_ys(left, right):
        """Heights at which a line crosses the strip left..right without touching an ellipse."""
        spans = sorted(
            (y - LINE_MARGIN, y + height + LINE_MARGIN)
            for x, y, width, height in use_case_boxes.values()
            if x < right and x + width > left
        )
        result, reach = [], 0
        for low, high in spans + [(system_height + 300, system_height + 300)]:
            if low - reach >= 2:
                result += [(reach + low) / 2] if low - reach < 30 else list(range(int(reach) + 8, int(low) - 7, 15))
            reach = max(reach, high)
        return result

    lane_channels = []
    for base in column_bases:
        lane_channels.append(
            (
                channel_ys(base - 35, base + column_width + 35),
                (base - 15, base + UC_WIDTH + FAN_GAP / 2, base + column_width + 15),
            )
        )
        for lane_x in (base, base + UC_WIDTH + FAN_GAP):
            lane_channels.append((channel_ys(lane_x - 35, lane_x + UC_WIDTH + 35), (lane_x + UC_WIDTH / 2,)))
    corridors = (
        [SYSTEM_X + SYSTEM_PADDING / 2]
        + [base + column_width + COLUMN_GAP / 2 for base in column_bases[:3]]
        + [SYSTEM_X + system_width - SYSTEM_PADDING / 2]
    )

    def route(actor, use_case, allow_crossing=False):
        """Bends of the shortest lawful line from actor to use case: [] when straight, None when there is none."""
        start, goal, (x, y, width, height) = center[actor], center[use_case], use_case_boxes[use_case]
        if segment_crossings(start, goal, actor, use_case) == 0:
            return []
        low_x, high_x = min(start[0], goal[0]) - 40, max(start[0], goal[0]) + 40
        low_y, high_y = min(start[1], goal[1]) - 300, max(start[1], goal[1]) + 300
        points = {
            (x - 25, y + height / 2),
            (x + width + 25, y + height / 2),
            (x + width / 2, y - 20),
            (x + width / 2, y + height + 20),
        }
        for channel_list, lane_xs in lane_channels:
            points.update(
                (lane_x, channel_y)
                for channel_y in channel_list
                if low_y <= channel_y <= high_y
                for lane_x in lane_xs
                if low_x <= lane_x <= high_x
            )
        corridor_ys = {
            channel_y for channel_list, _ in lane_channels for channel_y in channel_list if low_y <= channel_y <= high_y
        }
        points.update(
            (corridor_x, corridor_y)
            for corridor_x in corridors
            if low_x <= corridor_x <= high_x
            for corridor_y in corridor_ys | {start[1], goal[1]}
        )
        graph = [start] + sorted(points) + [goal]
        goal_index = len(graph) - 1
        cost, previous, queue = {0: 0}, {}, [(0, 0)]
        while queue:
            current_cost, index = heapq.heappop(queue)
            if index == goal_index:
                break
            if current_cost > cost[index]:
                continue
            for next_index in range(1, len(graph)):
                new_cost = (
                    current_cost
                    + math.dist(graph[index], graph[next_index])
                    + (0 if next_index == goal_index else BEND_PENALTY)
                )
                if next_index == index or new_cost >= cost.get(next_index, math.inf):
                    continue
                crossings = segment_crossings(graph[index], graph[next_index], actor, use_case, allow_crossing)
                if crossings is None:
                    continue
                new_cost += CROSSING_PENALTY * crossings
                if new_cost < cost.get(next_index, math.inf):
                    cost[next_index], previous[next_index] = new_cost, index
                    heapq.heappush(queue, (new_cost, next_index))
        if goal_index not in previous:
            return None
        path, index = [], goal_index
        while index:
            path.append(graph[index])
            index = previous[index]
        path = [start] + path[::-1]
        # Pull the line tight: drop every bend whose shortcut is still lawful
        simplified, index = [start], 0
        while index < len(path) - 1:
            index = max(
                next_index
                for next_index in range(index + 1, len(path))
                if next_index == index + 1 or segment_crossings(path[index], path[next_index], actor, use_case) == 0
            )
            simplified.append(path[index])
        return simplified[1:-1]

    # Straight lawful lines first, then the others, shortest first
    routed, unrouted, pending = {}, [], []
    for actor, use_case in sorted(associations, key=lambda pair: math.dist(center[pair[0]], center[pair[1]])):
        if segment_crossings(center[actor], center[use_case], actor, use_case) == 0:
            routed[actor, use_case] = []
            placed.append(
                (
                    center[actor],
                    center[use_case],
                    segment_bounds(center[actor], center[use_case], LINE_SPACING),
                    actor,
                    use_case,
                )
            )
        else:
            pending.append((actor, use_case))
    for actor, use_case in pending:
        waypoints = route(actor, use_case)
        if waypoints is None:
            waypoints = route(actor, use_case, allow_crossing=True)
        if waypoints is None:
            unrouted.append(f"{label[actor]} → {label[use_case]}")
            waypoints = []
        routed[actor, use_case] = waypoints
        line = [center[actor]] + waypoints + [center[use_case]]
        placed.extend(
            (first, second, segment_bounds(first, second, LINE_SPACING), actor, use_case)
            for first, second in pairwise(line)
        )

    report = []
    if unrouted:
        report.append(f"Warning: {len(unrouted)} lines have no lawful route and stay straight: {unrouted}")
    drawn = []
    for actor, use_case in associations:
        points = [(round(x), round(y)) for x, y in routed[actor, use_case]]
        cells.append(edge(f"assoc-{actor}-{use_case}", STYLES["Association"], actor, use_case, points))
        drawn.append(([center[actor]] + points + [center[use_case]], actor, use_case))
    for parent, child_ids in children.items():
        for child in child_ids:
            cells.append(edge(f"gen-{child}", STYLES["Generalization"], child, parent))

    # Actor generalizations: adjacent actors get a straight vertical line from below the label; others get a lane
    # of their own per parent actor, around the bottom when the parent is on the other edge.
    side_of = {actor_id[actor]: side for side, names in bands.items() for actor in names}
    order = {actor_id[actor]: index for names in bands.values() for index, actor in enumerate(names)}

    def adjacent(child, parent):
        return side_of[child] == side_of[parent] and abs(order[child] - order[parent]) == 1

    lane_parents = sorted(
        {parent for child, parent in actor_parents if not adjacent(child, parent)},
        key=lambda node_id: geometry[node_id][1],
    )
    lane_index = {node_id: index for index, node_id in enumerate(lane_parents)}
    actor_lines = []
    for child, parent in actor_parents:
        style, points = STYLES["Generalization"], []
        child_x, child_top, _, _ = geometry[child]
        parent_x, parent_top, _, _ = geometry[parent]
        child_side, parent_side = side_of[child], side_of[parent]
        if adjacent(child, parent):
            if child_top < parent_top:
                style += f"exitX=0.5;exitY=1;exitDy={ACTOR_LABEL_GAP};exitPerimeter=0;entryX=0.5;entryY=0;"
                actor_lines.append([(child_x + 15, child_top + 60 + ACTOR_LABEL_GAP), (parent_x + 15, parent_top)])
            else:
                style += f"exitX=0.5;exitY=0;entryX=0.5;entryY=1;entryDy={ACTOR_LABEL_GAP};entryPerimeter=0;"
                actor_lines.append([(child_x + 15, child_top), (parent_x + 15, parent_top + 60 + ACTOR_LABEL_GAP)])
        else:
            going_down = child_side != parent_side or child_top < actor_center[parent]
            exit_y = child_top + 60 if going_down else child_top
            lane = OUTER_LANE + PARENT_LANE_STEP * lane_index[parent]
            loop_y = bottom_loop + LOOP_STEP * lane_index[parent]
            lane_x = {"left": child_x - lane, "right": child_x + 30 + lane}[child_side]
            points = [(lane_x, exit_y)]
            if child_side != parent_side:
                if parent_side != "left":
                    sys.exit("An actor on the left edge cannot inherit from an actor on the right edge")
                lane_x = parent_x - lane
                points += [(points[0][0], loop_y), (lane_x, loop_y)]
            points.append((lane_x, actor_center[parent]))
            style += (
                f"exitX={0 if child_side == 'left' else 1};exitY={1 if going_down else 0};"
                f"entryX={0 if parent_side == 'left' else 1};entryY=0.5;jumpStyle=arc;jumpSize=10;"
            )
            exit_x = child_x if child_side == "left" else child_x + 30
            entry_x = parent_x if parent_side == "left" else parent_x + 30
            actor_lines.append([(exit_x, exit_y)] + points + [(entry_x, actor_center[parent])])
        cells.append(edge(f"gen-{child}", style, child, parent, points))

    # Check the lines as draw.io draws them
    cuts, fan_cuts, cross_points = set(), set(), []
    for index, (line, source, target) in enumerate(drawn):
        name = f"{label[source]} – {label[target]}"
        ends = [use_case_boxes[target]]
        for first, second in pairwise(line):
            if any(
                node_id != target and segment_hits(first, second, box, 0) for node_id, box in use_case_boxes.items()
            ):
                cuts.add(name)
            for child, parent, _ in fans:
                point = crossing(first, second, child, parent)
                if point and not segment_hits(point, point, ends[0], 0):
                    fan_cuts.add(name)
            for other_line, other_source, other_target in drawn[index + 1 :]:
                other_end = use_case_boxes[other_target]
                for other_first, other_second in pairwise(other_line):
                    point = crossing(first, second, other_first, other_second)
                    if point and not (
                        segment_hits(point, point, ends[0], 0) or segment_hits(point, point, other_end, 0)
                    ):
                        cross_points.append(f"{name} × {label[other_source]} – {label[other_target]}")
    association_lines = [line for line, _, _ in drawn]
    actor_crossings = sum(
        1
        for index, line in enumerate(actor_lines)
        for other in actor_lines[index + 1 :] + association_lines
        for first, second in pairwise(line)
        for other_first, other_second in pairwise(other)
        if crossing(first, second, other_first, other_second)
    )
    detours = sorted(
        (
            (
                sum(math.dist(first, second) for first, second in pairwise(line)) - math.dist(line[0], line[-1]),
                source,
                target,
            )
            for line, source, target in drawn
        ),
        reverse=True,
    )
    bends = Counter(len(waypoints) for waypoints in routed.values())
    report += [
        f"Lines cutting a use case: {sorted(cuts)}",
        f"Lines cutting a fan: {sorted(fan_cuts)}",
        f"Association crossings: {len(cross_points)} {cross_points}",
        f"Actor generalization crossings: {actor_crossings}",
        f"Detours over {DETOUR_REPORT} px: "
        + str(
            [
                f"{label[source]} – {label[target]} ({extra:.0f})"
                for extra, source, target in detours
                if extra > DETOUR_REPORT
            ]
        ),
        f"System {system_width}x{system_height}; associations by bends: {dict(sorted(bends.items()))}",
    ]
    return cells, report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT
    actors, use_cases = read_model(README)
    check_model(actors, use_cases)
    print(f"{len(actors)} actors, {len(use_cases)} use cases")
    cells, report = peacock(actors, use_cases)
    print("\n".join(report))
    content = (
        '<mxfile><diagram id="medilab-use-case" name="Use cases"><mxGraphModel><root><mxCell id="0"/>'
        '<mxCell id="1" parent="0"/>' + "\n".join(cells) + "</root></mxGraphModel></diagram></mxfile>\n"
    )
    output.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
