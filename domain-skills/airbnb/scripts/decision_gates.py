"""Pure Airbnb host-intelligence decision gates.

These helpers evaluate already-collected rows. They do not browse, call Airbnb,
read private artifacts, or depend on browser state.
"""

from __future__ import annotations

from statistics import median


ALLOWED_DECISIONS = {
    "pursue",
    "watch",
    "reject",
    "needs_more_data",
    "fix",
    "monitor",
    "no_action",
}

RESEARCH_MODES = {"opportunity_discovery", "property_validation", "repositioning"}
SEASONS_REQUIRED_FOR_SURVIVAL = {"peak", "shoulder", "slow"}
CHANNELS = {
    "airbnb",
    "vrbo",
    "booking_com",
    "google_hotels",
    "marriott_homes_villas",
    "direct",
    "monthly_midterm",
}


def present(value):
    return value not in (None, "", [], {}, ())


def as_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def as_number(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "pass", "passed"}


def falsy(value):
    return value is False or str(value).strip().lower() in {"0", "false", "no", "off", "disabled"}


def unique(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _most_common(items):
    counts = {}
    for item in items:
        if not item:
            continue
        counts[item] = counts.get(item, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def first_number(row, *fields, default=0):
    for field in fields:
        value = as_number((row or {}).get(field))
        if value is not None:
            return value
    return default


def decision_record(
    *,
    decision,
    confidence="low",
    evidence_refs=None,
    missing_required_evidence=None,
    do_not_use_reason=None,
    recommended_next_action=None,
    **extra,
):
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Unsupported decision: {decision}")
    return {
        "decision": decision,
        "confidence": confidence,
        "evidence_refs": as_list(evidence_refs),
        "missing_required_evidence": as_list(missing_required_evidence),
        "do_not_use_reason": do_not_use_reason,
        "recommended_next_action": recommended_next_action,
        **extra,
    }


def missing_fields(row, fields):
    return [field for field in fields if not present((row or {}).get(field))]


def grade_listing_maturity(row):
    reviews = int(as_number((row or {}).get("review_count"), 0) or 0)
    recent_30 = int(as_number((row or {}).get("recent_review_count_30d"), 0) or 0)
    recent_90 = int(as_number((row or {}).get("recent_review_count_90d"), 0) or 0)
    latest_review = present((row or {}).get("latest_review_date"))
    high_rank_signal = truthy((row or {}).get("high_rank_signal")) or truthy((row or {}).get("scarce_availability_signal"))
    explicit_new = truthy((row or {}).get("new_listing_flag"))
    stale = truthy((row or {}).get("stale_listing_flag"))
    evidence_refs = as_list((row or {}).get("evidence_refs"))

    if explicit_new or reviews < 3 or high_rank_signal:
        grade = "boosted_or_unproven"
        use = "inspiration"
        decision = "watch"
        reason = "new, low-review, or boost-risk comp cannot support base-case underwriting"
    elif stale or (reviews > 0 and not latest_review and recent_90 == 0):
        grade = "stale"
        use = "exclude"
        decision = "reject"
        reason = "stale or unverified review recency"
    elif reviews >= 10 and (recent_90 > 0 or latest_review):
        grade = "mature"
        use = "base_case"
        decision = "no_action"
        reason = None
    elif reviews >= 3 and (recent_90 > 0 or recent_30 > 0 or latest_review):
        grade = "promising"
        use = "sensitivity"
        decision = "monitor"
        reason = "promising comp is not mature enough for base-case underwriting"
    else:
        grade = "unknown"
        use = "exclude"
        decision = "needs_more_data"
        reason = "review maturity evidence is missing"

    return decision_record(
        decision=decision,
        confidence="medium" if evidence_refs else "low",
        evidence_refs=evidence_refs,
        do_not_use_reason=reason,
        recommended_next_action="collect recent review and future availability evidence" if decision != "no_action" else "allow for base-case comp use",
        maturity_grade=grade,
        underwriting_use=use,
        can_use_for_underwriting_flag=use == "base_case",
        new_listing_flag=explicit_new or reviews < 3,
        possible_airbnb_boost_flag=(explicit_new or reviews < 3) and high_rank_signal,
    )


def grade_public_comp(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    critical_flags = [
        "same_map_boundary_flag",
        "same_room_type_flag",
        "same_property_class_flag",
        "same_bedroom_band_flag",
        "same_target_guest_count_flag",
        "same_stay_length_flag",
        "same_date_or_season_flag",
        "same_core_amenity_filters_flag",
    ]
    missing = [flag for flag in critical_flags if flag not in row]
    failed = [flag for flag in critical_flags if flag in row and not truthy(row.get(flag))]
    optional_failed = [
        flag
        for flag in ("same_bathroom_band_flag", "same_bed_sleep_capacity_band_flag", "same_visible_price_context_flag", "same_channel_flag")
        if flag in row and not truthy(row.get(flag))
    ]
    reproducible = str(row.get("can_host_reproduce") or "unknown").lower()
    maturity = str(row.get("maturity_grade") or "").lower()

    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="comp cannot be graded until required similarity flags are present",
            recommended_next_action="collect missing comp similarity evidence",
            comp_grade="reject",
            evidence_use="exclude",
        )
    if failed:
        return decision_record(
            decision="reject",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="critical comp similarity flags failed",
            recommended_next_action="exclude from underwriting and collect closer comps",
            comp_grade="reject",
            evidence_use="exclude",
            failed_similarity_flags=failed,
        )
    if reproducible in {"no", "false"} or truthy(row.get("unreproducible_feature_flag")):
        return decision_record(
            decision="watch",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="winning variable is not reproducible by the candidate",
            recommended_next_action="keep as inspiration only and find equal-or-worse reproducible comps",
            comp_grade="C",
            evidence_use="inspiration",
        )
    if maturity in {"boosted_or_unproven", "stale", "unknown"}:
        evidence_use = "inspiration" if maturity == "boosted_or_unproven" else "exclude"
        return decision_record(
            decision="watch" if maturity == "boosted_or_unproven" else "reject",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason=f"listing maturity is {maturity}",
            recommended_next_action="corroborate with mature comps before underwriting",
            comp_grade="C" if maturity == "boosted_or_unproven" else "reject",
            evidence_use=evidence_use,
        )
    if optional_failed or reproducible in {"partial", "unknown"} or maturity == "promising":
        return decision_record(
            decision="monitor",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="one material difference requires sensitivity treatment",
            recommended_next_action="use only in sensitivity range",
            comp_grade="B",
            evidence_use="sensitivity",
            failed_similarity_flags=optional_failed,
        )
    return decision_record(
        decision="no_action",
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action="allow as A comp for base-case underwriting",
        comp_grade="A",
        evidence_use="underwriting",
    )


def evaluate_market_research_pack(row):
    row = row or {}
    mode = row.get("research_mode")
    missing = []
    evidence_refs = as_list(row.get("evidence_refs"))
    if mode not in RESEARCH_MODES:
        missing.append("research_mode")
    base_required = [
        "strict_comp_selection",
        "counterexample_matrix",
        "listing_maturity_filter",
        "slow_season_survival_model",
    ]
    missing.extend(missing_fields(row, base_required))
    if mode == "property_validation":
        if not present(row.get("target_address_or_building")):
            missing.append("target_address_or_building")
        if not present(row.get("map_boundary_receipt")):
            missing.append("map_boundary_receipt")
        if not present(row.get("selected_filter_chips")):
            missing.append("selected_filter_chips")
        if not present(row.get("map_friction_assessment")):
            missing.append("map_friction_assessment")
        if not (present(row.get("same_building_or_same_block_comps")) or present(row.get("equal_or_worse_profitable_comps"))):
            missing.append("same_building_or_same_block_comps_or_equal_or_worse_profitable_comps")
    elif mode == "opportunity_discovery":
        missing.extend(missing_fields(row, ["winning_product_patterns", "repeated_winner_examples", "reproducibility_assessment"]))
    elif mode == "repositioning":
        missing.extend(missing_fields(row, ["existing_listing_ref", "current_public_search_appearance", "smallest_viable_change"]))

    failed_gates = [gate for gate in base_required if str(row.get(gate)).lower() in {"fail", "failed", "reject", "contradicted"}]
    non_passing_gates = []
    for gate in base_required:
        value = str(row.get(gate)).lower()
        allowed = {"pass", "passed", "true", "supported"}
        if gate == "counterexample_matrix":
            allowed = {"supported", "pass", "passed", "true"}
        if value not in allowed:
            non_passing_gates.append(gate)
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="required market research evidence is incomplete",
            recommended_next_action="collect missing evidence before underwriting",
            market_research_decision="needs_more_data",
        )
    if failed_gates:
        return decision_record(
            decision="reject",
            confidence="high" if evidence_refs else "medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="one or more required market research gates failed",
            recommended_next_action="reject candidate or change the product/search thesis",
            market_research_decision="reject",
            failed_gates=failed_gates,
        )
    if non_passing_gates:
        return decision_record(
            decision="watch",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="one or more required market research gates has not passed",
            recommended_next_action="resolve non-passing gates before pursue",
            market_research_decision="watch",
            non_passing_gates=non_passing_gates,
        )
    if str(row.get("counterexample_matrix")).lower() == "inconclusive":
        return decision_record(
            decision="watch",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="counterexamples are inconclusive",
            recommended_next_action="collect stronger counterexamples before pursue",
            market_research_decision="watch",
        )
    return decision_record(
        decision="pursue",
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action="proceed to underwriting action log and review window",
        market_research_decision="pursue",
    )


def evaluate_slow_season_survival(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    season_rows = as_list(row.get("season_rows"))
    seasons = {str(item.get("season_segment")) for item in season_rows if isinstance(item, dict)}
    missing = []
    if not SEASONS_REQUIRED_FOR_SURVIVAL <= seasons:
        missing.append("peak_shoulder_and_slow_season_rows")
    for field in ("candidate_cost_floor", "required_monthly_net"):
        if not present(row.get(field)):
            missing.append(field)
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="slow-season survival inputs are incomplete",
            recommended_next_action="collect peak, shoulder, slow, cost-floor, and required-net inputs",
            survival_decision="needs_more_data",
        )

    required_monthly_net = as_number(row.get("required_monthly_net"), 0) or 0
    slow_rows = [item for item in season_rows if item.get("season_segment") == "slow"]
    slow_low_case = min(first_number(item, "net_after_tactics", "slow_season_low_case_net") for item in slow_rows)
    peak_rows = [item for item in season_rows if item.get("season_segment") == "peak"]
    peak_low_case = max([first_number(item, "net_after_tactics", "slow_season_low_case_net") for item in peak_rows] or [0])
    break_even_occupancy = as_number(row.get("break_even_occupancy"))
    slow_occupancy_floor = min([first_number(item, "occupancy_floor", "slow_season_occupancy_floor") for item in slow_rows] or [0])
    discount_needed = max(0, required_monthly_net - slow_low_case)
    fallback_needed = slow_low_case < required_monthly_net

    if slow_low_case < required_monthly_net and peak_low_case >= required_monthly_net:
        decision = "reject" if not truthy(row.get("monthly_or_14_day_fallback_available")) else "watch"
        reason = "deal works in peak season but fails ordinary slow-season floor"
    elif break_even_occupancy is not None and slow_occupancy_floor and slow_occupancy_floor < break_even_occupancy:
        decision = "watch"
        reason = "slow-season occupancy floor is below break-even"
    else:
        decision = "no_action"
        reason = None

    return decision_record(
        decision=decision,
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        do_not_use_reason=reason,
        recommended_next_action="reject or redesign slow-season strategy" if decision == "reject" else "use slow-season guardrails in underwriting",
        survival_decision="pass" if decision == "no_action" else decision,
        slow_season_adr_floor=min([first_number(item, "adr_floor", "slow_season_adr_floor") for item in slow_rows] or [0]),
        slow_season_occupancy_floor=slow_occupancy_floor,
        break_even_occupancy=break_even_occupancy,
        discount_needed=discount_needed,
        monthly_or_14_day_fallback_needed=fallback_needed,
    )


def diagnose_listing_conversion(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, ["listing_id"])
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="listing conversion diagnosis requires a listing_id",
            recommended_next_action="collect own public listing and search appearance",
            conversion_issue_type="unknown",
        )

    rank = as_number(row.get("search_rank"))
    impressions = as_number(row.get("impressions"))
    search_to_listing = as_number(row.get("search_to_listing_rate"))
    listing_to_booking = as_number(row.get("listing_to_booking_rate"))
    comp_price_index = as_number(row.get("comp_price_index"))
    review_count = as_number(row.get("review_count"), 0) or 0
    photo_count = as_number(row.get("photo_count"), 0) or 0
    missing_amenities = as_list(row.get("missing_amenity_filters"))
    hero_subject = row.get("hero_photo_subject")
    target_guest_segment = row.get("target_guest_segment")
    actual_guest_segment = row.get("actual_guest_segment")

    if rank is None and (impressions is None or impressions <= 0):
        issue = "visibility_problem"
        fixes = ["improve search eligibility and comp filter fit", "check availability and minimum-stay rules", "compare logged-out rank"]
    elif search_to_listing is not None and search_to_listing < as_number(row.get("search_to_listing_benchmark"), 0.02):
        issue = "search_card_click_problem"
        fixes = ["change hero photo", "adjust title/search-card promise", "surface strongest differentiator"]
    elif listing_to_booking is not None and listing_to_booking < as_number(row.get("listing_to_booking_benchmark"), 0.01):
        issue = "listing_page_conversion_problem"
        fixes = ["fix listing-page trust gaps", "improve photo tour and amenity proof", "review cancellation and house-rule friction"]
    elif comp_price_index is not None and comp_price_index > 1.12:
        issue = "price_friction"
        fixes = ["test price reduction within margin floor", "compare against A comps only", "separate peak from slow-season pricing"]
    elif review_count < 5:
        issue = "trust_signal_gap"
        fixes = ["prioritize review quality", "avoid using low-review comps for base case", "strengthen badges and listing clarity"]
    elif not hero_subject or photo_count < 12:
        issue = "photo_or_design_gap"
        fixes = ["change hero photo", "add room and amenity coverage", "show experience proof in photos"]
    elif missing_amenities:
        issue = "amenity_visibility_gap"
        fixes = ["update amenity completeness", "show amenity proof in photos", "rerun filtered search after update"]
    elif target_guest_segment and actual_guest_segment and target_guest_segment != actual_guest_segment:
        issue = "guest_segment_mismatch"
        fixes = ["reposition guest segment", "adjust capacity and rules", "rewrite content for target segment"]
    else:
        issue = "no_clear_issue"
        fixes = ["monitor conversion with current comp context"]

    return decision_record(
        decision="fix" if issue != "no_clear_issue" else "monitor",
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action=fixes[0],
        conversion_issue_type=issue,
        top_3_fix_candidates=fixes[:3],
    )


