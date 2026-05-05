"""Normalize guest-visible Airbnb photo and product evidence.

The helper is deterministic and local-only. It consumes text and optional image
labels already collected by public or own-listing workflows, then returns fields
that can be compared across own listings and public comps.
"""

from __future__ import annotations

import re


SUBJECT_PATTERNS = [
    ("parking", r"\b(parking|car park|garage|ev charger|driveway)\b"),
    ("pool_or_spa", r"\b(pool|spa|hot tub|jacuzzi|sauna)\b"),
    ("view", r"\b(view|skyline|balcony|terrace|river|ocean|harbour|city view)\b"),
    ("workspace", r"\b(workspace|desk|office|monitor|work station|ethernet)\b"),
    ("bedroom", r"\b(bedroom|bed|king|queen|single bed|bunk)\b"),
    ("bathroom", r"\b(bathroom|bath|shower|ensuite|toilet)\b"),
    ("kitchen", r"\b(kitchen|cooktop|oven|stove|fridge|dishwasher)\b"),
    ("living_area", r"\b(living|lounge|sofa|couch|tv room|dining)\b"),
    ("family", r"\b(cot|crib|high chair|children|kids|baby|family)\b"),
    ("pet", r"\b(pet|dog|cat|pet friendly|pets allowed)\b"),
    ("self_checkin", r"\b(self check[- ]?in|lockbox|smart lock|keypad)\b"),
    ("laundry", r"\b(washer|dryer|laundry|washing machine)\b"),
    ("air_conditioning", r"\b(air conditioning|air con|a/c|heating)\b"),
    ("exterior", r"\b(exterior|building|facade|entrance|lobby|street)\b"),
]

CORE_ROOM_SUBJECTS = {
    "bedroom": "bedroom_proof_flag",
    "bathroom": "bathroom_proof_flag",
    "kitchen": "kitchen_proof_flag",
    "living_area": "living_area_proof_flag",
    "workspace": "workspace_proof_flag",
}

THESIS_AMENITY_SUBJECTS = {
    "parking": "parking_proof_flag",
    "pool_or_spa": "pool_or_spa_proof_flag",
    "view": "view_proof_flag",
    "family": "family_proof_flag",
    "pet": "pet_proof_flag",
    "self_checkin": "self_checkin_proof_flag",
    "laundry": "laundry_proof_flag",
    "air_conditioning": "air_conditioning_proof_flag",
}

DESIGN_GAP_PATTERNS = {
    "dated_finish": r"\b(dated|old furniture|worn|tired|peeling|stained)\b",
    "dark_photo": r"\b(dark photo|dark photos|photos? look dark|dim|poor lighting|shadowy)\b",
    "clutter": r"\b(clutter|messy|untidy|too much furniture)\b",
    "small_or_cramped": r"\b(small|cramped|tight space|narrow)\b",
    "maintenance_visible": r"\b(broken|damaged|cracked|mould|mold|rust)\b",
}


def unique(values):
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _label_from_photo_item(item):
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        parts = []
        for key in ("subject", "caption", "alt", "aria_label", "label", "room", "title", "text"):
            value = item.get(key)
            if value:
                parts.append(str(value))
        return " ".join(parts)
    return str(item)


def infer_subject(text):
    haystack = str(text or "").lower()
    for subject, pattern in SUBJECT_PATTERNS:
        if re.search(pattern, haystack, re.I):
            return subject
    return None


def infer_subjects_from_text(text, limit=None):
    subjects = []
    haystack = str(text or "")
    for subject, pattern in SUBJECT_PATTERNS:
        if re.search(pattern, haystack, re.I):
            subjects.append(subject)
    subjects = unique(subjects)
    return subjects[:limit] if limit else subjects


def photo_subjects(photo_items, fallback_text="", first_photo_limit=5):
    labels = [_label_from_photo_item(item) for item in (photo_items or [])]
    subjects = []
    for label in labels[:first_photo_limit]:
        subjects.append(infer_subject(label) or "unknown")
    if not subjects and fallback_text:
        subjects = infer_subjects_from_text(fallback_text, limit=first_photo_limit)
    return subjects[:first_photo_limit]


def visible_amenity_claims(text):
    return unique(
        subject
        for subject, pattern in [*CORE_ROOM_SUBJECTS.items(), *THESIS_AMENITY_SUBJECTS.items()]
        if re.search(dict(SUBJECT_PATTERNS).get(subject, r"$^"), text or "", re.I)
    )


def design_gap_flags(text):
    return [
        flag
        for flag, pattern in DESIGN_GAP_PATTERNS.items()
        if re.search(pattern, text or "", re.I)
    ]


def normalize_photo_product_evidence(
    raw_listing_text="",
    raw_photo_data=None,
    hero_text=None,
    first_photo_limit=5,
):
    """Return normalized visual-product fields for listing and comp workflows."""

    listing_text = str(raw_listing_text or "")
    photo_text = " ".join(_label_from_photo_item(item) for item in (raw_photo_data or []))
    hero_label = _label_from_photo_item(hero_text)
    combined_text = " ".join(value for value in (hero_label, photo_text, listing_text) if value)
    has_photo_labels = bool((raw_photo_data or []) or hero_text)
    subjects = photo_subjects(raw_photo_data, fallback_text=combined_text, first_photo_limit=first_photo_limit)
    hero_subject = infer_subject(hero_label) or (subjects[0] if subjects else infer_subject(combined_text))

    photo_evidence_text = " ".join(value for value in (hero_label, photo_text) if value)
    proof_text = photo_evidence_text if has_photo_labels else combined_text
    all_subjects = unique(subjects + infer_subjects_from_text(proof_text))
    claims_visible = visible_amenity_claims(combined_text)
    claims_proven = [claim for claim in claims_visible if claim in all_subjects]

    evidence = {
        "hero_photo_subject": hero_subject,
        "hero_photo_subject_tag": hero_subject,
        "first_five_photo_subjects": subjects,
        "amenity_claims_visible": claims_visible,
        "amenity_claims_proven_in_photos": claims_proven,
        "design_gap_flags": design_gap_flags(combined_text),
        "photo_product_evidence_source": "visible_text_and_image_labels",
    }
    for subject, field in CORE_ROOM_SUBJECTS.items():
        evidence[field] = subject in all_subjects
    for subject, field in THESIS_AMENITY_SUBJECTS.items():
        evidence[field] = subject in all_subjects

    missing = []
    for subject, field in {**CORE_ROOM_SUBJECTS, **THESIS_AMENITY_SUBJECTS}.items():
        if subject in claims_visible and not evidence[field]:
            missing.append(subject)
    evidence["missing_photo_proof"] = unique(missing)

    proof_fields = list(CORE_ROOM_SUBJECTS.values()) + list(THESIS_AMENITY_SUBJECTS.values())
    proven_count = sum(1 for field in proof_fields if evidence[field])
    penalty = min(len(evidence["design_gap_flags"]) * 0.08, 0.32)
    evidence["photo_product_score"] = round(max(0.0, min(1.0, proven_count / len(proof_fields) - penalty)), 2)
    return evidence
