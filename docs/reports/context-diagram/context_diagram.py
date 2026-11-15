"""Generate the MediLab context diagram (DFD level 0) as medilab-context.drawio next to this script.

Entities stand in two columns and every flow is a straight horizontal line between an entity box and the system
circle. The entities and flows below are the table "Entities and flows" of readme.md next to this script; change both.
"""

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SPACING = 24  # vertical distance between two flows
GAP = 18  # space between two entity boxes
PAD = 10  # space above the first and below the last flow of a box
BOX_W = 210
LEFT_X = 40
TOP = 40
MIN_GAP = 160  # shortest distance from a box to the far side of the circle
LABEL_CHAR_W = 6.6  # average width of a 12px label character
LABEL_MARGIN = 50  # free line left around a label, both sides together
SYSTEM_NAME = (
    "MediLab<br>Laboratory Information Management Subsystem for a Contract Testing Laboratory on the Odoo Platform"
)

# (entity, flows into the system, flows out of the system)
LEFT = [
    (
        "Customer",
        ["Registration and Profile", "Test Orders", "Quotation Responses and Cancellation Requests",
         "Support Requests and Ratings"],
        ["Quotations and Payment Links", "Invoices and Receipts", "Order Status, Notices and Support Replies",
         "Issued Test Reports"],
    ),
    (
        "Sales",
        ["Customer Records and Portal Invitations", "Quotations, Revisions and Templates",
         "Order Confirmations, Collection Starts and Cancellations", "Payment Records"],
        ["Order Queue and Tasks", "Return Estimates and Risk Notices", "Pipeline and KPI Reports"],
    ),
    (
        "Head of Sales",
        ["Approval Thresholds", "Quotation Approvals", "Credit Flags", "Cancellation Approvals"],
        ["Quotations Pending Approval", "All Orders and Sales Statistics"],
    ),
    (
        "Accountant",
        ["Invoices and Adjustments", "Payment Confirmations and Rejections", "Daily Reconciliation Locks"],
        ["Invoice and Payment Status", "Receivables and Overdue Lists", "Financial Reports",
         "Daily Gateway Transactions"],
    ),
    (
        "Sample Delivery Staff",
        ["Collection Plans", "Collection Records and Customer Signatures", "Sample Receipts, Labels and Handovers",
         "Report Deliveries and Sample Returns"],
        ["Collection Tasks and Reminders", "Expected Samples", "Dispatches to Carry and Reports to Deliver"],
    ),
]
RIGHT = [
    (
        "Lab Head",
        ["Parameter Authorizations", "Report Signatures and Rejections", "Regulation Basis Confirmations",
         "Report Change Approvals"],
        ["Signing Tasks and Prepared Reports", "Lab-wide Statistics"],
    ),
    (
        "Head of Department",
        ["Task Assignments and Booking Moves", "Result Approvals and Rejections", "Subcontractor Dispatches",
         "Department Receipts and Re-collection Requests"],
        ["Department Queue and Summaries", "Risk and Insufficient-Sample Notices", "Outsourcing Suggestions"],
    ),
    (
        "Tester",
        ["Task Claims and Booking Changes", "Test Results and Retests", "Laboratory Files",
         "Change Requests and Sample Disposals"],
        ["To-do List and Reminders", "Method Steps and Locations", "Rejection Reasons and Warnings"],
    ),
    (
        "Administrator",
        ["Master Data and Prices", "People, Roles and Approval Chains", "Settings and Integration Credentials",
         "Sync Folders and Devices"],
        ["Expiry and Failed-Job Alerts", "Audit Trail and Archives"],
    ),
    ("Subcontractor", ["Subcontractor Results"], ["Dispatches", "Rejected Results with Reasons"]),
    ("Payment Gateway", ["Checkout Links and Payment Notifications"], ["Payment Link Requests and Status Polls"]),
    ("Email Service", ["Delivery Status Events"], ["Outgoing E-mails"]),
    ("Digital Signature Provider", ["Signatures and Certificate Status"], ["Signing Requests and Certificate Queries"]),
]

ENTITY_STYLE = "rounded=0;whiteSpace=wrap;html=1;fontStyle=0;fontSize=25;fillColor=#ffffff;strokeColor=#000000;"
SYSTEM_STYLE = (
    "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=none;strokeColor=#000000;strokeWidth=2;"
    "fontSize=60;fontStyle=1;"
)
EDGE_STYLE = "html=1;endArrow=classic;endFill=1;labelBackgroundColor=#ffffff;fontSize=12;"


def column_height(entities):
    """Height of an entity column: its boxes and the space between them."""
    flows = sum(len(inputs) + len(outputs) for _, inputs, outputs in entities)
    return flows * SPACING + len(entities) * (2 * PAD + GAP) - GAP