PHOTO_PRODUCT_GAP_ISSUES = {
    "hero_photo_gap",
    "photo_order_gap",
    "sleeping_capacity_not_proven",
    "amenity_not_visible",
    "trust_signal_gap",
    "design_gap",
    "guest_segment_mismatch",
    "price_not_content_problem",
    "no_clear_issue",
}

CONTENT_OPTIMIZATION_ISSUES = {
    "search_card_click_problem",
    "listing_page_conversion_problem",
    "photo_or_design_gap",
    "amenity_visibility_gap",
    "guest_segment_mismatch",
    "hero_photo_gap",
    "photo_order_gap",
    "sleeping_capacity_not_proven",
    "amenity_not_visible",
    "design_gap",
}

GALLERY_CRO_NON_CONTENT_ISSUES = {
    "price_not_content_problem",
    "price_friction",
    "trust_signal_gap",
    "visibility_problem",
    "no_clear_issue",
}

CONTENT_SCOPE_BY_ISSUE = {
    "search_card_click_problem": ["hero_photo_change", "title_above_fold_rewrite", "first_five_reorder"],
    "listing_page_conversion_problem": ["full_section_copy_rewrite", "first_five_reorder", "caption_or_amenity_proof_update"],
    "photo_or_design_gap": ["gallery_reshoot_or_edit", "first_five_reorder", "caption_or_amenity_proof_update"],
    "amenity_visibility_gap": ["caption_or_amenity_proof_update", "gallery_reshoot_or_edit", "full_section_copy_rewrite"],
    "guest_segment_mismatch": ["title_above_fold_rewrite", "full_section_copy_rewrite", "hero_photo_change"],
    "hero_photo_gap": ["hero_photo_change", "title_above_fold_rewrite", "first_five_reorder"],
    "photo_order_gap": ["first_five_reorder", "caption_or_amenity_proof_update"],
    "sleeping_capacity_not_proven": ["gallery_reshoot_or_edit", "full_section_copy_rewrite", "caption_or_amenity_proof_update"],
    "amenity_not_visible": ["caption_or_amenity_proof_update", "gallery_reshoot_or_edit", "full_section_copy_rewrite"],
    "design_gap": ["gallery_reshoot_or_edit", "caption_or_amenity_proof_update"],
}

PHOTO_SUBJECT_LABELS = {
    "view": "view/outlook",
    "living_area": "lounge/dining flow",
    "kitchen": "kitchen",
    "bedroom": "primary bedroom",
    "bathroom": "signature bathroom",
    "workspace": "workspace",
    "parking": "parking bay",
    "pool_or_spa": "pool/spa/sauna",
    "family": "family setup",
    "pet": "pet-friendly proof",
    "self_checkin": "self check-in",
    "laundry": "laundry",
    "exterior": "building/entry",
}

BANNED_COPY_PHRASES = {
    "nestled",
    "boasts",
    "amenities galore",
    "look no further",
    "perfectly located",
    "perfectly situated",
    "charming",
    "curated",
    "thoughtfully designed",
    "indulge",
    "elevate your stay",
    "unforgettable",
    "ideal base",
    "heart of the city",
    "oasis",
    "sanctuary",
}


def first_present(row, *fields):
    for field in fields:
        value = (row or {}).get(field)
        if present(value):
            return value
    return None


def _clean_copy_text(value):
    return " ".join(str(value or "").replace("\n", " ").split())


def _title_case_fragment(value):
    return " ".join(word.capitalize() for word in _clean_copy_text(value).replace("_", " ").split())


def _title_safe(value, max_chars=50):
    value = _clean_copy_text(value)
    if not value:
        return None
    if len(value) <= max_chars:
        return value
    words = value.split()
    shortened = ""
    for word in words:
        candidate = f"{shortened} {word}".strip()
        if len(candidate) > max_chars:
            break
        shortened = candidate
    return shortened or value[:max_chars].rstrip()


def _scalar_text(value):
    if isinstance(value, (dict, list, tuple, set)):
        return None
    return _clean_copy_text(value)


def _issue_from_content_row(row):
    issue = first_present(
        row,
        "source_issue_class",
        "issue_class",
        "primary_gap",
        "conversion_issue_type",
    )
    if issue:
        return str(issue).strip()
    for source in _source_gate_records(row):
        issue = first_present(source, "source_issue_class", "issue_class", "primary_gap", "conversion_issue_type")
        if issue:
            return str(issue).strip()
    return ""


def _source_gate_records(row):
    records = []
    for field in (
        "source_photo_product_gap_audit",
        "source_conversion_diagnosis",
        "source_decision_gate_output",
        "source_decision_record",
    ):
        value = (row or {}).get(field)
        if isinstance(value, dict):
            records.append(value)
    return records


def _source_gate_name(row, records):
    if present((row or {}).get("source_decision_gate") or (row or {}).get("decision_gate")):
        return (row or {}).get("source_decision_gate") or (row or {}).get("decision_gate")
    if isinstance((row or {}).get("source_photo_product_gap_audit"), dict):
        return "airbnb_photo_product_gap_audit"
    if isinstance((row or {}).get("source_conversion_diagnosis"), dict):
        return "airbnb_conversion_diagnosis"
    for record in records:
        if present(record.get("source_decision_gate") or record.get("decision_gate")):
            return record.get("source_decision_gate") or record.get("decision_gate")
    return "unknown"


def _first_from_row_or_sources(row, records, *fields):
    value = first_present(row, *fields)
    if present(value):
        return value
    for record in records:
        value = first_present(record, *fields)
        if present(value):
            return value
    return None


def _own_public_audit(row):
    return (row or {}).get("own_public_listing_audit") or (row or {}).get("own_public_audit") or {}


def _own_search_card(row):
    return (row or {}).get("own_search_card") or {}


def _listing_facts(row):
    return (row or {}).get("listing_facts") or {}


def _location_facts(row):
    return (row or {}).get("location_facts") or {}


def _subject_label(subject):
    key = str(subject or "").strip().lower()
    return PHOTO_SUBJECT_LABELS.get(key, _title_case_fragment(key) if key else None)


def _derive_why_book(row, own_audit=None, own_card=None):
    own_audit = own_audit or {}
    own_card = own_card or {}
    facts = _listing_facts(row)
    value = first_present(
        row,
        "why_book",
        "primary_usp",
        "title_promise",
        "strongest_differentiator",
    ) or first_present(facts, "why_book", "primary_usp", "view_orientation", "exterior_usp")
    if value:
        return _clean_copy_text(value)
    hero = own_card.get("hero_photo_subject_tag") or own_audit.get("hero_photo_subject") or row.get("hero_photo_subject")
    return _subject_label(hero)


def _current_title(row, own_audit=None, own_card=None):
    own_audit = own_audit or {}
    own_card = own_card or {}
    return _clean_copy_text(
        first_present(row, "current_title_text", "title_text")
        or own_audit.get("title_text")
        or own_card.get("visible_title_short")
    )


def _compose_title(row, why_book, *, challenger=False):
    supplied = row.get("recommended_challenger_title" if challenger else "recommended_primary_title")
    if supplied:
        return _title_safe(supplied)
    if not why_book:
        return None
    facts = _listing_facts(row)
    location = _scalar_text(first_present(row, "suburb_or_area", "market") or first_present(facts, "suburb_or_area", "building_name"))
    secondary = None
    for value in (
        row.get("secondary_usp"),
        facts.get("view_orientation"),
        facts.get("exterior_usp"),
        facts.get("architectural_style"),
        facts.get("workspace"),
        facts.get("balcony_count"),
    ):
        secondary = _scalar_text(value)
        if secondary:
            break
    primary = _title_case_fragment(why_book)
    if challenger and secondary:
        candidate = f"{_title_case_fragment(str(secondary))} | {primary}"
    elif location:
        candidate = f"{_title_case_fragment(location)} | {primary}"
    elif secondary:
        candidate = f"{primary} + {_title_case_fragment(str(secondary))}"
    else:
        candidate = primary
    return _title_safe(candidate)


