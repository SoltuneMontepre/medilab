"""Check that business-flows.md lists, for each flow, the features the feature list says it owns."""

import re
from collections import defaultdict
from pathlib import Path

FLOWS = Path(__file__).resolve().parents[2] / "functional" / "business-flows.md"
FEATURE_LINK = re.compile(r"\[(F-\d{2})\]\(\.\./reports/feature-list/readme\.md#([\w-]+)\)")
FLOW_HEADING = re.compile(r"## ((?:WF|SF)-\d{2}) ")
FEATURES_LINE = "- **Features:** "
EVERY_FLOW_LINE = "Every flow uses "
EVERY_FLOW = "Every flow"


def owned_features(features):
    """The IDs of the features each workflow owns, in ID order."""
    owned = defaultdict(list)
    for feature in features:
        owned[feature.workflow].append(feature.id)
    return owned


def check_links(where, line, expected, anchors, errors):
    """Add an error when the feature links of a line are not the expected features, or link to another section."""
    links = FEATURE_LINK.findall(line)
    found = [feature_id for feature_id, _ in links]
    if found != expected:
        errors.append(f"business-flows.md: {where} lists {found}, the feature list gives {expected}")
    for feature_id, anchor in links:
        if anchors.get(feature_id) != anchor:
            errors.append(f"business-flows.md: {where} links {feature_id} to #{anchor}")


def check_table(lines, owned, errors):
    """Check the Features column of the flow table."""
    start = next(i for i, line in enumerate(lines) if line.startswith("| Flow "))
    rows = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    if "Features" not in rows[0]:
        errors.append("business-flows.md: the flow table has no Features column")
        return
    column = rows[0].index("Features")
    for row in rows[2:]:
        found = [cell for cell in row[column].split(", ") if cell]
        if found != owned.get(row[0], []):
            errors.append(
                f"business-flows.md: the table lists {found} for {row[0]}, the feature list gives {owned.get(row[0], [])}"
            )
    missing = set(owned) - {row[0] for row in rows[2:]} - {EVERY_FLOW}
    if missing:
        errors.append(f"business-flows.md: the flow table has no row for {', '.join(sorted(missing))}")


def check(features, errors):
    """Add an error for every place where business-flows.md and the feature list disagree on who owns a feature."""
    owned = owned_features(features)
    anchors = {feature.id: feature.anchor for feature in features}
    lines = FLOWS.read_text(encoding="utf-8").splitlines()
    check_table(lines, owned, errors)
    every_flow = [line for line in lines if line.startswith(EVERY_FLOW_LINE)]
    if len(every_flow) != 1:
        errors.append(f"business-flows.md: expected one line starting '{EVERY_FLOW_LINE}', found {len(every_flow)}")
    else:
        check_links("the every-flow line", every_flow[0], owned.get(EVERY_FLOW, []), anchors, errors)
    flow = None
    listed = set()
    for line in lines:
        heading = FLOW_HEADING.match(line)
        if heading:
            flow = heading.group(1)
        elif flow and line.startswith(FEATURES_LINE):
            check_links(flow, line, owned.get(flow, []), anchors, errors)
            listed.add(flow)
    for flow in sorted(set(owned) - listed - {EVERY_FLOW}):
        errors.append(f"business-flows.md: {flow} has no '{FEATURES_LINE.strip()}' line")
