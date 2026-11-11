"""Reads and fills the data bindings of report DOCX files. A binding is a content control whose tag names it, such as
medilab:customer_name, in the body, a header or a footer. MediLab fills each binding from business records and locks
it, and reads the bindings back to check that a saved document still prints the values of the records."""

import io
import re
import zipfile

from lxml import etree

from odoo.addons.sol_laboratory.constants.report_templates import BINDING_TAG_PREFIX

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
# The parts of a document that print text: its body, headers and footers.
TEXT_PARTS = re.compile(r"word/(document|header\d*|footer\d*)\.xml\Z")
# The largest part read, uncompressed, so a crafted file cannot exhaust memory.
MAX_PART_SIZE = 50 * 1024 * 1024
# Neither the editor nor the template author can delete a locked binding or change its text.
LOCKED = "sdtContentLocked"
# A4 with 2 cm margins, in twentieths of a point.
PAGE = {"w": "11906", "h": "16838"}
MARGIN = "1134"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
PACKAGE_RELATIONSHIPS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


class ReportDocumentInvalid(Exception):
    """The file is not a DOCX document MediLab can read."""


def paragraph(text, bold=False):
    """A block of a block binding: one paragraph."""
    return ("paragraph", text, bold)


def table(header, rows):
    """A block of a block binding: a table with a bold header row."""
    return ("table", list(header), [list(row) for row in rows])


def bindings(docx):
    """The text each binding of the document prints, by binding name, once per content control: a name used twice has
    two texts. Whitespace is collapsed, as the editor may wrap and split the text it keeps."""
    found = {}
    for root in _parts(docx).values():
        for name, control in _controls(root):
            found.setdefault(name, []).append(_text(_content(control)))
    return found


def block_bindings(docx):
    """The names of the bindings placed as paragraphs of their own, which can hold paragraphs and tables."""
    return {name for root in _parts(docx).values() for name, control in _controls(root) if _is_block(_content(control))}


def fill(docx, values):
    """The document with each binding named in values holding its value, locked: a text for a scalar binding, a list
    of paragraph() and table() blocks for a block binding."""
    parts = _parts(docx)
    for root in parts.values():
        for name, control in list(_controls(root)):
            if name in values:
                _set(control, values[name])
    return _write(docx, parts)


def starter(title, labels, block_labels):
    """A first template: the title, then each scalar binding after its label, then each block binding under its
    heading, every binding locked against deletion."""
    body = etree.Element(_w("body"))
    body.append(_paragraph(title, bold=True))
    for name, label in labels.items():
        line = _paragraph(f"{label}: ")
        line.append(_control(name, _run(f"[{label}]")))
        body.append(line)
    for name, label in block_labels.items():
        body.append(_paragraph(label, bold=True))
        body.append(_control(name, _paragraph(f"[{label}]")))
    section = etree.SubElement(body, _w("sectPr"))
    etree.SubElement(section, _w("pgSz"), {_w(key): value for key, value in PAGE.items()})
    etree.SubElement(section, _w("pgMar"), {_w(side): MARGIN for side in ("top", "right", "bottom", "left")})
    document = etree.Element(_w("document"), nsmap={"w": W})
    document.append(body)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELATIONSHIPS)
        archive.writestr("word/document.xml", _xml(document))
    return buffer.getvalue()


def _w(name):
    return f"{{{W}}}{name}"


def _parts(docx):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        with zipfile.ZipFile(io.BytesIO(docx)) as archive:
            parts = {}
            for info in archive.infolist():
                if not TEXT_PARTS.fullmatch(info.filename):
                    continue
                if info.file_size > MAX_PART_SIZE:
                    raise ReportDocumentInvalid(f"{info.filename} is too large.")
                parts[info.filename] = etree.fromstring(archive.read(info), parser)
    except (zipfile.BadZipFile, etree.XMLSyntaxError, KeyError, ValueError) as error:
        raise ReportDocumentInvalid(str(error)) from None
    if "word/document.xml" not in parts:
        raise ReportDocumentInvalid("The file has no document body.")
    return parts


def _write(docx, parts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx)) as source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = _xml(parts[info.filename]) if info.filename in parts else source.read(info)
            target.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def _xml(root):
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _controls(root):
    # Outer controls first; a binding inside another binding's content is replaced with it.
    for control in root.iter(_w("sdt")):
        tag = control.find("w:sdtPr/w:tag", NS)
        name = tag.get(_w("val"), "") if tag is not None else ""
        if name.startswith(BINDING_TAG_PREFIX):
            yield name.removeprefix(BINDING_TAG_PREFIX), control


def _content(control):
    content = control.find("w:sdtContent", NS)
    if content is None:
        content = etree.SubElement(control, _w("sdtContent"))
    return content


def _is_block(content):
    return any(child.tag in (_w("p"), _w("tbl")) for child in content)


def _text(element):
    lines = list(element.iter(_w("p"))) or [element]
    return " ".join(" ".join("".join(node.text or "" for node in line.iter(_w("t"))).split()) for line in lines).strip()


def _set(control, value):
    properties = control.find("w:sdtPr", NS)
    for old in properties.findall("w:lock", NS) + properties.findall("w:showingPlcHdr", NS):
        properties.remove(old)
    etree.SubElement(properties, _w("lock"), {_w("val"): LOCKED})
    content = _content(control)
    block = _is_block(content)
    style = content.find(".//w:rPr", NS)
    for child in list(content):
        content.remove(child)
    if block:
        for element in [_paragraph(value)] if isinstance(value, str) else [_block(item) for item in value]:
            content.append(element)
    else:
        text = value if isinstance(value, str) else " ".join(_text(_block(item)) for item in value)
        content.append(_run(text, style))


def _block(item):
    kind, *values = item
    if kind == "paragraph":
        return _paragraph(*values)
    header, rows = values
    grid = etree.Element(_w("tbl"))
    properties = etree.SubElement(grid, _w("tblPr"))
    etree.SubElement(properties, _w("tblW"), {_w("w"): "5000", _w("type"): "pct"})
    borders = etree.SubElement(properties, _w("tblBorders"))
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        etree.SubElement(borders, _w(side), {_w("val"): "single", _w("sz"): "4", _w("space"): "0", _w("color"): "auto"})
    columns = etree.SubElement(grid, _w("tblGrid"))
    for _column in header:
        etree.SubElement(columns, _w("gridCol"), {_w("w"): str(9638 // max(len(header), 1))})
    for cells, bold in [(header, True)] + [(row, False) for row in rows]:
        line = etree.SubElement(grid, _w("tr"))
        for cell in cells:
            column = etree.SubElement(line, _w("tc"))
            column.append(_paragraph(cell, bold))
    return grid


def _paragraph(text, bold=False):
    line = etree.Element(_w("p"))
    if text:
        line.append(_run(text, bold=bold))
    return line


def _run(text, style=None, bold=False):
    run = etree.Element(_w("r"))
    if style is not None:
        run.append(etree.fromstring(etree.tostring(style)))
    elif bold:
        etree.SubElement(etree.SubElement(run, _w("rPr")), _w("b"))
    node = etree.SubElement(run, _w("t"))
    node.text = text
    node.set(XML_SPACE, "preserve")
    return run


def _control(name, element):
    control = etree.Element(_w("sdt"))
    properties = etree.SubElement(control, _w("sdtPr"))
    etree.SubElement(properties, _w("tag"), {_w("val"): BINDING_TAG_PREFIX + name})
    etree.SubElement(properties, _w("lock"), {_w("val"): "sdtLocked"})
    etree.SubElement(control, _w("sdtContent")).append(element)
    return control