def _format_capacity(facts):
    guests = as_number(facts.get("max_guests"))
    bedrooms = as_number(facts.get("bedrooms"))
    beds = as_number(facts.get("beds"))
    parts = []
    if guests:
        parts.append(f"sleeps {int(guests)}")
    if bedrooms:
        parts.append(f"{int(bedrooms)} bedroom{'s' if int(bedrooms) != 1 else ''}")
    if beds:
        parts.append(f"{int(beds)} bed{'s' if int(beds) != 1 else ''}")
    return ", ".join(parts)


def _format_verified_features(row, facts):
    features = []
    for field, label in [
        ("parking_details", "parking"),
        ("parking", "parking"),
        ("ev", "EV"),
        ("workspace", "workspace"),
        ("wifi_speed", "fast Wi-Fi"),
        ("laundry", "laundry"),
        ("balcony_count", "balcony"),
        ("outdoor_alfresco", "alfresco"),
        ("view_orientation", _scalar_text(facts.get("view_orientation"))),
        ("floor_level", f"Level {facts.get('floor_level')}" if present(facts.get("floor_level")) else None),
    ]:
        if present(facts.get(field)) and label:
            features.append(label)
    location = _location_facts(row)
    anchors = as_list(location.get("walkable_anchors") or location.get("key_anchors"))
    if anchors:
        features.append(str(anchors[0]))
    return unique(features)


def _limit_sentences(text, max_chars=280):
    text = _clean_copy_text(text)
    if len(text) <= max_chars:
        return text
    shortened = ""
    for word in text.split():
        candidate = f"{shortened} {word}".strip()
        if len(candidate) > max_chars - 1:
            break
        shortened = candidate
    return f"{shortened.rstrip('.')}." if shortened else text[:max_chars].rstrip()


def _compose_above_fold(row, why_book, *, challenger=False):
    supplied = row.get("above_fold_challenger" if challenger else "above_fold_primary")
    if supplied:
        return _limit_sentences(supplied)
    if not why_book:
        return None
    facts = _listing_facts(row)
    capacity = _format_capacity(facts)
    features = _format_verified_features(row, facts)
    proof = features[0] if features else None
    micro = features[1] if len(features) > 1 else None
    if challenger and micro:
        first = f"{_clean_copy_text(micro).capitalize()} supports a {_clean_copy_text(why_book)} stay"
    elif proof:
        first = f"{_clean_copy_text(why_book).capitalize()} with {proof}"
    else:
        first = _clean_copy_text(why_book).capitalize()
    second_parts = []
    if capacity:
        second_parts.append(capacity.capitalize())
    if micro and not challenger:
        second_parts.append(f"with {micro}")
    elif proof and challenger:
        second_parts.append(f"with {proof}")
    second = ", ".join(second_parts)
    if second:
        return _limit_sentences(f"{first}. {second}.")
    return _limit_sentences(f"{first}.")


def _first_five_order(row, issue, why_book, own_audit=None):
    own_audit = own_audit or {}
    current_subjects = as_list(own_audit.get("first_five_photo_subjects") or row.get("first_five_photo_subjects"))
    order = [
        {
            "rank": 1,
            "target": "primary why-book hero",
            "current_subject": _subject_label(current_subjects[0]) if len(current_subjects) > 0 else None,
            "rationale": f"lead with {why_book or 'the strongest proven differentiator'} and keep it crop-safe",
        },
        {
            "rank": 2,
            "target": "alternate proof of the same promise",
            "current_subject": _subject_label(current_subjects[1]) if len(current_subjects) > 1 else None,
            "rationale": "build trust without repeating the same angle",
        },
        {
            "rank": 3,
            "target": "lounge/dining space and flow",
            "current_subject": _subject_label(current_subjects[2]) if len(current_subjects) > 2 else None,
            "rationale": "make layout, light, and seating capacity readable",
        },
        {
            "rank": 4,
            "target": "kitchen, outdoor/alfresco, workspace, or family proof",
            "current_subject": _subject_label(current_subjects[3]) if len(current_subjects) > 3 else None,
            "rationale": "surface the strongest segment-specific booking driver",
        },
        {
            "rank": 5,
            "target": "primary bedroom, signature bathroom, or scarce parking",
            "current_subject": _subject_label(current_subjects[4]) if len(current_subjects) > 4 else None,
            "rationale": "prove comfort, sleep quality, or a scarce amenity early",
        },
    ]
    if issue in {"sleeping_capacity_not_proven"}:
        order[3]["target"] = "bedroom and sleeping layout proof"
        order[4]["target"] = "secondary sleeping proof or sofa-bed proof"
    elif issue in {"amenity_not_visible", "amenity_visibility_gap"}:
        order[3]["target"] = "missing thesis amenity proof"
    elif issue in {"guest_segment_mismatch"}:
        order[3]["target"] = "target-segment proof"
    return order


def _missing_shots(row, issue, own_audit=None):
    own_audit = own_audit or {}
    missing = []
    missing_proof = unique(as_list(row.get("missing_photo_proof")) + as_list(own_audit.get("missing_photo_proof")))
    missing_amenities = unique(as_list(row.get("missing_visible_amenities")) + as_list(own_audit.get("missing_visible_amenities")) + as_list(row.get("missing_amenity_filters")))
    wanted = set(str(item).strip().lower() for item in missing_proof + missing_amenities if item)
    if "parking" in wanted:
        missing.append("Parking bay: context wide plus bay number/signage and clearance proof")
    if "view" in wanted:
        missing.append("View/balcony: inside-to-out and outside-to-in balcony flow pair")
    if "workspace" in wanted:
        missing.append("Workspace: desk, chair, power point, and outlook/Wi-Fi proof")
    if "pool_or_spa" in wanted:
        missing.append("Pool/spa/sauna/gym: people-free amenity proof with building-managed disclaimer in copy")
    if "family" in wanted:
        missing.append("Family setup: cot/high chair/kids room/bunk proof where offered")
    if "pet" in wanted:
        missing.append("Pet proof: practical pet-friendly feature only if pets are genuinely allowed")
    if "self_checkin" in wanted:
        missing.append("Arrival proof: entry, lift/lobby, door hardware, and self-check-in path")
    if "laundry" in wanted:
        missing.append("Laundry: washer/dryer and long-stay utility proof")
    if any(item in wanted for item in {"bedroom", "sleep", "bed"}):
        missing.append("Sleeping layout: each bedroom wide, bed size proof, and sofa-bed proof if used for capacity")
    if issue in {"photo_order_gap", "hero_photo_gap"} and not missing:
        missing.append("Exact photo IDs for hero and first-five reorder")
    if issue == "design_gap":
        missing.append("Fresh room wides: lounge, kitchen, primary bedroom, bathroom, and main differentiator")
    return unique(as_list(row.get("missing_shots")) + missing)


def _reshoot_shotlist(missing_shots):
    shotlist = []
    for item in missing_shots:
        lowered = item.lower()
        if "parking" in lowered:
            shotlist.append({"area": "parking", "shots": ["context wide", "bay number/signage close crop"], "technique": "straight, bright, no identifiable vehicles if avoidable"})
        elif "balcony" in lowered or "view" in lowered:
            shotlist.append({"area": "balcony/view", "shots": ["inside-to-out flow", "outside-to-in flow", "view wide"], "technique": "daylight, horizon level, keep view central in square crop"})
        elif "workspace" in lowered:
            shotlist.append({"area": "workspace", "shots": ["desk wide", "power/seat detail"], "technique": "neutral white balance, readable desk and chair"})
        elif "sleeping" in lowered or "bedroom" in lowered:
            shotlist.append({"area": "sleeping layout", "shots": ["bedroom entry wide", "alternate wide", "bed size/storage detail"], "technique": "1.2 m camera height, straight verticals"})
        elif "pool" in lowered or "spa" in lowered or "sauna" in lowered or "gym" in lowered:
            shotlist.append({"area": "building amenities", "shots": ["people-free amenity wide", "access/context shot"], "technique": "manage reflections, keep facility truthful"})
        elif "arrival" in lowered or "entry" in lowered:
            shotlist.append({"area": "arrival", "shots": ["building entry", "lift/lobby", "door/check-in hardware"], "technique": "clear path of travel, no private codes visible"})
    return shotlist


def _edit_briefs(issue, why_book):
    briefs = []
    if issue in {"hero_photo_gap", "search_card_click_problem"}:
        briefs.append("Hero polish: brighten evenly, straighten verticals, neutral white balance, and export 1:1, 16:9, 3:2, and 4:5 crops preserving the primary USP.")
    if issue in {"photo_order_gap", "photo_or_design_gap", "design_gap", "listing_page_conversion_problem"}:
        briefs.append("Gallery consistency: normalize white balance and exposure across room wides; avoid HDR halos and over-processed colours.")
    if issue in {"amenity_not_visible", "amenity_visibility_gap"}:
        briefs.append("Amenity proof: improve legibility of the real amenity without adding features; captions should state any limitations or building-managed disclaimer.")
    if why_book and "view" in why_book.lower():
        briefs.append("View clarity: reduce glare and preserve skyline/sea contrast; keep horizon level and the view central in crop variants.")
    return briefs


def _gallery_photo_identifier(photo, fallback):
    for field in ("photo_id", "image_id", "id", "filename", "url"):
        if present((photo or {}).get(field)):
            return str(photo.get(field))
    subject = _gallery_photo_subject(photo)
    return f"subject:{subject or 'photo'}:{fallback}"


def _gallery_has_exact_identifier(photo):
    return any(present((photo or {}).get(field)) for field in ("photo_id", "image_id", "id", "filename", "url"))


def _gallery_photo_subject(photo):
    photo = photo or {}
    raw = first_present(photo, "subject", "room", "label", "caption", "alt", "title", "text")
    value = str(raw or "").strip().lower().replace("-", " ")
    if not value:
        return "unknown"
    keyword_map = {
        "parking": ("parking", "garage", "car park", "ev"),
        "pool_or_spa": ("pool", "spa", "hot tub", "jacuzzi", "sauna"),
        "view": ("view", "skyline", "balcony", "alfresco", "terrace", "ocean", "harbour", "river"),
        "workspace": ("workspace", "desk", "office", "monitor", "work"),
        "bedroom": ("bedroom", "bed", "king", "queen", "sleep"),
        "bathroom": ("bathroom", "bath", "shower", "ensuite"),
        "kitchen": ("kitchen", "oven", "cooktop", "dishwasher"),
        "living_area": ("living", "lounge", "sofa", "dining"),
        "family": ("family", "kids", "bunk", "cot", "high chair"),
        "laundry": ("laundry", "washer", "dryer"),
        "exterior": ("exterior", "facade", "entrance", "lobby", "building"),
    }
    for subject, terms in keyword_map.items():
        if any(term in value for term in terms):
            return subject
    return value.replace(" ", "_")


def _gallery_subject_from_text(value):
    return _gallery_photo_subject({"subject": value}) if present(value) else None


def _gallery_photo_scorecard(photo, position):
    supplied = as_number(first_present(photo, "photo_score", "score"), None)
    demand = as_number(first_present(photo, "demand_driver_score", "demand_driver"), supplied or 0) or 0
    clarity = as_number(first_present(photo, "clarity_diagnosticity_score", "clarity_score"), supplied or 0) or 0
    crop = as_number(first_present(photo, "crop_safety_score", "crop_safety"), supplied or 0) or 0
    penalty = as_number(photo.get("redundancy_penalty"), 0) or 0
    score = max(0, min(100, (0.50 * demand) + (0.30 * clarity) + (0.20 * crop) - penalty))
    return {
        "photo_id_or_subject": _gallery_photo_identifier(photo, position),
        "has_exact_photo_id": _gallery_has_exact_identifier(photo),
        "subject": _gallery_photo_subject(photo),
        "score": round(score, 1),
        "demand_driver_score": round(demand, 1),
        "clarity_diagnosticity_score": round(clarity, 1),
        "crop_safety_score": round(crop, 1),
        "crop_notes": photo.get("crop_notes"),
        "eligible_for_hero": demand >= 80 and clarity >= 75 and crop >= 80,
    }


