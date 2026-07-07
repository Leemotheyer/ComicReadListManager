import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

from app.models import ReadList, ReadListItem

READING_LIST_NS = {
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "readlist"


def generate_cbl(read_list: ReadList) -> str:
    root = ET.Element("ReadingList")
    root.set("xmlns:xsd", READING_LIST_NS["xsd"])
    root.set("xmlns:xsi", READING_LIST_NS["xsi"])

    name_el = ET.SubElement(root, "Name")
    name_el.text = read_list.name

    books_el = ET.SubElement(root, "Books")
    for item in read_list.items:
        attrs = {
            "Series": item.series,
            "Number": item.issue_number,
        }
        if item.volume_year is not None:
            attrs["Volume"] = str(item.volume_year)
        if item.cover_year is not None:
            attrs["Year"] = str(item.cover_year)

        book_el = ET.SubElement(books_el, "Book", attrs)
        if item.notes:
            notes_el = ET.SubElement(book_el, "Notes")
            notes_el.text = item.notes
        db_el = ET.SubElement(
            book_el,
            "Database",
            {
                "Name": "cv",
                "Series": f"4050-{item.cv_volume_id}",
                "Issue": f"4000-{item.cv_issue_id}",
            },
        )
        _ = db_el  # noqa: F841 — element attached to tree

    ET.SubElement(root, "Matchers")

    rough = ET.tostring(root, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding=None)


def export_filename(read_list: ReadList) -> str:
    return f"{_slugify(read_list.name)}.cbl"
