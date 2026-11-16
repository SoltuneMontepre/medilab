"""Write the feature list workbook that accompanies BM04 from the tables of readme.md next to this script.

The workbook holds every feature in the columns of the mandatory features table in section 3 of BM04. The script also
checks that business-flows.md lists the features each flow owns, and writes the comparison with the previous version.
Run: uv run --with openpyxl python docs/reports/feature-list/feature_list.py
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import business_flows
import comparison
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
README = HERE / "readme.md"
BM04 = HERE.parent / "BM04_hoang"
VERSION = "v1.1"
PREVIOUS_VERSION = "v1.0"
OUTPUT = BM04 / f"SWP490_GFA26SE153_Feature_List_{VERSION}.xlsx"
PREVIOUS = BM04 / f"SWP490_GFA26SE153_Feature_List_{PREVIOUS_VERSION}.xlsx"
COMPARISON = f"SWP490_GFA26SE153_Feature_List_{PREVIOUS_VERSION}-vs-{VERSION}"
INDEX_COLUMNS = ["ID", "Feature", "Actor", "Workflow", "Mandatory", "Owner"]
WORKBOOK_COLUMNS = {"ID": 7, "Feature": 34, "Actor": 26, "Acceptance criteria": 90, "Workflow": 11, "Owner": 22}
KINDS = ("Main", "Rule", "Exception")
ID_LINK = re.compile(r"\[(F-\d{2})\]\(#([\w-]+)\)")
HEADING = re.compile(r"### (F-\d{2}) (.+)")
CRITERION = re.compile(r"- TC-F(\d{2})-(\d{2}) (\w+): (.+)")
WORKFLOW = re.compile(r"WF-0[1-6]|SF-\d{2}|Every flow")
HEADER_FILL = "14233A"


@dataclass
class Feature:
    id: str
    name: str
    actor: str
    workflow: str
    mandatory: str
    owner: str
    anchor: str


def slug(heading):
    """The anchor GitHub gives a heading."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def section(lines, title):
    """The lines under the `## title` heading, up to the next `## ` heading."""
    start = lines.index(f"## {title}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start:end]


def read_index(lines, errors):
    """The features of the Features table, in table order."""
    rows = [line for line in section(lines, "Features") if line.startswith("|")]
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    if header != INDEX_COLUMNS:
        errors.append(f"Features table columns are {header}, expected {INDEX_COLUMNS}")
        return []
    features = []
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        link = ID_LINK.fullmatch(cells[0])
        if len(cells) != len(INDEX_COLUMNS) or not link:
            errors.append(f"Features row without {len(INDEX_COLUMNS)} cells and an ID link: {row}")
            continue
        features.append(Feature(link.group(1), *cells[1:], anchor=link.group(2)))
    return features


def read_criteria(lines, errors):
    """The heading name and the criteria of each feature of the Acceptance criteria section."""
    criteria = {}
    current = None
    for line in section(lines, "Acceptance criteria"):
        heading = HEADING.fullmatch(line)
        if heading:
            current = heading.group(1)
            if current in criteria:
                errors.append(f"{current} has two sections")
            criteria[current] = {"name": heading.group(2)}
        elif line.startswith("- "):
            match = CRITERION.fullmatch(line)
            if not current or not match:
                errors.append(f"Criterion not in the form '- TC-Fnn-0n Kind: text': {line}")
                continue
            number, index, kind, text = match.groups()
            expected = KINDS[len(criteria[current]) - 1] if len(criteria[current]) <= len(KINDS) else None
            if f"F-{number}" != current or kind != expected or int(index) != KINDS.index(kind) + 1:
                errors.append(f"{current}: expected TC-{current.replace('-', '')}-0n {expected}, found {line}")
            criteria[current][kind] = text
    return criteria


def check(features, criteria, errors):
    """Add an error for every inconsistency between the table and the sections."""
    ids = [feature.id for feature in features]
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        errors.append("Feature IDs in the Features table are not unique and ascending")
    for feature in features:
        name = f"{feature.id} {feature.name}"
        if feature.anchor != slug(name):
            errors.append(f"{feature.id} links to #{feature.anchor}, its section is #{slug(name)}")
        if not WORKFLOW.fullmatch(feature.workflow):
            errors.append(f"{feature.id} has workflow '{feature.workflow}'")
        if feature.mandatory not in ("Yes", "No"):
            errors.append(f"{feature.id} has mandatory '{feature.mandatory}', expected Yes or No")
        if feature.mandatory == "Yes" and not feature.owner:
            errors.append(f"{feature.id} is mandatory and has no owner")
        found = criteria.get(feature.id)
        if not found:
            errors.append(f"{feature.id} has no section in Acceptance criteria")
            continue
        if found["name"] != feature.name:
            errors.append(f"{feature.id} is '{feature.name}' in the table and '{found['name']}' in its section")
        missing = [kind for kind in KINDS if kind not in found]
        if missing:
            errors.append(f"{feature.id} has no {', '.join(missing)} criterion")
    for extra in sorted(set(criteria) - set(ids)):
        errors.append(f"{extra} has a section but no row in the Features table")


def workbook_rows(features, criteria):
    """Each feature in the columns of the workbook."""
    rows = []
    for feature in features:
        acceptance = " ".join(f"{kind}: {criteria[feature.id][kind]}" for kind in KINDS)
        rows.append((feature.id, feature.name, feature.actor, acceptance, feature.workflow, feature.owner or None))
    return rows


def write(rows):
    """Write the workbook, styled like the one submitted with BM04."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Features"
    sheet.append(list(WORKBOOK_COLUMNS))
    for row in rows:
        sheet.append(list(row))
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column, width in zip("ABCDEF", WORKBOOK_COLUMNS.values()):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions
    book.save(OUTPUT)


def main():
    lines = README.read_text(encoding="utf-8").splitlines()
    errors = []
    features = read_index(lines, errors)
    criteria = read_criteria(lines, errors)
    check(features, criteria, errors)
    business_flows.check(features, errors)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    rows = workbook_rows(features, criteria)
    write(rows)
    print(f"Wrote {len(features)} features to {OUTPUT.relative_to(HERE.parents[2]).as_posix()}")
    compared = comparison.write(
        PREVIOUS,
        rows,
        (PREVIOUS_VERSION, VERSION),
        BM04 / f"{COMPARISON}.xlsx",
        BM04 / f"{COMPARISON}.pdf",
    )
    changed = sum(change is not None for _, change in compared)
    print(f"Wrote the comparison with {PREVIOUS_VERSION}: {changed} features changed")


if __name__ == "__main__":
    main()