def _gallery_comp_subjects(row):
    values = []
    patterns = row.get("a_comp_visual_patterns") or row.get("comp_visual_patterns") or {}
    if isinstance(patterns, dict):
        values.extend(as_list(patterns.get("hero_subject_mode")))
        values.extend(as_list(patterns.get("first_five_subjects")))
        values.extend(as_list(patterns.get("repeated_winning_subjects")))
    elif isinstance(patterns, list):
        for item in patterns:
            if isinstance(item, dict):
                values.append(first_present(item, "hero_subject", "subject", "hero_photo_subject_tag"))
                values.extend(as_list(item.get("first_five_subjects")))
            else:
                values.append(item)
    for comp in as_list(row.get("a_comp_cards")) + as_list(row.get("a_comp_listing_snapshots")):
        if isinstance(comp, dict):
            values.append(first_present(comp, "hero_photo_subject_tag", "hero_photo_subject"))
            values.extend(as_list(comp.get("first_five_photo_subjects")))
    return unique([_gallery_subject_from_text(value) for value in values if present(value)])


def _gallery_priority_subjects(row, scorecards):
    available = {card["subject"] for card in scorecards}
    priorities = []
    why_subject = _gallery_subject_from_text(row.get("why_book") or row.get("title_or_search_card_promise"))
    if why_subject:
        priorities.append(why_subject)
    priorities.extend(_gallery_comp_subjects(row))
    segment = str(row.get("target_guest_segment") or row.get("guest_segment") or "").lower()
    season = str(row.get("seasonality") or "").lower()
    if any(term in segment for term in ("family", "group", "kids")):
        priorities.extend(["family", "living_area", "bedroom", "kitchen"])
    if any(term in segment for term in ("work", "business", "executive", "remote")):
        priorities.extend(["workspace", "living_area", "bedroom"])
    if "summer" in season:
        priorities.extend(["pool_or_spa", "view"])
    if "winter" in season:
        priorities.extend(["living_area", "bathroom"])
    priorities.extend(["living_area", "kitchen", "bedroom", "bathroom", "workspace", "parking", "view", "pool_or_spa", "laundry", "exterior"])
    return [subject for subject in unique(priorities) if subject in available]


def _gallery_pick_first_five(scorecards, row):
    ranked = sorted(scorecards, key=lambda card: (-card["score"], card["photo_id_or_subject"]))
    selected = []
    used = set()
    for subject in _gallery_priority_subjects(row, ranked):
        for card in ranked:
            if card["subject"] == subject and card["photo_id_or_subject"] not in used:
                selected.append(card)
                used.add(card["photo_id_or_subject"])
                break
        if len(selected) == 5:
            break
    for card in ranked:
        if len(selected) == 5:
            break
        if card["photo_id_or_subject"] not in used:
            selected.append(card)
            used.add(card["photo_id_or_subject"])
    hero = selected[0] if selected else None
    alternates = [
        card for card in ranked
        if hero and card["photo_id_or_subject"] != hero["photo_id_or_subject"] and card["eligible_for_hero"]
    ][:2]
    return hero, alternates, selected


def _gallery_room_coverage(scorecards, own_audit):
    subjects = {card["subject"] for card in scorecards}
    plan = []
    for subject, flag_field in [
        ("bedroom", "bedroom_proof_flag"),
        ("bathroom", "bathroom_proof_flag"),
        ("kitchen", "kitchen_proof_flag"),
        ("living_area", "living_area_proof_flag"),
    ]:
        covered = subject in subjects or truthy((own_audit or {}).get(flag_field))
        plan.append({
            "subject": subject,
            "status": "covered" if covered else "missing",
            "recommended_action": "use strongest existing proof photo" if covered else f"shoot clear {_subject_label(subject)} proof",
        })
    return plan


def _gallery_amenity_plan(scorecards, own_audit, row):
    subjects = {card["subject"] for card in scorecards}
    claims = unique(as_list((own_audit or {}).get("amenity_claims_visible")) + as_list(row.get("amenity_claims_visible")))
    proven = set(as_list((own_audit or {}).get("amenity_claims_proven_in_photos")) + as_list(row.get("amenity_claims_proven_in_photos")))
    missing = unique(as_list((own_audit or {}).get("missing_photo_proof")) + as_list(row.get("missing_photo_proof")))
    plan = []
    for amenity in unique(claims + list(proven) + missing):
        status = "covered" if amenity in subjects or amenity in proven else "missing"
        plan.append({
            "amenity": amenity,
            "status": status,
            "recommended_action": "caption and place the proof photo in the gallery" if status == "covered" else f"capture proof shot for {_subject_label(amenity)}",
        })
    return plan


def _gallery_caption_pairings(first_five, why_book):
    pairings = []
    for index, card in enumerate(first_five, start=1):
        if index == 1:
            guidance = f"Lead with {why_book or 'the primary why-book'} in a factual caption."
        else:
            guidance = f"Prove {_subject_label(card['subject'])} without repeating the previous image."
        pairings.append({
            "position": index,
            "photo_id_or_subject": card["photo_id_or_subject"],
            "subject": card["subject"],
            "caption_guidance": guidance,
        })
    return pairings


def build_gallery_cro_execution_board(row):
    """Build a gallery-specific execution board from exact photo candidates."""
    row = row or {}
    own_audit = _own_public_audit(row)
    source_gap = row.get("source_photo_product_gap_audit") or {}
    issue = _issue_from_content_row(row) or str(source_gap.get("issue_class") or source_gap.get("primary_gap") or "").strip()
    evidence_refs = unique(as_list(row.get("evidence_refs")) + as_list(own_audit.get("evidence_refs")))
    force = truthy(row.get("explicit_gallery_request")) or truthy(row.get("user_requested_gallery_work"))

    if issue in GALLERY_CRO_NON_CONTENT_ISSUES and not force:
        return decision_record(
            decision="monitor",
            confidence="medium" if evidence_refs else "low",
            evidence_refs=evidence_refs,
            do_not_use_reason=f"{issue} is not a gallery CRO trigger",
            recommended_next_action="resolve the non-gallery bottleneck before changing photos",
            source_issue_class=issue,
            board_status="not_applicable",
            action_checklist=[],
        )
    if issue and issue not in CONTENT_OPTIMIZATION_ISSUES and not force:
        return decision_record(
            decision="reject",
            confidence="medium" if evidence_refs else "low",
            evidence_refs=evidence_refs,
            do_not_use_reason=f"{issue} is not a recognized gallery CRO trigger",
            recommended_next_action="run conversion diagnosis or photo/product gap audit before changing gallery order",
            source_issue_class=issue,
            board_status="not_applicable",
            action_checklist=[],
        )

    photos = [item for item in as_list(row.get("candidate_photos") or row.get("photos")) if isinstance(item, dict)]
    scorecards = [_gallery_photo_scorecard(photo, index + 1) for index, photo in enumerate(photos)]
    hero, alternates, first_five = _gallery_pick_first_five(scorecards, row)
    current_order = as_list(row.get("current_photo_order") or own_audit.get("current_photo_order") or own_audit.get("first_five_photo_subjects"))
    why_book = _derive_why_book(row, own_audit, _own_search_card(row))
    missing = missing_fields(row, ["listing_id", "stay_length"])
    if not present(row.get("target_guest_segment") or row.get("guest_segment")):
        missing.append("target_guest_segment")
    if not issue and not force:
        missing.append("source_issue_class_or_explicit_gallery_request")
    if not evidence_refs:
        missing.append("evidence_refs")
    if not why_book:
        missing.append("why_book")
    if not present(row.get("title_or_search_card_promise") or row.get("current_title_text")):
        missing.append("title_or_search_card_promise")
    if not photos:
        missing.append("candidate_photos")
    if not current_order:
        missing.append("current_photo_order")
    if first_five and not all(card["has_exact_photo_id"] for card in first_five):
        missing.append("exact_photo_ids_for_selected_first_five")
    if hero and not hero["eligible_for_hero"]:
        missing.append("cover_safe_hero_candidate")

    room_coverage = _gallery_room_coverage(scorecards, own_audit)
    amenity_plan = _gallery_amenity_plan(scorecards, own_audit, row)
    missing_proof_shots = unique(
        [item["subject"] for item in room_coverage if item["status"] == "missing"]
        + [item["amenity"] for item in amenity_plan if item["status"] == "missing"]
    )
    expected_metric = "search_to_listing_conversion" if issue in {"hero_photo_gap", "photo_order_gap", "search_card_click_problem"} else "listing_to_booking_conversion"
    review_window_days = int(as_number(row.get("review_window_days"), 14) or 14)
    first_five_order = [
        {
            "position": index,
            "photo_id_or_subject": card["photo_id_or_subject"],
            "subject": card["subject"],
            "score": card["score"],
            "crop_safety_score": card["crop_safety_score"],
            "rationale": "cover photo proves the primary why-book" if index == 1 else f"adds {_subject_label(card['subject'])} proof",
        }
        for index, card in enumerate(first_five, start=1)
    ]
    reshoot_shotlist = [
        {
            "subject": subject,
            "shot_brief": f"Capture honest, bright {_subject_label(subject)} proof with straight verticals and readable scale.",
        }
        for subject in missing_proof_shots
    ]
    edit_briefs = [
        {
            "photo_id_or_subject": card["photo_id_or_subject"],
            "edit_brief": "Straighten verticals, neutral white balance, and export crop variants preserving the visible USP.",
        }
        for card in first_five
        if card["crop_safety_score"] < 80 or card["clarity_diagnosticity_score"] < 75
    ]
    payload = {
        "gallery_cro_execution_board_id": row.get("gallery_cro_execution_board_id"),
        "listing_id": row.get("listing_id"),
        "source_issue_class": issue or "explicit_gallery_request",
        "target_date_or_window": row.get("target_date_or_window"),
        "target_guest_segment": row.get("target_guest_segment") or row.get("guest_segment"),
        "stay_length": row.get("stay_length"),
        "seasonality": row.get("seasonality"),
        "channel_goal": row.get("channel_goal") or "airbnb",
        "why_book": why_book,
        "hero_primary_photo_id_or_subject": hero["photo_id_or_subject"] if hero else None,
        "hero_alternate_photo_ids_or_subjects": [card["photo_id_or_subject"] for card in alternates],
        "hero_crop_safety_score": hero["crop_safety_score"] if hero else None,
        "hero_score_components": hero,
        "first_five_order": first_five_order,
        "first_five_scorecard": first_five,
        "room_coverage_plan": room_coverage,
        "amenity_proof_plan": amenity_plan,
        "missing_proof_shots": missing_proof_shots,
        "reshoot_shotlist": reshoot_shotlist,
        "edit_briefs": edit_briefs,
        "caption_copy_pairings": _gallery_caption_pairings(first_five, why_book),
        "design_gap_flags": unique(as_list(own_audit.get("design_gap_flags")) + as_list(row.get("design_gap_flags"))),
        "comp_visual_patterns": _gallery_comp_subjects(row),
        "ab_test_plan": {
            "primary_hypothesis": "new hero and first-five order improves bookings per impression",
            "kpi": "bookings_per_impression",
            "fallback_kpi": expected_metric,
            "guardrails": ["listing_to_booking_conversion", "save_rate", "message_rate", "accuracy_complaints"],
            "cadence": "weekly",
            "stop_rule": "keep the variant only after two consecutive reads show at least 10% relative lift with neutral or improving guardrails",
            "review_window_days": review_window_days,
        },
        "rollback_plan": {
            "restore_photo_order": current_order,
            "restore_captions_from": row.get("current_caption_snapshot") or "prior listing snapshot",
            "rollback_criteria": row.get("rollback_criteria") or "revert if target metric or guardrails worsen after the review window",
        },
        "action_checklist": [
            "set primary hero",
            "publish first-five order",
            "apply caption pairings",
            "queue missing proof shots",
            "open A/B review window",
        ],
        "expected_metric": expected_metric,
        "review_window_days": review_window_days,
        "created_at": row.get("created_at"),
    }

    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="gallery CRO execution board requires exact photo candidates, current gallery state, title promise, why-book, and evidence refs",
            recommended_next_action="collect exact photo candidates and current gallery state before publishing a gallery change",
            board_status="needs_photo_selection",
            **payload,
        )

    return decision_record(
        decision="fix",
        confidence="high" if len(evidence_refs) >= 2 else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action="publish the Gallery CRO first-five order and open the A/B review window",
        board_status="ready_to_ship",
        **payload,
    )