# The circle spans the tallest column: its top meets the first box, its bottom the last box
RADIUS = max(column_height(LEFT), column_height(RIGHT)) / 2
CENTER_Y = TOP + RADIUS


def column_layout(entities):
    """Return each box's name, top and height with its flows; inbound flows come first in a box."""
    y = CENTER_Y - column_height(entities) / 2
    boxes = []
    for name, inputs, outputs in entities:
        flows = [(label, True) for label in inputs] + [(label, False) for label in outputs]
        height = len(flows) * SPACING + 2 * PAD
        lanes = [(label, inbound, y + PAD + (lane + 0.5) * SPACING) for lane, (label, inbound) in enumerate(flows)]
        boxes.append((name, y, height, lanes))
        y += height + GAP
    return boxes


def circle_offset(flow_y):
    """Horizontal distance from the circle's centre to where a flow at this height meets it."""
    offset = flow_y - CENTER_Y
    return math.sqrt(RADIUS * RADIUS - offset * offset)


def column_gap(boxes):
    """Shortest box-to-circle distance that leaves every label of the column room on its line."""
    needed = [
        len(label) * LABEL_CHAR_W + LABEL_MARGIN - (RADIUS - circle_offset(flow_y))
        for _, _, _, lanes in boxes
        for label, _, flow_y in lanes
    ]
    return max(MIN_GAP, *needed)


LEFT_BOXES = column_layout(LEFT)
RIGHT_BOXES = column_layout(RIGHT)
CENTER_X = LEFT_X + BOX_W + column_gap(LEFT_BOXES) + RADIUS
RIGHT_X = CENTER_X + RADIUS + column_gap(RIGHT_BOXES)


def column_cells(boxes, box_x, side, first_edge):
    """Return the cells of one column's boxes and flows; side is -1 on the left and 1 on the right."""
    cells = []
    edge_number = first_edge
    for index, (name, y, height, lanes) in enumerate(boxes):
        entity_id = f"e{side}{index}"
        cells.append(
            f'<mxCell id="{entity_id}" value="{escape(name)}" style="{ENTITY_STYLE}" vertex="1" parent="1">'
            f'<mxGeometry x="{box_x}" y="{round(y, 1)}" width="{BOX_W}" height="{height}" as="geometry"/></mxCell>'
        )
        for label, inbound, flow_y in lanes:
            # A fixed point exactly on the circle (perimeter=0) keeps draw.io from projecting the line elsewhere
            circle_x = CENTER_X + side * circle_offset(flow_y)
            circle_point = (
                round((circle_x - (CENTER_X - RADIUS)) / (2 * RADIUS), 4),
                round((flow_y - (CENTER_Y - RADIUS)) / (2 * RADIUS), 4),
            )
            box_point = (0 if side == 1 else 1, round((flow_y - y) / height, 4))
            source, target = (entity_id, "sys") if inbound else ("sys", entity_id)
            exit_point, entry_point = (box_point, circle_point) if inbound else (circle_point, box_point)
            style = (
                f"{EDGE_STYLE}exitX={exit_point[0]};exitY={exit_point[1]};exitDx=0;exitDy=0;exitPerimeter=0;"
                f"entryX={entry_point[0]};entryY={entry_point[1]};entryDx=0;entryDy=0;entryPerimeter=0;"
            )
            cells.append(
                f'<mxCell id="f{edge_number}" value="{escape(label)}" style="{style}" edge="1" parent="1" '
                f'source="{source}" target="{target}"><mxGeometry relative="1" as="geometry"/></mxCell>'
            )
            edge_number += 1
    return cells, edge_number


output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("medilab-context.drawio")
left_cells, edge_total = column_cells(LEFT_BOXES, LEFT_X, -1, 0)
right_cells, edge_total = column_cells(RIGHT_BOXES, RIGHT_X, 1, edge_total)
system_cell = (
    f'<mxCell id="sys" value="{escape(SYSTEM_NAME)}" style="{SYSTEM_STYLE}" vertex="1" parent="1">'
    f'<mxGeometry x="{CENTER_X - RADIUS}" y="{CENTER_Y - RADIUS}" width="{2 * RADIUS}" height="{2 * RADIUS}" '
    f'as="geometry"/></mxCell>'
)
cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>', system_cell, *left_cells, *right_cells]
output_path.write_text(
    '<mxfile><diagram id="medilab-context" name="MediLab Context"><mxGraphModel grid="0" page="0"><root>'
    + "".join(cells)
    + "</root></mxGraphModel></diagram></mxfile>",
    encoding="utf-8",
)
print(f"{output_path}: {len(LEFT) + len(RIGHT)} entities, {edge_total} flows")
