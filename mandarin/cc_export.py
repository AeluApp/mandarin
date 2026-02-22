"""IMS Common Cartridge 1.3 export.

Exports vocabulary content as a CC ZIP file with QTI 2.1 assessments.
"""

from __future__ import annotations

import io
import logging
import random
import xml.etree.ElementTree as ET
from typing import List, Optional
from zipfile import ZipFile

from . import db

logger = logging.getLogger(__name__)


def _qti_item_xml(item_id: int, hanzi: str, pinyin: str,
                  english: str, distractors: List[str]) -> str:
    """Generate QTI 2.1 XML for a single vocabulary assessment item."""
    root = ET.Element("assessmentItem", {
        "xmlns": "http://www.imsglobal.org/xsd/imsqti_v2p1",
        "identifier": f"item_{item_id}",
        "title": hanzi,
        "adaptive": "false",
        "timeDependent": "false",
    })

    # Response declaration
    resp = ET.SubElement(root, "responseDeclaration", {
        "identifier": "RESPONSE",
        "cardinality": "single",
        "baseType": "identifier",
    })
    correct = ET.SubElement(resp, "correctResponse")
    ET.SubElement(correct, "value").text = "choice_correct"

    # Item body
    body = ET.SubElement(root, "itemBody")
    p = ET.SubElement(body, "p")
    p.text = f"What does {hanzi} ({pinyin}) mean?"

    interaction = ET.SubElement(body, "choiceInteraction", {
        "responseIdentifier": "RESPONSE",
        "shuffle": "true",
        "maxChoices": "1",
    })

    # Correct choice
    choice = ET.SubElement(interaction, "simpleChoice", {"identifier": "choice_correct"})
    choice.text = english

    # Distractors
    for i, d in enumerate(distractors[:3]):
        choice = ET.SubElement(interaction, "simpleChoice", {"identifier": f"choice_{i}"})
        choice.text = d

    # Response processing
    processing = ET.SubElement(root, "responseProcessing", {
        "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct",
    })

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _manifest_xml(resource_ids: List[str]) -> str:
    """Generate imsmanifest.xml for the Common Cartridge package."""
    ns = "http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1"
    root = ET.Element("manifest", {
        "xmlns": ns,
        "xmlns:lom": "http://ltsc.ieee.org/xsd/LOM",
        "identifier": "mandarin_cc_export",
    })

    # Metadata
    metadata = ET.SubElement(root, "metadata")
    schema = ET.SubElement(metadata, "schema")
    schema.text = "IMS Common Cartridge"
    version = ET.SubElement(metadata, "schemaversion")
    version.text = "1.3.0"

    # Organizations
    orgs = ET.SubElement(root, "organizations")
    org = ET.SubElement(orgs, "organization", {"identifier": "org_1"})
    for rid in resource_ids:
        item = ET.SubElement(org, "item", {"identifier": f"item_{rid}", "identifierref": rid})
        title = ET.SubElement(item, "title")
        title.text = f"Vocabulary Quiz {rid}"

    # Resources
    resources = ET.SubElement(root, "resources")
    for rid in resource_ids:
        res = ET.SubElement(resources, "resource", {
            "identifier": rid,
            "type": "imsqti_xmlv2p1",
            "href": f"assessments/{rid}.xml",
        })
        ET.SubElement(res, "file", {"href": f"assessments/{rid}.xml"})

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def export_cc(conn, user_id: int, hsk_level: Optional[int] = None) -> bytes:
    """Export vocabulary content as a Common Cartridge ZIP.

    Args:
        conn: Database connection.
        user_id: User ID (for progress-aware distractor selection).
        hsk_level: Optional HSK level filter (1-9).

    Returns:
        ZIP file bytes.
    """
    query = "SELECT id, hanzi, pinyin, english FROM content_item WHERE 1=1"
    params: list = []

    if hsk_level:
        query += " AND hsk_level = ?"
        params.append(hsk_level)

    query += " ORDER BY hsk_level, id"
    items = conn.execute(query, params).fetchall()

    if not items:
        # Return empty CC package
        buf = io.BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("imsmanifest.xml", _manifest_xml([]))
        return buf.getvalue()

    # Collect all English translations for distractor pool
    all_english = [row["english"] for row in items]

    resource_ids = []
    assessment_files = {}

    for item in items:
        rid = f"vocab_{item['id']}"
        resource_ids.append(rid)

        # Select distractors (other items' translations)
        distractors = [e for e in all_english if e != item["english"]]
        # Take up to 3 distractors, deterministic per item
        rng = random.Random(item["id"])
        distractors = rng.sample(distractors, min(3, len(distractors)))

        qti_xml = _qti_item_xml(
            item["id"], item["hanzi"], item["pinyin"],
            item["english"], distractors,
        )
        assessment_files[f"assessments/{rid}.xml"] = qti_xml

    # Build ZIP
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("imsmanifest.xml", _manifest_xml(resource_ids))
        for path, content in assessment_files.items():
            zf.writestr(path, content)

    logger.info("cc_export.generated", extra={
        "user_id": user_id,
        "hsk_level": hsk_level,
        "item_count": len(items),
    })

    return buf.getvalue()