def _copy_sections(row, issue, why_book):
    supplied = row.get("copy_sections")
    if supplied:
        return supplied
    facts = _listing_facts(row)
    location = _location_facts(row)
    sections = {
        "the_space": [
            f"Lead with {why_book or 'the primary proven USP'} and support it with concrete room, bed, view, level, parking, workspace, and appliance facts.",
            "Use quick-scan bullets for bedroom setup, apartment features, security/parking, and extras when those facts are provided.",
        ],
        "guest_access": [
            "State entire-home access, balcony/alfresco, parking bay, lift/level, check-in method, and building amenities only when provided.",
        ],
        "other_things_to_note": [
            "Set expectations for building-managed amenities, same-day prep, streaming limitations, noise windows, strata rules, or access quirks when provided.",
        ],
        "house_rules": [
            "Use friendly-firm bullets for guest count, quiet hours, no parties, smoking/vaping, pets, rubbish, and real host-provided fees.",
        ],
    }
    if first_present(facts, "parking_details", "parking", "ev"):
        sections["guest_access"].append("Include parking bay number and clearance when verified.")
    if first_present(location, "walkable_anchors", "key_anchors"):
        sections["the_space"].append("Use realistic metres/kilometres or walk times for guest-relevant anchors.")
    if issue == "guest_segment_mismatch":
        sections["the_space"].append("Rewrite the promise around the target guest segment rather than the current accidental audience.")
    return sections


def _content_risk_flags(row, current_title, why_book, primary_title):
    risks = []
    haystack = f"{current_title} {primary_title or ''}".lower()
    for phrase in sorted(BANNED_COPY_PHRASES):
        if phrase in haystack:
            risks.append(f"banned_or_weak_phrase_present:{phrase}")
    if why_book and primary_title and str(why_book).lower().split()[0] not in primary_title.lower():
        risks.append("title_may_not_lead_with_primary_usp")
    if not current_title:
        risks.append("current_title_missing")
    return unique(as_list(row.get("content_risk_flags")) + risks)


def build_listing_content_optimization_brief(row):
    """Build a structured content brief from already-collected Airbnb evidence."""
    row = row or {}
    own_audit = _own_public_audit(row)
    own_card = _own_search_card(row)
    source_records = _source_gate_records(row)
    issue = _issue_from_content_row(row)
    evidence_refs = unique(
        as_list(row.get("evidence_refs"))
        + as_list(own_audit.get("evidence_refs"))
        + as_list(own_card.get("evidence_refs"))
        + [
            ref
            for source in source_records
            for ref in as_list(source.get("evidence_refs"))
        ]
    )
    force = truthy(row.get("force_content_brief")) or truthy(row.get("user_requested_content_work"))
    missing = missing_fields(row, ["listing_id"])

    if not issue:
        missing.append("source_issue_class")
    if not evidence_refs and not force:
        missing.append("evidence_refs")

    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="content optimization brief requires a listing_id and source issue class",
            recommended_next_action="run conversion diagnosis or photo/product gap audit first",
            source_issue_class=issue or "unknown",
            optimization_scope=[],
        )

    if issue not in CONTENT_OPTIMIZATION_ISSUES and not force:
        decision = "monitor" if issue in GALLERY_CRO_NON_CONTENT_ISSUES else "reject"
        return decision_record(
            decision=decision,
            confidence="medium" if evidence_refs else "low",
            evidence_refs=evidence_refs,
            do_not_use_reason=f"{issue} is not a content-optimization trigger",
            recommended_next_action="store as decision evidence; do not create a content action unless the user explicitly asks",
            source_issue_class=issue,
            optimization_scope=[],
        )

    why_book = _derive_why_book(row, own_audit, own_card)
    current_title = _current_title(row, own_audit, own_card)
    primary_title = _compose_title(row, why_book, challenger=False)
    challenger_title = _compose_title(row, why_book, challenger=True)
    above_fold_primary = _compose_above_fold(row, why_book, challenger=False)
    above_fold_challenger = _compose_above_fold(row, why_book, challenger=True)
    missing_required_facts = unique(as_list(row.get("missing_required_facts")))

    if not why_book:
        missing_required_facts.append("primary why-book / USP")
    if "title_above_fold_rewrite" in CONTENT_SCOPE_BY_ISSUE.get(issue, []) and not current_title:
        missing_required_facts.append("current title text")
    if not primary_title and "title_above_fold_rewrite" in CONTENT_SCOPE_BY_ISSUE.get(issue, []):
        missing_required_facts.append("verified USP suitable for a <=50 character title")
    if not above_fold_primary and "title_above_fold_rewrite" in CONTENT_SCOPE_BY_ISSUE.get(issue, []):
        missing_required_facts.append("verified facts suitable for above-fold copy")
    if "full_section_copy_rewrite" in CONTENT_SCOPE_BY_ISSUE.get(issue, []) and not (_listing_facts(row) or row.get("listing_facts_ref")):
        missing_required_facts.append("listing facts for section copy")

    missing_shots = _missing_shots(row, issue, own_audit)
    expected_metric = _first_from_row_or_sources(
        row,
        source_records,
        "expected_metric",
        "target_metric",
    ) or ("search_to_listing_conversion" if issue in {"hero_photo_gap", "photo_order_gap", "search_card_click_problem"} else "listing_to_booking_conversion")
    hero_subject = (
        row.get("hero_primary_photo_id_or_subject")
        or row.get("recommended_hero_photo_id")
        or own_card.get("hero_photo_subject_tag")
        or own_audit.get("hero_photo_subject")
        or row.get("hero_photo_subject")
    )
    hero_title_alignment = "unknown"
    if why_book and hero_subject:
        hero_title_alignment = "aligned" if str(hero_subject).lower() in str(why_book).lower() or str(why_book).lower() in str(hero_subject).lower() else "review_required"
    brief_status = "needs_host_facts" if missing_required_facts else "ready_for_review"
    recommended_next_action = (
        "collect missing host facts before implementing the content brief"
        if missing_required_facts
        else "create recommendation and action log only after host accepts the content brief"
    )
    review_window_days = int(as_number(_first_from_row_or_sources(row, source_records, "review_window_days"), 14) or 14)

    return decision_record(
        decision="fix",
        confidence="high" if evidence_refs and (own_audit or own_card) else "medium" if evidence_refs else "low",
        evidence_refs=evidence_refs,
        missing_required_evidence=[],
        do_not_use_reason=None,
        recommended_next_action=recommended_next_action,
        content_optimization_brief_id=row.get("content_optimization_brief_id"),
        listing_id=row.get("listing_id"),
        brief_status=brief_status,
        source_decision_gate=_source_gate_name(row, source_records),
        source_conversion_diagnosis_id=_first_from_row_or_sources(row, source_records, "source_conversion_diagnosis_id", "conversion_diagnosis_id"),
        source_photo_product_gap_audit_id=_first_from_row_or_sources(row, source_records, "source_photo_product_gap_audit_id", "photo_product_gap_audit_id"),
        source_issue_class=issue,
        target_date_or_window=row.get("target_date_or_window"),
        target_guest_segment=row.get("target_guest_segment") or row.get("guest_segment"),
        stay_length=row.get("stay_length"),
        seasonality=row.get("seasonality"),
        why_book=why_book,
        optimization_scope=CONTENT_SCOPE_BY_ISSUE.get(issue, ["title_above_fold_rewrite", "hero_photo_change"] if force else []),
        current_title_text=current_title,
        recommended_primary_title=primary_title,
        recommended_challenger_title=challenger_title,
        above_fold_primary=above_fold_primary,
        above_fold_challenger=above_fold_challenger,
        title_ctr_score=row.get("title_ctr_score"),
        above_fold_score=row.get("above_fold_score"),
        hero_primary_photo_id_or_subject=hero_subject,
        hero_alternate_photo_ids_or_subjects=as_list(row.get("hero_alternate_photo_ids_or_subjects")),
        hero_title_alignment=hero_title_alignment,
        first_five_order=_first_five_order(row, issue, why_book, own_audit),
        gallery_sequence_notes=[
            "first five must prove different decision questions",
            "lifestyle images belong mid-gallery unless explicitly being tested",
            "floor plan belongs near the end unless layout complexity requires positions 6-8",
        ],
        caption_updates=as_list(row.get("caption_updates")),
        missing_shots=missing_shots,
        reshoot_shotlist=as_list(row.get("reshoot_shotlist")) or _reshoot_shotlist(missing_shots),
        edit_briefs=as_list(row.get("edit_briefs")) or _edit_briefs(issue, why_book),
        copy_sections=_copy_sections(row, issue, why_book),
        ab_test_plan={
            "hypothesis": f"Changing content for {issue} will improve {expected_metric}",
            "variants": [
                {"name": "Primary", "title": primary_title, "above_fold": above_fold_primary, "hero": hero_subject},
                {"name": "Challenger", "title": challenger_title, "above_fold": above_fold_challenger, "hero": None},
            ],
            "kpi": "bookings per impression when observable, otherwise search-to-listing conversion",
            "guardrails": ["save rate", "message rate", "listing-to-booking conversion", "accuracy/review complaints"],
            "cadence": "weekly",
            "stop_rules": ">=10% relative lift across 2 consecutive reads with stable guardrails",
            "sizing_note": "25k-40k impressions per arm is order-of-magnitude guidance for CTR tests",
        },
        rollback_plan={
            "preserve_before_state": ["title", "above_fold_copy", "photo_order", "captions"],
            "rollback_action": "restore prior title, copy, photo order, and captions if guardrails degrade or test loses",
        },
        missing_required_facts=unique(missing_required_facts),
        content_risk_flags=_content_risk_flags(row, current_title, why_book, primary_title),
        expected_metric=expected_metric,
        review_window_days=review_window_days,
        created_at=row.get("created_at"),
    )


def audit_photo_product_gap(row):
    """Classify photo/product gaps against A-comps before recommending price cuts."""
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, ["listing_id", "guest_segment", "stay_length"])
    own_audit = row.get("own_public_listing_audit") or {}
    own_card = row.get("own_search_card") or {}
    a_comp_cards = [item for item in as_list(row.get("a_comp_cards")) if isinstance(item, dict)]
    a_comp_listings = [item for item in as_list(row.get("a_comp_listing_snapshots")) if isinstance(item, dict)]
    conversion_metrics = row.get("own_conversion_metrics") or {}

    if not own_audit and not own_card:
        missing.append("own_public_listing_audit_or_search_card")
    if not a_comp_cards and not a_comp_listings:
        missing.append("a_comp_visual_set")
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="photo/product audit requires own guest-visible evidence and A-comp visual evidence",
            recommended_next_action="collect own public listing audit, own search card, and A-comp visual snapshots",
            primary_gap="unknown",
            issue_class="unknown",
            top_3_fix_candidates=[],
        )

    comp_price_index = as_number(row.get("comp_price_index"))
    if comp_price_index is None:
        own_price = as_number(row.get("own_total_price"))
        comp_prices = [
            as_number(item.get("visible_price_total") or item.get("visible_total_guest_price"))
            for item in a_comp_cards + a_comp_listings
        ]
        comp_prices = [price for price in comp_prices if price is not None]
        if own_price is not None and comp_prices:
            comp_price_index = own_price / median(comp_prices)

    search_to_listing = as_number(
        conversion_metrics.get("search_to_listing_rate"),
        as_number(row.get("search_to_listing_rate")),
    )
    listing_to_booking = as_number(
        conversion_metrics.get("listing_to_booking_rate"),
        as_number(row.get("listing_to_booking_rate")),
    )
    search_benchmark = as_number(row.get("search_to_listing_benchmark"), 0.02)
    booking_benchmark = as_number(row.get("listing_to_booking_benchmark"), 0.01)

    own_hero = str(own_card.get("hero_photo_subject_tag") or own_audit.get("hero_photo_subject") or row.get("hero_photo_subject") or "").strip().lower()
    comp_hero_subjects = [
        str(item.get("hero_photo_subject_tag") or item.get("hero_photo_subject") or "").strip().lower()
        for item in a_comp_cards + a_comp_listings
        if str(item.get("hero_photo_subject_tag") or item.get("hero_photo_subject") or "").strip()
    ]
    strongest_comp_subject = _most_common(comp_hero_subjects)
    missing_amenities = unique(as_list(row.get("missing_visible_amenities")) + as_list(own_audit.get("missing_visible_amenities")) + as_list(row.get("missing_amenity_filters")))
    missing_proof = unique(as_list(row.get("missing_photo_proof")) + as_list(own_audit.get("missing_photo_proof")))
    photo_count = as_number(own_audit.get("photo_count"), as_number(row.get("photo_count"), 0)) or 0
    first_five = as_list(own_audit.get("first_five_photo_subjects") or row.get("first_five_photo_subjects"))
    design_gap_flags = unique(as_list(row.get("design_gap_flags")) + as_list(own_audit.get("design_gap_flags")))
    photo_product_score = as_number(own_audit.get("photo_product_score"), as_number(row.get("photo_product_score")))
    room_proof_fields = [
        "bedroom_proof_flag",
        "bathroom_proof_flag",
        "kitchen_proof_flag",
        "living_area_proof_flag",
        "workspace_proof_flag",
    ]
    amenity_proof_fields = [
        "parking_proof_flag",
        "pool_or_spa_proof_flag",
        "view_proof_flag",
        "family_proof_flag",
        "pet_proof_flag",
        "self_checkin_proof_flag",
    ]
    room_proof_flags = {field: truthy(own_audit.get(field) if field in own_audit else row.get(field)) for field in room_proof_fields}
    amenity_proof_flags = {field: truthy(own_audit.get(field) if field in own_audit else row.get(field)) for field in amenity_proof_fields}
    review_count = as_number(own_audit.get("review_count"), as_number(row.get("review_count"), 0)) or 0
    rating = as_number(own_audit.get("overall_rating"), as_number(row.get("rating")))
    own_segment = str(row.get("actual_guest_segment") or own_audit.get("guest_segment") or "").strip().lower()
    target_segment = str(row.get("guest_segment") or row.get("target_guest_segment") or "").strip().lower()
    design_gap_flag = (
        truthy(row.get("design_gap_flag"))
        or truthy(own_audit.get("design_gap_flag"))
        or bool(design_gap_flags)
        or (photo_product_score is not None and photo_product_score < 0.35)
    )

    issue = "no_clear_issue"
    fixes = ["monitor content and conversion against the A-comp set"]

    if search_to_listing is not None and search_to_listing < search_benchmark and strongest_comp_subject and own_hero != strongest_comp_subject:
        issue = "hero_photo_gap"
        fixes = [
            f"replace hero photo with {strongest_comp_subject} proof",
            "align title/search-card promise with the winning visible feature",
            "rerun logged-out search-card comparison after the photo change",
        ]
    elif search_to_listing is not None and search_to_listing < search_benchmark and len(first_five) < 5:
        issue = "photo_order_gap"
        fixes = [
            "reorder first 5 photos to prove the primary guest promise",
            "move bedroom, living, kitchen, and differentiator proof before decorative shots",
            "rerun search-to-listing conversion review after 14 days",
        ]
    elif listing_to_booking is not None and listing_to_booking < booking_benchmark and any("sleep" in str(item).lower() or "bed" in str(item).lower() for item in missing_proof):
        issue = "sleeping_capacity_not_proven"
        fixes = [
            "add and move sleeping-capacity proof into the early photo set",
            "make bed count and room layout visible in listing content",
            "compare against A-comps with similar capacity proof",
        ]
    elif missing_amenities or any(item in {"parking", "pool_or_spa", "view", "workspace", "family", "pet", "self_checkin"} for item in missing_proof):
        issue = "amenity_not_visible"
        missing_display = missing_amenities or [item for item in missing_proof if item in {"parking", "pool_or_spa", "view", "workspace", "family", "pet", "self_checkin"}]
        fixes = [
            f"show or complete visible amenity proof for {', '.join(map(str, missing_display[:3]))}",
            "update Airbnb amenity fields and photo captions where applicable",
            "rerun filtered public search after the amenity update",
        ]
    elif review_count < 5 or (rating is not None and rating < 4.7):
        issue = "trust_signal_gap"
        fixes = [
            "prioritize review quality and trust-signal recovery before aggressive pricing",
            "tighten accuracy, check-in, and cleanliness proof in content",
            "avoid benchmarking against mature A-comps without trust adjustment",
        ]
    elif design_gap_flag or photo_count < 12:
        issue = "design_gap"
        fixes = [
            "upgrade room presentation and photo coverage before price testing",
            "match A-comp proof for bedrooms, bathrooms, kitchen, and living spaces",
            "document design gaps that cannot be fixed without capex",
        ]
    elif own_segment and target_segment and own_segment != target_segment:
        issue = "guest_segment_mismatch"
        fixes = [
            "rewrite listing promise for the target guest segment",
            "adjust rules, sleeping layout, and amenities to match that segment",
            "rerun comp set using the corrected guest segment",
        ]
    elif comp_price_index is not None and comp_price_index > 1.12:
        issue = "price_not_content_problem"
        fixes = [
            "test price only after content and trust blockers are ruled out",
            "compare price only against A-comps in the same date and stay-length context",
            "protect margin floor and review conversion after the pricing test",
        ]

    confidence = "high" if evidence_refs and (a_comp_cards or a_comp_listings) else "medium" if evidence_refs else "low"
    return decision_record(
        decision="fix" if issue != "no_clear_issue" else "monitor",
        confidence=confidence,
        evidence_refs=evidence_refs,
        recommended_next_action=fixes[0],
        primary_gap=issue,
        issue_class=issue,
        top_3_fix_candidates=fixes[:3],
        comp_hero_subject_mode=strongest_comp_subject,
        comp_price_index=comp_price_index,
        first_five_photo_subjects=first_five,
        room_proof_flags=room_proof_flags,
        amenity_proof_flags=amenity_proof_flags,
        amenity_claims_proven_in_photos=as_list(own_audit.get("amenity_claims_proven_in_photos") or row.get("amenity_claims_proven_in_photos")),
        missing_photo_proof=missing_proof,
        missing_visible_amenities=missing_amenities,
        design_gap_flags=design_gap_flags,
        photo_product_score=photo_product_score,
        expected_metric="search_to_listing_conversion" if issue in {"hero_photo_gap", "photo_order_gap"} else "listing_to_booking_conversion" if issue != "no_clear_issue" else "content_quality_monitoring",
        review_window_days=int(as_number(row.get("review_window_days"), 14) or 14),
    )


def evaluate_case_study_replay(row):
    """Turn a walkthrough pattern into a bounded recommendation experiment."""
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, [
        "case_type",
        "starting_symptom",
        "hypothesis",
        "recommended_intervention",
        "expected_metric",
        "review_window_days",
    ])
    before_evidence = as_list(row.get("before_state_evidence") or row.get("available_evidence"))
    counterexamples = row.get("counterexample_matrix") or {}
    if not before_evidence:
        missing.append("before_state_evidence")
    if not counterexamples:
        missing.append("counterexample_matrix")
    if not row.get("pre_window"):
        missing.append("pre_window")
    if not row.get("post_window"):
        missing.append("post_window")
    if not row.get("rollback_criteria"):
        missing.append("rollback_criteria")
    interventions = as_list(row.get("recommended_intervention"))
    if len(interventions) > 1 or truthy(row.get("bundled_intervention_flag")):
        missing.append("single_smallest_viable_intervention")
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="case study replay requires before-state evidence, counterexamples, one intervention, metric, windows, and rollback criteria",
            recommended_next_action="complete the case replay evidence pack before creating a recommendation",
            validated_pattern=False,
            experiment_template=None,
        )

    counterexample_result = str(counterexamples.get("thesis_result") or row.get("counterexample_result") or "").lower()
    if counterexample_result in {"contradicted", "failed", "reject"}:
        return decision_record(
            decision="reject",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="counterexample matrix contradicts the case-study hypothesis",
            recommended_next_action="revise the hypothesis or reject the intervention pattern",
            validated_pattern=False,
            experiment_template=None,
        )

    intervention = interventions[0] if interventions else row.get("recommended_intervention")
    experiment = {
        "case_type": row.get("case_type"),
        "listing_id": row.get("listing_id"),
        "hypothesis": row.get("hypothesis"),
        "variant_description": intervention,
        "control_description": row.get("control_description") or "pre-intervention listing state and matched A-comp context",
        "target_metric": row.get("expected_metric"),
        "guardrail_metrics": as_list(row.get("guardrail_metrics")) or ["margin", "booking_quality", "review_quality"],
        "pre_period_start": (row.get("pre_window") or {}).get("start"),
        "pre_period_end": (row.get("pre_window") or {}).get("end"),
        "post_period_start": (row.get("post_window") or {}).get("start"),
        "post_period_end": (row.get("post_window") or {}).get("end"),
        "eligible_dates": as_list(row.get("eligible_dates")),
        "excluded_dates": as_list(row.get("excluded_dates")),
        "demand_context_controls": as_list(row.get("demand_context_controls")),
        "rollback_criteria": row.get("rollback_criteria"),
        "review_window_days": int(as_number(row.get("review_window_days"), 14) or 14),
    }
    confidence = "high" if evidence_refs and counterexample_result == "supported" else "medium" if evidence_refs else "low"
    return decision_record(
        decision="fix",
        confidence=confidence,
        evidence_refs=evidence_refs,
        recommended_next_action=intervention,
        validated_pattern=True,
        case_type=row.get("case_type"),
        starting_symptom=row.get("starting_symptom"),
        expected_metric=row.get("expected_metric"),
        experiment_template=experiment,
    )


def generate_calendar_actions(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, ["listing_id", "date", "calendar_state", "margin_floor"])
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="calendar action requires listing/date/state and margin floor",
            recommended_next_action="collect calendar, comp price, booking pace, and cost floor",
            action_candidates=[],
        )
    margin_floor = as_number(row.get("margin_floor"), 0) or 0
    proposed_price = as_number(row.get("proposed_price"), as_number(row.get("own_price"), 0)) or 0
    season = str(row.get("season_segment") or "").lower()
    booking_pace = str(row.get("booking_pace") or "").lower()
    comp_price_index = as_number(row.get("comp_price_index"))
    orphan_night = truthy(row.get("orphan_night_flag"))
    min_stay_choke = truthy(row.get("minimum_stay_choke_flag"))
    peak = season == "peak" or truthy(row.get("peak_demand_flag"))

    if proposed_price < margin_floor:
        return decision_record(
            decision="no_action",
            confidence="high",
            evidence_refs=evidence_refs,
            do_not_use_reason="proposed price or discount would fall below margin floor",
            recommended_next_action="protect price floor",
            action_candidates=[_calendar_action("protect_price_floor", row)],
        )

    actions = []
    if peak and str(row.get("requested_action") or "").startswith("slow_season"):
        actions.append(_calendar_action("no_action", row, reason="slow-season tactic requested for peak date without explicit evidence"))
    elif orphan_night and row.get("calendar_state") == "unbooked":
        actions.append(_calendar_action("fix_orphan_night", row))
    elif min_stay_choke:
        actions.append(_calendar_action("lower_minimum_stay", row))
    elif comp_price_index is not None and comp_price_index < 0.88 and booking_pace in {"ahead", "strong"}:
        actions.append(_calendar_action("raise_price", row))
    elif comp_price_index is not None and comp_price_index > 1.12 and booking_pace in {"behind", "weak"}:
        actions.append(_calendar_action("reduce_price", row))
    elif season == "slow" and booking_pace in {"behind", "weak"}:
        actions.append(_calendar_action("add_5_day_discount", row))
        actions.append(_calendar_action("add_14_day_discount", row))
    else:
        actions.append(_calendar_action("no_action", row))

    return decision_record(
        decision="fix" if actions and actions[0]["action_type"] != "no_action" else "no_action",
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action=actions[0]["action_type"],
        action_candidates=actions,
    )


def _calendar_action(action_type, row, reason=None):
    expected = {
        "raise_price": ("guest-facing total price", "increase"),
        "reduce_price": ("booking pace or conversion", "increase"),
        "add_promotion": ("booking pace", "increase"),
        "remove_peak_date_promotion": ("margin", "protect"),
        "lower_minimum_stay": ("bookable search coverage", "increase"),
        "fix_orphan_night": ("sellable orphan-night revenue", "increase"),
        "add_5_day_discount": ("slow-season booking pace", "increase"),
        "add_14_day_discount": ("slow-season booking pace", "increase"),
        "protect_price_floor": ("contribution margin", "protect"),
        "no_action": ("current performance", "monitor"),
    }
    expected_metric, expected_direction = expected.get(action_type, ("target metric", "monitor"))
    return {
        "listing_id": row.get("listing_id"),
        "target_date": row.get("date"),
        "action_type": action_type,
        "expected_metric": expected_metric,
        "expected_direction": expected_direction,
        "rollback_criteria": row.get("rollback_criteria") or "revert if booking pace, margin, or conversion worsens after review window",
        "review_window_days": int(as_number(row.get("review_window_days"), 14) or 14),
        "reason": reason,
    }


def audit_settings_drift(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    calendar_rows = as_list(row.get("calendar_rows"))
    strategy = row.get("intended_strategy") or {}
    missing = missing_fields(row, ["listing_id"])
    if not calendar_rows:
        missing.append("calendar_rows")
    if not strategy:
        missing.append("intended_strategy")
    margin_floor = first_number(row, "margin_floor", default=None)
    if margin_floor is None:
        margin_floor = as_number(strategy.get("price_floor"))
    if margin_floor is None:
        missing.append("margin_floor")
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=unique(missing),
            do_not_use_reason="settings drift audit requires listing, calendar rows, intended strategy, and margin floor",
            recommended_next_action="collect pricing settings, rule-sets, calendar snapshots, intended strategy, and cost floor",
            settings_drift_findings=[],
            drift_summary={},
        )

    findings = []
    pricing_settings = row.get("pricing_settings") or {}
    max_staleness_days = int(as_number(strategy.get("max_source_staleness_days"), as_number(row.get("max_source_staleness_days"), 7)) or 7)
    source_staleness_days = as_number(row.get("source_staleness_days"), as_number(pricing_settings.get("source_staleness_days")))
    if source_staleness_days is not None and source_staleness_days > max_staleness_days:
        findings.append(_settings_drift_finding(
            row,
            {},
            "stale_pricing_evidence",
            "medium",
            "unknown",
            "pricing/rule evidence older than strategy freshness window",
            "refresh pricing settings, rule-sets, and calendar snapshots before making pricing decisions",
            strategy,
            margin_floor,
            evidence_refs,
        ))

    source_of_authority = str(strategy.get("source_of_authority") or row.get("source_of_authority") or "").lower()
    pricing_sync_stale = truthy(row.get("pricing_source_stale_flag")) or truthy(pricing_settings.get("pricing_source_stale_flag"))
    days_since_sync = as_number(row.get("days_since_last_pricing_sync"), as_number(pricing_settings.get("days_since_last_pricing_sync")))
    if source_of_authority and source_of_authority not in {"airbnb_manual", "airbnb", "manual"}:
        sync_threshold = int(as_number(strategy.get("max_pricing_sync_age_days"), 2) or 2)
        if pricing_sync_stale or (days_since_sync is not None and days_since_sync > sync_threshold):
            findings.append(_settings_drift_finding(
                row,
                {},
                "software_sync_drift",
                "high",
                "underpricing",
                "pricing source is expected to control rates but sync evidence is stale",
                "inspect pricing software connection and last successful sync before trusting calendar prices",
                strategy,
                margin_floor,
                evidence_refs,
            ))

    for calendar_row in calendar_rows:
        if not isinstance(calendar_row, dict):
            continue
        context = _settings_date_context(calendar_row)
        active_discount_pct, active_discount_types = _active_discount_pct(calendar_row, pricing_settings)
        nightly_price = first_number(calendar_row, "nightly_price", "own_price", "base_price", default=first_number(row, "own_price", "base_price", default=0))
        effective_price = nightly_price * (1 - active_discount_pct / 100)
        high_demand = context in {"peak", "event", "holiday"} or truthy(calendar_row.get("peak_demand_flag")) or truthy(calendar_row.get("event_flag")) or truthy(calendar_row.get("holiday_flag"))
        strong_pace = str(calendar_row.get("booking_pace") or "").lower() in {"ahead", "strong"}
        allowed_discounts = {str(item).lower() for item in as_list(strategy.get("allowed_discount_types"))}
        blocked_discounts = {str(item).lower() for item in as_list(strategy.get("blocked_discount_types"))}

        if active_discount_pct > 0 and effective_price < margin_floor:
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "margin_floor_breach",
                "critical",
                "margin_leakage",
                "effective price after active discounts is below the margin floor",
                "protect price floor and remove or narrow the discount",
                strategy,
                margin_floor,
                evidence_refs,
                active_discount_pct=active_discount_pct,
                active_discount_types=active_discount_types,
                effective_price=effective_price,
            ))

        disallowed_discount = bool(active_discount_types & blocked_discounts) or (
            active_discount_pct > 0
            and (high_demand or strong_pace)
            and not truthy(strategy.get("allow_high_demand_discounts"))
            and not (active_discount_types and active_discount_types <= allowed_discounts)
        )
        if disallowed_discount:
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "discount_leakage",
                "critical" if high_demand else "high",
                "margin_leakage",
                "discount or promotion applies to a high-demand or strong-pace date without explicit strategy permission",
                "remove peak-date promotion or disable the leaking discount for the affected window",
                strategy,
                margin_floor,
                evidence_refs,
                active_discount_pct=active_discount_pct,
                active_discount_types=active_discount_types,
                effective_price=effective_price,
            ))

        smart_active = truthy(calendar_row.get("smart_pricing_flag")) or truthy(pricing_settings.get("smart_pricing_enabled"))
        smart_policy = str(strategy.get("smart_pricing_policy") or "").lower()
        smart_min = first_number(pricing_settings, "smart_pricing_min", default=first_number(calendar_row, "smart_pricing_min", default=None))
        if smart_active and smart_policy in {"off", "manual_only", "custom_rule_controls"}:
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "smart_pricing_conflict",
                "high",
                "underpricing",
                "Smart Pricing is active where the intended strategy says manual or custom rule-set control should govern",
                "disable Smart Pricing for governed dates or update the intended strategy with evidence",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))
        if smart_active and smart_min is not None and smart_min < margin_floor:
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "smart_pricing_conflict",
                "critical",
                "underpricing",
                "Smart Pricing minimum is below the margin floor",
                "raise Smart Pricing minimum above margin floor before trusting automated pricing",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        active_rule_set_count = int(as_number(calendar_row.get("active_rule_set_count"), 1 if present(calendar_row.get("rule_set_id")) else 0) or 0)
        if active_rule_set_count > 1 or truthy(calendar_row.get("overlapping_rule_set_conflict_flag")):
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "rule_set_overlap_conflict",
                "high",
                "unknown",
                "multiple or conflicting rule-sets appear active for the same date",
                "inspect active rule-sets and remove the conflicting overlap",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        if high_demand and truthy(strategy.get("require_rule_set_for_high_demand")) and not present(calendar_row.get("rule_set_id")):
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "rule_set_gap",
                "medium",
                "underpricing",
                "high-demand date has no active rule-set even though strategy requires governed pricing",
                "add or verify the event/holiday rule-set before the demand window",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        valid_until = strategy.get("custom_price_valid_until") or calendar_row.get("custom_price_valid_until")
        if truthy(calendar_row.get("custom_price_flag")) and valid_until and str(calendar_row.get("calendar_date") or "") > str(valid_until):
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "stale_manual_override",
                "medium",
                "unknown",
                "custom calendar price remains active after its intended review window",
                "remove the stale override or document a new review window",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        minimum_stay = as_number(calendar_row.get("minimum_stay"))
        orphan_gap = as_number(calendar_row.get("orphan_gap_nights"))
        common_max_stay = as_number(strategy.get("common_short_stay_max_nights"), as_number(row.get("common_short_stay_max_nights")))
        if minimum_stay is not None and ((orphan_gap is not None and 0 < orphan_gap < minimum_stay) or (common_max_stay is not None and minimum_stay > common_max_stay and high_demand)):
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "minimum_stay_choke",
                "high" if orphan_gap else "medium",
                "lost_bookability",
                "minimum-stay rule blocks an otherwise relevant search or orphan-night opportunity",
                "create a temporary margin-safe minimum-stay rule for the affected dates",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        if high_demand and (falsy(calendar_row.get("check_in_allowed")) or falsy(calendar_row.get("checkout_allowed"))):
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "checkin_checkout_choke",
                "high",
                "lost_bookability",
                "check-in or checkout restriction blocks a high-demand date pattern",
                "review arrival/departure restrictions for the demand window",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

        promo_intended = truthy(calendar_row.get("promotion_intended")) or truthy(strategy.get("promotion_intended"))
        promo_status = str(calendar_row.get("custom_promotion_eligibility_status") or pricing_settings.get("custom_promotion_eligibility_status") or "").lower()
        if promo_intended and promo_status in {"ineligible", "blocked", "not_eligible"}:
            findings.append(_settings_drift_finding(
                row,
                calendar_row,
                "promotion_eligibility_gap",
                "medium",
                "lost_bookability",
                "promotion is intended but Airbnb eligibility or median-price rules block it",
                "use manual pricing action or wait until promotion eligibility clears",
                strategy,
                margin_floor,
                evidence_refs,
                effective_price=effective_price,
            ))

    findings = _merge_settings_drift_findings(findings)
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "monitor": 0}
    highest = max((severity_rank.get(item["severity"], 0) for item in findings), default=0)
    decision = "fix" if highest >= 3 else "monitor" if findings else "no_action"
    recommended = findings[0]["recommended_next_action"] if findings else "monitor settings drift on the next cadence"
    return decision_record(
        decision=decision,
        confidence="high" if evidence_refs and findings else "medium" if evidence_refs else "low",
        evidence_refs=evidence_refs,
        recommended_next_action=recommended,
        settings_drift_findings=findings,
        drift_summary={
            "finding_count": len(findings),
            "critical_count": sum(1 for item in findings if item["severity"] == "critical"),
            "high_count": sum(1 for item in findings if item["severity"] == "high"),
            "affected_dates_count": len({item.get("target_date") for item in findings if item.get("target_date")}),
        },
    )


def _settings_date_context(calendar_row):
    explicit = str(calendar_row.get("date_class") or calendar_row.get("demand_context") or calendar_row.get("season_segment") or "").lower()
    if explicit:
        return explicit
    if truthy(calendar_row.get("event_flag")):
        return "event"
    if truthy(calendar_row.get("holiday_flag")):
        return "holiday"
    if truthy(calendar_row.get("peak_demand_flag")):
        return "peak"
    return "ordinary"


def _active_discount_pct(calendar_row, pricing_settings):
    discount_fields = {
        "custom_promotion_discount_pct": "custom_promotion",
        "active_promotion_discount_pct": "custom_promotion",
        "length_of_stay_discount_pct": "length_of_stay",
        "weekly_discount_pct": "weekly",
        "monthly_discount_pct": "monthly",
        "last_minute_discount_pct": "last_minute",
        "early_bird_discount_pct": "early_bird",
        "active_discount_pct": "manual_discount",
    }
    total = 0
    types = set()
    for field, discount_type in discount_fields.items():
        value = as_number(calendar_row.get(field), as_number(pricing_settings.get(field), 0)) or 0
        if value > 0:
            total += value
            types.add(discount_type)
    total = min(total, 95)
    return total, types


def _settings_drift_finding(
    row,
    calendar_row,
    drift_type,
    severity,
    revenue_risk_direction,
    reason,
    next_action,
    strategy,
    margin_floor,
    evidence_refs,
    *,
    active_discount_pct=0,
    active_discount_types=None,
    effective_price=None,
):
    return {
        "listing_id": row.get("listing_id"),
        "target_date": calendar_row.get("calendar_date") or row.get("target_date"),
        "target_date_or_window": row.get("target_date_or_window") or calendar_row.get("calendar_date"),
        "drift_type": drift_type,
        "severity": severity,
        "affected_dates_count": 1 if calendar_row.get("calendar_date") else 0,
        "affected_nights": int(as_number(calendar_row.get("affected_nights"), 1 if calendar_row.get("calendar_date") else 0) or 0),
        "revenue_risk_direction": revenue_risk_direction,
        "intended_setting": strategy,
        "actual_setting": {
            "nightly_price": calendar_row.get("nightly_price"),
            "minimum_stay": calendar_row.get("minimum_stay"),
            "maximum_stay": calendar_row.get("maximum_stay"),
            "check_in_allowed": calendar_row.get("check_in_allowed"),
            "checkout_allowed": calendar_row.get("checkout_allowed"),
        },
        "active_rule_set_id": calendar_row.get("rule_set_id"),
        "active_discount_or_promotion": sorted(active_discount_types or []),
        "active_discount_pct": active_discount_pct,
        "smart_pricing_state": calendar_row.get("smart_pricing_flag"),
        "margin_floor": margin_floor,
        "effective_price_after_discounts": effective_price,
        "demand_context": _settings_date_context(calendar_row),
        "comp_price_index": calendar_row.get("comp_price_index"),
        "decision": "fix" if severity in {"critical", "high"} else "monitor",
        "confidence": "high" if evidence_refs else "medium",
        "evidence_refs": evidence_refs,
        "do_not_use_reason": reason,
        "recommended_next_action": next_action,
        "rollback_criteria": calendar_row.get("rollback_criteria") or "revert if booking pace, margin, or conversion worsens after review window",
        "review_window_days": int(as_number(calendar_row.get("review_window_days"), 14) or 14),
    }


def _merge_settings_drift_findings(findings):
    merged = {}
    for finding in findings:
        key = (finding["listing_id"], finding["target_date"], finding["drift_type"], finding["severity"])
        existing = merged.get(key)
        if not existing:
            merged[key] = finding
            continue
        existing["affected_dates_count"] += finding.get("affected_dates_count", 0)
        existing["affected_nights"] += finding.get("affected_nights", 0)
        existing["evidence_refs"] = unique(existing.get("evidence_refs", []) + finding.get("evidence_refs", []))
    return list(merged.values())


def evaluate_operations_risk(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, ["listing_id"])
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="operations risk requires listing_id",
            recommended_next_action="collect reviews, messages, tasks, and turnover evidence",
            risks=[],
        )
    risk_rules = [
        ("cleaning_quality_risk", "cleaning_theme_count", "audit cleaning checklist and cleaner feedback loop"),
        ("checkin_risk", "checkin_issue_count", "fix check-in instructions and arrival messaging"),
        ("message_gap_risk", "message_gap_count", "repair scheduled messages or quick replies"),
        ("maintenance_recurrence", "maintenance_repeat_count", "open maintenance recurrence task"),
        ("fee_complaint_risk", "fee_complaint_count", "review fee transparency and listing copy"),
        ("turnover_overload", "tight_turnover_count", "reduce turnover load or add cleaner capacity"),
        ("review_theme_regression", "negative_review_theme_count", "review recent theme regression and intervene"),
    ]
    risks = []
    for risk_class, field, intervention in risk_rules:
        count = int(as_number(row.get(field), 0) or 0)
        if count <= 0:
            continue
        severity = "high" if count >= 3 else "medium" if count == 2 else "low"
        risks.append({
            "affected_listing": row.get("listing_id"),
            "risk_class": risk_class,
            "severity": severity,
            "recent_examples": as_list(row.get(f"{field}_examples")),
            "recommended_intervention": intervention,
            "next_review_window": row.get("next_review_window") or "next 5 eligible stays or next review cycle",
            "evidence_refs": evidence_refs,
        })
    return decision_record(
        decision="fix" if risks else "monitor",
        confidence="high" if evidence_refs and risks else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action=risks[0]["recommended_intervention"] if risks else "monitor operations risk",
        risks=risks,
    )


def evaluate_channel_strategy(row):
    row = row or {}
    evidence_refs = as_list(row.get("evidence_refs"))
    missing = missing_fields(row, ["market_research_decision", "product_channel_fit"])
    if missing:
        return decision_record(
            decision="needs_more_data",
            confidence="low",
            evidence_refs=evidence_refs,
            missing_required_evidence=missing,
            do_not_use_reason="channel strategy requires market evidence and product-channel fit",
            recommended_next_action="complete market evidence before channel expansion",
            channel_recommendations=[],
        )
    if row.get("market_research_decision") not in {"pursue", "watch", "fix", "monitor"}:
        return decision_record(
            decision="no_action",
            confidence="medium",
            evidence_refs=evidence_refs,
            do_not_use_reason="channel expansion should not proceed before market evidence supports the product",
            recommended_next_action="keep Airbnb-native pricing and rank decisions on Airbnb evidence",
            channel_recommendations=[],
        )
    fits = row.get("product_channel_fit") or {}
    ops_ready = truthy(row.get("operations_can_support_channels"))
    recommendations = []
    for channel, fit in fits.items():
        if channel not in CHANNELS:
            continue
        if truthy(fit) and (channel == "airbnb" or ops_ready):
            recommendations.append({"channel": channel, "recommendation": "use" if channel == "airbnb" else "test", "evidence_refs": evidence_refs})
    return decision_record(
        decision="fix" if any(item["channel"] != "airbnb" for item in recommendations) else "monitor",
        confidence="high" if evidence_refs else "medium",
        evidence_refs=evidence_refs,
        recommended_next_action="create recommendation/action log entries for selected channel tests",
        channel_recommendations=recommendations,
        default_source_for_airbnb_native_decisions="airbnb",
    )


def build_listing_opportunity_snapshot(row):
    row = row or {}
    a_prices = [as_number(item.get("visible_price_total")) for item in as_list(row.get("a_comp_price_rows")) if isinstance(item, dict)]
    a_prices = [price for price in a_prices if price is not None]
    own_price = as_number(row.get("own_total_price"))
    median_a = median(a_prices) if a_prices else None
    comp_price_index = (own_price / median_a) if own_price is not None and median_a else None
    conversion = diagnose_listing_conversion({**row, "comp_price_index": comp_price_index})
    maturity = grade_listing_maturity(row.get("review_maturity_input") or row)
    opportunity_issue = opportunity_issue_type(row, comp_price_index, conversion["conversion_issue_type"])
    return {
        "listing_id": row.get("listing_id"),
        "target_date_or_window": row.get("target_date_or_window"),
        "guest_segment": row.get("guest_segment"),
        "stay_length": row.get("stay_length"),
        "own_rank_or_absence": row.get("own_rank_or_absence"),
        "own_total_price": own_price,
        "median_A_comp_total_price": median_a,
        "comp_price_index": comp_price_index,
        "review_maturity_status": maturity["maturity_grade"],
        "conversion_issue_type": opportunity_issue,
        "top_3_fix_candidates": conversion["top_3_fix_candidates"],
        "confidence": "high" if as_list(row.get("evidence_refs")) and a_prices else "medium" if a_prices else "low",
        "evidence_refs": as_list(row.get("evidence_refs")),
        "decision": conversion["decision"],
        "missing_required_evidence": [] if a_prices else ["a_comp_price_rows"],
        "do_not_use_reason": None if a_prices else "A-comp prices are missing",
        "recommended_next_action": conversion["recommended_next_action"],
    }


def opportunity_issue_type(row, comp_price_index, conversion_issue):
    if truthy((row or {}).get("minimum_stay_choke_flag")):
        return "minimum_stay_choke"
    if comp_price_index is not None and comp_price_index > 1.12:
        return "overpriced_vs_A_comps"
    if comp_price_index is not None and comp_price_index < 0.88:
        return "underpriced_vs_A_comps"
    mapping = {
        "visibility_problem": "weak_search_visibility",
        "search_card_click_problem": "weak_click_appeal",
        "listing_page_conversion_problem": "listing_page_conversion_issue",
        "trust_signal_gap": "review_trust_gap",
        "amenity_visibility_gap": "amenity_filter_gap",
        "price_friction": "overpriced_vs_A_comps",
    }
    return mapping.get(conversion_issue, "no_clear_issue")
