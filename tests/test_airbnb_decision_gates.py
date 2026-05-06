import json
import importlib.util
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/decision_gates.py")
    spec = importlib.util.spec_from_file_location("airbnb_decision_gates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_fixture(name):
    path = Path("domain-skills/airbnb/fixtures/decision-gates") / name
    return json.loads(path.read_text(encoding="utf-8"))


def mature_comp_row(**overrides):
    row = {
        "same_map_boundary_flag": True,
        "same_room_type_flag": True,
        "same_property_class_flag": True,
        "same_bedroom_band_flag": True,
        "same_target_guest_count_flag": True,
        "same_stay_length_flag": True,
        "same_date_or_season_flag": True,
        "same_core_amenity_filters_flag": True,
        "same_visible_price_context_flag": True,
        "same_channel_flag": True,
        "can_host_reproduce": "yes",
        "maturity_grade": "mature",
        "evidence_refs": ["search-run-1", "listing-1"],
    }
    row.update(overrides)
    return row


def survival_rows(slow_net):
    return [
        {"season_segment": "peak", "net_after_tactics": 5000, "adr_floor": 420, "occupancy_floor": 0.82},
        {"season_segment": "shoulder", "net_after_tactics": 3200, "adr_floor": 310, "occupancy_floor": 0.64},
        {"season_segment": "slow", "net_after_tactics": slow_net, "adr_floor": 180, "occupancy_floor": 0.38},
    ]


def test_property_validation_fails_without_address_boundary_or_equal_worse_proof():
    module = load_module()

    result = module.evaluate_market_research_pack({
        "research_mode": "property_validation",
        "strict_comp_selection": "pass",
        "counterexample_matrix": "supported",
        "listing_maturity_filter": "pass",
        "slow_season_survival_model": "pass",
        "beautiful_broad_market_winners": ["premium-listing"],
    })

    assert result["decision"] == "needs_more_data"
    assert "target_address_or_building" in result["missing_required_evidence"]
    assert "map_boundary_receipt" in result["missing_required_evidence"]
    assert "same_building_or_same_block_comps_or_equal_or_worse_profitable_comps" in result["missing_required_evidence"]


def test_property_validation_with_equal_or_worse_proof_can_pursue():
    module = load_module()

    result = module.evaluate_market_research_pack({
        "research_mode": "property_validation",
        "target_address_or_building": "500 Elizabeth Street",
        "map_boundary_receipt": {"title": "Homes within map area"},
        "selected_filter_chips": ["Entire home", "3+ bedrooms"],
        "map_friction_assessment": {"barrier_type": "none"},
        "equal_or_worse_profitable_comps": [{"listing_id": "123"}],
        "strict_comp_selection": "pass",
        "counterexample_matrix": "supported",
        "listing_maturity_filter": "pass",
        "slow_season_survival_model": "pass",
        "evidence_refs": ["market-run-1"],
    })

    assert result["decision"] == "pursue"
    assert result["market_research_decision"] == "pursue"


def test_market_research_cannot_pursue_with_non_passing_required_gate():
    module = load_module()

    result = module.evaluate_market_research_pack({
        "research_mode": "property_validation",
        "target_address_or_building": "500 Elizabeth Street",
        "map_boundary_receipt": {"title": "Homes within map area"},
        "selected_filter_chips": ["Entire home", "3+ bedrooms"],
        "map_friction_assessment": {"barrier_type": "none"},
        "equal_or_worse_profitable_comps": [{"listing_id": "123"}],
        "strict_comp_selection": "pass",
        "counterexample_matrix": "supported",
        "listing_maturity_filter": "needs_more_data",
        "slow_season_survival_model": "pass",
        "evidence_refs": ["market-run-1"],
    })

    assert result["decision"] == "watch"
    assert result["market_research_decision"] == "watch"
    assert result["non_passing_gates"] == ["listing_maturity_filter"]


def test_beautiful_unreproducible_comp_is_inspiration_only():
    module = load_module()

    result = module.grade_public_comp(mature_comp_row(can_host_reproduce="no"))

    assert result["comp_grade"] == "C"
    assert result["evidence_use"] == "inspiration"
    assert result["decision"] == "watch"


def test_missing_entire_home_public_scan_gate_is_covered_by_planner():
    path = Path("domain-skills/airbnb/scripts/public_scan_planner.py")
    spec = importlib.util.spec_from_file_location("airbnb_public_scan_planner", path)
    planner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(planner)

    try:
        planner.validate_similarity_filter_pack(["min_bedrooms=3"])
    except ValueError as error:
        assert "Entire home" in str(error)
    else:
        raise AssertionError("missing Entire home should fail normal public comp validation")

    assert planner.validate_similarity_filter_pack(["Room"], explicit_room_study=True)["checked"] is True


def test_boosted_or_low_review_listing_cannot_support_base_case():
    module = load_module()

    maturity = module.grade_listing_maturity({
        "review_count": 1,
        "high_rank_signal": True,
        "new_listing_flag": True,
        "evidence_refs": ["search-card-1"],
    })
    comp = module.grade_public_comp(mature_comp_row(maturity_grade=maturity["maturity_grade"]))

    assert maturity["maturity_grade"] == "boosted_or_unproven"
    assert maturity["can_use_for_underwriting_flag"] is False
    assert comp["comp_grade"] == "C"
    assert comp["evidence_use"] == "inspiration"


def test_mature_recent_review_comp_can_support_base_case():
    module = load_module()

    maturity = module.grade_listing_maturity({
        "review_count": 44,
        "latest_review_date": "2026-04-15",
        "recent_review_count_90d": 7,
        "evidence_refs": ["listing-review-snapshot"],
    })
    comp = module.grade_public_comp(mature_comp_row(maturity_grade=maturity["maturity_grade"]))

    assert maturity["maturity_grade"] == "mature"
    assert maturity["underwriting_use"] == "base_case"
    assert comp["comp_grade"] == "A"
    assert comp["evidence_use"] == "underwriting"


def test_slow_season_model_rejects_peak_only_deal():
    module = load_module()

    result = module.evaluate_slow_season_survival({
        "season_rows": survival_rows(slow_net=900),
        "candidate_cost_floor": 1200,
        "required_monthly_net": 2500,
        "monthly_or_14_day_fallback_available": False,
        "evidence_refs": ["slow-season-grid"],
    })

    assert result["survival_decision"] == "reject"
    assert result["decision"] == "reject"
    assert result["monthly_or_14_day_fallback_needed"] is True


def test_slow_season_model_passes_when_weak_months_clear_floor():
    module = load_module()

    result = module.evaluate_slow_season_survival({
        "season_rows": survival_rows(slow_net=2700),
        "candidate_cost_floor": 1200,
        "required_monthly_net": 2500,
        "evidence_refs": ["slow-season-grid"],
    })

    assert result["survival_decision"] == "pass"
    assert result["decision"] == "no_action"


def test_calendar_action_generator_refuses_below_margin_discount():
    module = load_module()

    result = module.generate_calendar_actions({
        "listing_id": "100",
        "date": "2026-07-01",
        "calendar_state": "unbooked",
        "margin_floor": 300,
        "proposed_price": 250,
        "evidence_refs": ["calendar-date-1"],
    })

    assert result["decision"] == "no_action"
    assert result["action_candidates"][0]["action_type"] == "protect_price_floor"
    assert "margin floor" in result["do_not_use_reason"]


def test_settings_drift_requires_strategy_calendar_and_margin_floor():
    module = load_module()

    result = module.audit_settings_drift({"listing_id": "100"})

    assert result["decision"] == "needs_more_data"
    assert "calendar_rows" in result["missing_required_evidence"]
    assert "intended_strategy" in result["missing_required_evidence"]
    assert "margin_floor" in result["missing_required_evidence"]


def test_settings_drift_flags_peak_discount_leakage():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 260,
        "intended_strategy": {
            "date_class": "event",
            "blocked_discount_types": ["custom_promotion"],
            "smart_pricing_policy": "custom_rule_controls",
        },
        "calendar_rows": [{
            "calendar_date": "2026-12-31",
            "date_class": "event",
            "nightly_price": 650,
            "custom_promotion_discount_pct": 20,
            "booking_pace": "strong",
            "rule_set_id": "nye-premium",
        }],
        "evidence_refs": ["calendar:2026-12-31", "pricing-settings"],
    })

    assert result["decision"] == "fix"
    finding_types = {finding["drift_type"] for finding in result["settings_drift_findings"]}
    assert "discount_leakage" in finding_types
    leakage = next(finding for finding in result["settings_drift_findings"] if finding["drift_type"] == "discount_leakage")
    assert leakage["severity"] == "critical"
    assert leakage["recommended_next_action"].startswith("remove peak-date promotion")


def test_settings_drift_blocks_discount_below_margin_floor():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 300,
        "intended_strategy": {"date_class": "slow", "allowed_discount_types": ["weekly"]},
        "calendar_rows": [{
            "calendar_date": "2026-08-04",
            "date_class": "slow",
            "nightly_price": 320,
            "weekly_discount_pct": 10,
        }],
        "evidence_refs": ["calendar:2026-08-04"],
    })

    assert result["decision"] == "fix"
    breach = result["settings_drift_findings"][0]
    assert breach["drift_type"] == "margin_floor_breach"
    assert breach["effective_price_after_discounts"] == 288
    assert breach["recommended_next_action"] == "protect price floor and remove or narrow the discount"


def test_settings_drift_flags_smart_pricing_conflict_and_low_minimum():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 250,
        "pricing_settings": {"smart_pricing_enabled": True, "smart_pricing_min": 220},
        "intended_strategy": {"smart_pricing_policy": "custom_rule_controls"},
        "calendar_rows": [{"calendar_date": "2026-10-03", "nightly_price": 400, "smart_pricing_flag": True}],
        "evidence_refs": ["pricing-settings", "calendar:2026-10-03"],
    })

    findings = result["settings_drift_findings"]
    assert result["decision"] == "fix"
    assert any(finding["drift_type"] == "smart_pricing_conflict" for finding in findings)
    assert any(finding["severity"] == "high" for finding in findings)
    assert any(finding["severity"] == "critical" for finding in findings)


def test_settings_drift_flags_orphan_minimum_stay_choke():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 180,
        "intended_strategy": {"date_class": "ordinary_weekend", "common_short_stay_max_nights": 2},
        "calendar_rows": [{
            "calendar_date": "2026-09-12",
            "date_class": "ordinary_weekend",
            "nightly_price": 310,
            "minimum_stay": 3,
            "orphan_gap_nights": 2,
        }],
        "evidence_refs": ["calendar:2026-09-12"],
    })

    assert result["decision"] == "fix"
    assert result["settings_drift_findings"][0]["drift_type"] == "minimum_stay_choke"
    assert result["settings_drift_findings"][0]["revenue_risk_direction"] == "lost_bookability"


def test_settings_drift_flags_pricing_software_sync_staleness():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 200,
        "days_since_last_pricing_sync": 4,
        "intended_strategy": {
            "source_of_authority": "pricelabs",
            "max_pricing_sync_age_days": 2,
        },
        "calendar_rows": [{"calendar_date": "2026-11-01", "nightly_price": 420}],
        "evidence_refs": ["pricing-source-receipt"],
    })

    assert result["decision"] == "fix"
    assert result["settings_drift_findings"][0]["drift_type"] == "software_sync_drift"
    assert result["settings_drift_findings"][0]["severity"] == "high"


def test_settings_drift_allows_explicit_slow_season_discount_above_floor():
    module = load_module()

    result = module.audit_settings_drift({
        "listing_id": "100",
        "margin_floor": 200,
        "intended_strategy": {
            "date_class": "slow",
            "allowed_discount_types": ["weekly"],
            "smart_pricing_policy": "off",
        },
        "calendar_rows": [{
            "calendar_date": "2026-08-11",
            "date_class": "slow",
            "nightly_price": 300,
            "weekly_discount_pct": 10,
        }],
        "evidence_refs": ["calendar:2026-08-11"],
    })

    assert result["decision"] == "no_action"
    assert result["settings_drift_findings"] == []


def test_conversion_diagnosis_distinguishes_visibility_click_booking_and_price():
    module = load_module()

    assert module.diagnose_listing_conversion({"listing_id": "1", "evidence_refs": ["rank"]})["conversion_issue_type"] == "visibility_problem"
    assert module.diagnose_listing_conversion({
        "listing_id": "1",
        "search_rank": 5,
        "search_to_listing_rate": 0.01,
        "search_to_listing_benchmark": 0.03,
        "evidence_refs": ["insights"],
    })["conversion_issue_type"] == "search_card_click_problem"
    assert module.diagnose_listing_conversion({
        "listing_id": "1",
        "search_rank": 5,
        "listing_to_booking_rate": 0.002,
        "listing_to_booking_benchmark": 0.01,
        "evidence_refs": ["insights"],
    })["conversion_issue_type"] == "listing_page_conversion_problem"
    assert module.diagnose_listing_conversion({
        "listing_id": "1",
        "search_rank": 5,
        "comp_price_index": 1.3,
        "evidence_refs": ["price-index"],
    })["conversion_issue_type"] == "price_friction"


def test_photo_product_gap_audit_finds_hero_gap_before_price_cut():
    module = load_module()

    result = module.audit_photo_product_gap({
        "listing_id": "100",
        "guest_segment": "family_group",
        "stay_length": 3,
        "own_search_card": {"hero_photo_subject_tag": "building exterior"},
        "own_public_listing_audit": {"photo_count": 20, "review_count": 30, "overall_rating": 4.9},
        "own_conversion_metrics": {"search_to_listing_rate": 0.01},
        "search_to_listing_benchmark": 0.03,
        "a_comp_cards": [
            {"hero_photo_subject_tag": "free parking", "visible_price_total": 1000},
            {"hero_photo_subject_tag": "free parking", "visible_price_total": 1100},
        ],
        "own_total_price": 1050,
        "evidence_refs": ["own-public", "a-comps"],
    })

    assert result["decision"] == "fix"
    assert result["primary_gap"] == "hero_photo_gap"
    assert result["expected_metric"] == "search_to_listing_conversion"
    assert result["top_3_fix_candidates"][0].startswith("replace hero photo")


def test_photo_product_gap_audit_separates_price_from_content_problem():
    module = load_module()

    result = module.audit_photo_product_gap({
        "listing_id": "100",
        "guest_segment": "business",
        "stay_length": 2,
        "own_search_card": {"hero_photo_subject_tag": "workspace"},
        "own_public_listing_audit": {
            "photo_count": 24,
            "review_count": 44,
            "overall_rating": 4.92,
            "first_five_photo_subjects": ["workspace", "bedroom", "bathroom", "kitchen", "living room"],
        },
        "a_comp_cards": [
            {"hero_photo_subject_tag": "workspace", "visible_price_total": 1000},
            {"hero_photo_subject_tag": "workspace", "visible_price_total": 1050},
        ],
        "comp_price_index": 1.25,
        "evidence_refs": ["own-public", "a-comps", "price-index"],
    })

    assert result["decision"] == "fix"
    assert result["primary_gap"] == "price_not_content_problem"
    assert "price" in result["recommended_next_action"]


def test_case_study_replay_requires_before_state_counterexample_and_single_intervention():
    module = load_module()

    result = module.evaluate_case_study_replay({
        "case_type": "photo_conversion_rescue",
        "starting_symptom": "low click-through",
        "hypothesis": "hero photo is weak",
        "recommended_intervention": ["replace hero photo", "drop price"],
        "expected_metric": "search_to_listing_conversion",
        "review_window_days": 14,
        "evidence_refs": ["case-pack"],
    })

    assert result["decision"] == "needs_more_data"
    assert "before_state_evidence" in result["missing_required_evidence"]
    assert "counterexample_matrix" in result["missing_required_evidence"]
    assert "single_smallest_viable_intervention" in result["missing_required_evidence"]


def test_case_study_replay_creates_experiment_template():
    module = load_module()

    result = module.evaluate_case_study_replay({
        "case_type": "photo_conversion_rescue",
        "listing_id": "100",
        "starting_symptom": "high impressions with low search-to-listing conversion",
        "before_state_evidence": ["own-public", "insights", "a-comps"],
        "hypothesis": "hero photo fails to show scarce parking proof",
        "counterexample_matrix": {"thesis_result": "supported", "winner_with_feature": "A comp", "loser_without_feature": "own listing"},
        "recommended_intervention": "replace hero photo with parking proof",
        "expected_metric": "search_to_listing_conversion",
        "pre_window": {"start": "2026-04-01", "end": "2026-04-14"},
        "post_window": {"start": "2026-04-15", "end": "2026-04-29"},
        "rollback_criteria": "revert if search-to-listing conversion worsens",
        "review_window_days": 14,
        "evidence_refs": ["case-pack"],
    })

    assert result["decision"] == "fix"
    assert result["validated_pattern"] is True
    assert result["experiment_template"]["target_metric"] == "search_to_listing_conversion"
    assert result["experiment_template"]["variant_description"] == "replace hero photo with parking proof"


def test_operations_risk_emits_severity_and_evidence_for_recurring_issues():
    module = load_module()

    result = module.evaluate_operations_risk({
        "listing_id": "100",
        "cleaning_theme_count": 3,
        "checkin_issue_count": 1,
        "cleaning_theme_count_examples": ["dust", "bathroom"],
        "evidence_refs": ["reviews"],
    })

    assert result["decision"] == "fix"
    assert result["risks"][0]["risk_class"] == "cleaning_quality_risk"
    assert result["risks"][0]["severity"] == "high"
    assert result["risks"][0]["evidence_refs"] == ["reviews"]


def test_channel_strategy_requires_market_evidence_before_expansion():
    module = load_module()

    missing = module.evaluate_channel_strategy({"product_channel_fit": {"vrbo": True}})

    assert missing["decision"] == "needs_more_data"
    assert "market_research_decision" in missing["missing_required_evidence"]

    result = module.evaluate_channel_strategy({
        "market_research_decision": "pursue",
        "product_channel_fit": {"airbnb": True, "vrbo": True, "booking_com": True},
        "operations_can_support_channels": True,
        "evidence_refs": ["channel-scan"],
    })

    assert result["decision"] == "fix"
    assert {item["channel"] for item in result["channel_recommendations"]} == {"airbnb", "vrbo", "booking_com"}


def test_listing_opportunity_snapshot_joins_own_listing_comps_maturity_and_conversion():
    module = load_module()

    result = module.build_listing_opportunity_snapshot({
        "listing_id": "100",
        "target_date_or_window": "2026-07",
        "guest_segment": "family",
        "stay_length": 3,
        "own_rank_or_absence": 24,
        "own_total_price": 1300,
        "a_comp_price_rows": [{"visible_price_total": 1000}, {"visible_price_total": 1100}, {"visible_price_total": 1200}],
        "review_maturity_input": {"review_count": 33, "latest_review_date": "2026-04-01", "recent_review_count_90d": 5},
        "search_rank": 24,
        "photo_count": 20,
        "evidence_refs": ["own-public", "comp-scan"],
    })

    assert result["median_A_comp_total_price"] == 1100
    assert round(result["comp_price_index"], 2) == 1.18
    assert result["review_maturity_status"] == "mature"
    assert result["conversion_issue_type"] == "overpriced_vs_A_comps"


def test_recommendation_records_include_required_decision_fields():
    module = load_module()

    result = module.generate_calendar_actions({
        "listing_id": "100",
        "date": "2026-07-01",
        "calendar_state": "unbooked",
        "margin_floor": 200,
        "own_price": 350,
        "orphan_night_flag": True,
        "evidence_refs": ["calendar-date-1"],
    })

    for field in ["decision", "confidence", "evidence_refs", "missing_required_evidence", "do_not_use_reason", "recommended_next_action"]:
        assert field in result
    action = result["action_candidates"][0]
    assert action["action_type"] == "fix_orphan_night"
    assert action["expected_metric"] == "sellable orphan-night revenue"
    assert action["expected_direction"] == "increase"
    assert action["rollback_criteria"]
    assert action["review_window_days"] == 14


def test_fixture_property_validation_passes_with_same_boundary_proof():
    module = load_module()

    result = module.evaluate_market_research_pack(load_fixture("property-validation-pass.json"))

    assert result["decision"] == "pursue"


def test_fixture_property_validation_rejects_unreproducible_premium_comps():
    module = load_module()

    comp = module.grade_public_comp(load_fixture("premium-unreproducible-comp.json"))
    market = module.evaluate_market_research_pack(load_fixture("property-validation-premium-only.json"))

    assert comp["comp_grade"] == "C"
    assert comp["evidence_use"] == "inspiration"
    assert market["decision"] in {"watch", "reject"}


def test_fixture_listing_opportunity_snapshot_uses_core_diagnosis():
    module = load_module()

    result = module.build_listing_opportunity_snapshot(load_fixture("listing-opportunity-overpriced.json"))

    assert result["conversion_issue_type"] == "overpriced_vs_A_comps"
    assert result["top_3_fix_candidates"]


def test_fixture_slow_season_pass_and_reject_cases():
    module = load_module()

    passing = module.evaluate_slow_season_survival(load_fixture("slow-season-pass.json"))
    failing = module.evaluate_slow_season_survival(load_fixture("slow-season-reject.json"))

    assert passing["survival_decision"] == "pass"
    assert failing["survival_decision"] == "reject"


def test_fixture_operations_creates_cleaning_and_checkin_risk():
    module = load_module()

    result = module.evaluate_operations_risk(load_fixture("operations-cleaning-checkin-risk.json"))

    risks = {risk["risk_class"]: risk for risk in result["risks"]}
    assert risks["cleaning_quality_risk"]["severity"] == "high"
    assert risks["checkin_risk"]["severity"] == "medium"


def test_fixture_settings_drift_peak_leakage_and_rule_gap():
    module = load_module()

    result = module.audit_settings_drift(load_fixture("settings-drift-peak-leakage.json"))

    finding_types = {finding["drift_type"] for finding in result["settings_drift_findings"]}
    assert result["decision"] == "fix"
    assert "discount_leakage" in finding_types
    assert "rule_set_gap" in finding_types


def test_fixture_photo_product_gap_audit_uses_visual_comp_set():
    module = load_module()

    result = module.audit_photo_product_gap(load_fixture("photo-gap-hero-missing-winning-amenity.json"))

    assert result["decision"] == "fix"
    assert result["primary_gap"] == "hero_photo_gap"
    assert result["comp_hero_subject_mode"] == "free parking"


def test_photo_product_gap_audit_uses_normalized_proof_fields():
    module = load_module()

    result = module.audit_photo_product_gap({
        "listing_id": "123",
        "guest_segment": "family",
        "stay_length": "3 nights",
        "evidence_refs": ["own-public:123", "comp-card:1"],
        "own_search_card": {"hero_photo_subject_tag": "bedroom"},
        "own_public_listing_audit": {
            "photo_count": 24,
            "review_count": 40,
            "overall_rating": 4.9,
            "first_five_photo_subjects": ["bedroom", "bathroom", "kitchen", "living_area", "workspace"],
            "parking_proof_flag": False,
            "missing_photo_proof": ["parking"],
            "amenity_claims_proven_in_photos": ["bedroom", "bathroom", "kitchen"],
            "photo_product_score": 0.42,
        },
        "a_comp_cards": [{"hero_photo_subject_tag": "bedroom", "visible_price_total": 1000}],
        "own_conversion_metrics": {"listing_to_booking_rate": 0.02},
    })

    assert result["primary_gap"] == "amenity_not_visible"
    assert result["amenity_proof_flags"]["parking_proof_flag"] is False
    assert result["missing_photo_proof"] == ["parking"]
    assert result["photo_product_score"] == 0.42


def test_content_optimization_brief_generates_copy_and_missing_shots():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "source_issue_class": "hero_photo_gap",
        "target_guest_segment": "business",
        "stay_length": "3 nights",
        "why_book": "skyline balcony",
        "current_title_text": "CBD apartment",
        "listing_facts": {
            "max_guests": 4,
            "bedrooms": 2,
            "beds": 2,
            "floor_level": 53,
            "parking_details": {"count": 1, "clearance_m": 2.1},
        },
        "location_facts": {"walkable_anchors": ["Free Tram Zone 200 m"]},
        "own_public_listing_audit": {
            "hero_photo_subject": "living_area",
            "first_five_photo_subjects": ["living_area", "kitchen"],
            "missing_photo_proof": ["parking"],
        },
        "evidence_refs": ["own-public", "a-comp-visuals"],
    })

    assert result["decision"] == "fix"
    assert result["brief_status"] == "ready_for_review"
    assert "hero_photo_change" in result["optimization_scope"]
    assert result["recommended_primary_title"] == "Skyline Balcony"
    assert "{" not in result["recommended_primary_title"]
    assert result["above_fold_primary"].startswith("Skyline balcony with parking")
    assert "Sleeps 4, 2 bedrooms, 2 beds" in result["above_fold_primary"]
    assert result["hero_title_alignment"] == "review_required"
    assert result["expected_metric"] == "search_to_listing_conversion"
    assert result["review_window_days"] == 14
    assert any("Parking bay" in item for item in result["missing_shots"])
    assert result["ab_test_plan"]["variants"][0]["above_fold"] == result["above_fold_primary"]


def test_content_optimization_brief_requires_evidence_unless_forced():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "source_issue_class": "hero_photo_gap",
        "why_book": "skyline balcony",
    })

    assert result["decision"] == "needs_more_data"
    assert "evidence_refs" in result["missing_required_evidence"]


def test_content_optimization_brief_routes_non_content_issues_away():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "source_issue_class": "price_not_content_problem",
        "evidence_refs": ["price-index"],
    })

    assert result["decision"] == "monitor"
    assert result["optimization_scope"] == []
    assert "not a content-optimization trigger" in result["do_not_use_reason"]


def test_content_optimization_brief_allows_explicit_user_forced_work():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "source_issue_class": "price_not_content_problem",
        "force_content_brief": True,
        "why_book": "skyline balcony",
        "current_title_text": "CBD apartment",
    })

    assert result["decision"] == "fix"
    assert result["brief_status"] == "ready_for_review"
    assert result["optimization_scope"] == ["title_above_fold_rewrite", "hero_photo_change"]
    assert result["recommended_primary_title"] == "Skyline Balcony"
    assert result["evidence_refs"] == []


def test_content_optimization_brief_marks_missing_host_facts():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "source_issue_class": "guest_segment_mismatch",
        "why_book": "work-ready skyline apartment",
        "current_title_text": "CBD apartment",
        "evidence_refs": ["conversion-diagnosis"],
    })

    assert result["decision"] == "fix"
    assert result["brief_status"] == "needs_host_facts"
    assert "listing facts for section copy" in result["missing_required_facts"]
    assert result["recommended_next_action"].startswith("collect missing host facts")


def test_content_optimization_brief_accepts_nested_photo_product_audit():
    module = load_module()

    result = module.build_listing_content_optimization_brief({
        "listing_id": "123",
        "why_book": "secure parking",
        "current_title_text": "CBD apartment",
        "source_photo_product_gap_audit": {
            "photo_product_gap_audit_id": "gap-1",
            "issue_class": "hero_photo_gap",
            "expected_metric": "search_to_listing_conversion",
            "review_window_days": 30,
            "evidence_refs": ["gap-audit:1"],
        },
        "own_public_listing_audit": {
            "hero_photo_subject": "exterior",
            "first_five_photo_subjects": ["exterior", "living_area"],
        },
    })

    assert result["decision"] == "fix"
    assert result["source_issue_class"] == "hero_photo_gap"
    assert result["source_decision_gate"] == "airbnb_photo_product_gap_audit"
    assert result["source_photo_product_gap_audit_id"] == "gap-1"
    assert result["expected_metric"] == "search_to_listing_conversion"
    assert result["review_window_days"] == 30
    assert result["evidence_refs"] == ["gap-audit:1"]


def test_fixture_gallery_cro_execution_board_creates_ship_ready_order():
    module = load_module()

    result = module.build_gallery_cro_execution_board(load_fixture("gallery-cro-execution-board.json"))

    assert result["decision"] == "fix"
    assert result["board_status"] == "ready_to_ship"
    assert result["hero_primary_photo_id_or_subject"] == "parking-hero"
    assert result["hero_crop_safety_score"] == 91
    assert [item["photo_id_or_subject"] for item in result["first_five_order"]] == [
        "parking-hero",
        "lounge-wide",
        "kitchen-wide",
        "primary-bedroom",
        "bathroom-wide",
    ]
    assert "pool_or_spa" in result["missing_proof_shots"]
    assert result["caption_copy_pairings"][0]["photo_id_or_subject"] == "parking-hero"
    assert result["ab_test_plan"]["fallback_kpi"] == "search_to_listing_conversion"
    assert result["rollback_plan"]["restore_photo_order"][0] == "old-exterior"


def test_gallery_cro_execution_board_refuses_price_only_issue_without_request():
    module = load_module()

    result = module.build_gallery_cro_execution_board({
        "listing_id": "100",
        "source_issue_class": "price_not_content_problem",
        "evidence_refs": ["price-index"],
    })

    assert result["decision"] == "monitor"
    assert result["board_status"] == "not_applicable"
    assert "not a gallery CRO trigger" in result["do_not_use_reason"]


def test_gallery_cro_execution_board_requires_exact_selected_photo_ids():
    module = load_module()

    result = module.build_gallery_cro_execution_board({
        "listing_id": "100",
        "source_issue_class": "hero_photo_gap",
        "target_guest_segment": "family",
        "stay_length": "2 nights",
        "why_book": "secure parking",
        "title_or_search_card_promise": "Secure parking city stay",
        "current_photo_order": ["old-1", "old-2", "old-3", "old-4", "old-5"],
        "candidate_photos": [
            {"subject": "secure parking", "demand_driver_score": 92, "clarity_diagnosticity_score": 88, "crop_safety_score": 90},
            {"subject": "lounge", "demand_driver_score": 80, "clarity_diagnosticity_score": 80, "crop_safety_score": 82},
        ],
        "evidence_refs": ["own-public", "comp-visuals"],
    })

    assert result["decision"] == "needs_more_data"
    assert "exact_photo_ids_for_selected_first_five" in result["missing_required_evidence"]
    assert result["first_five_order"][0]["photo_id_or_subject"].startswith("subject:parking")


def test_gallery_cro_execution_board_rejects_unknown_issue_without_request():
    module = load_module()

    result = module.build_gallery_cro_execution_board({
        "listing_id": "100",
        "source_issue_class": "unknown_operator_hunch",
        "target_guest_segment": "family",
        "stay_length": "2 nights",
        "why_book": "secure parking",
        "title_or_search_card_promise": "Secure parking city stay",
        "current_photo_order": ["old-1", "old-2", "old-3", "old-4", "old-5"],
        "candidate_photos": [
            {"photo_id": "parking-hero", "subject": "secure parking", "demand_driver_score": 92, "clarity_diagnosticity_score": 88, "crop_safety_score": 90},
            {"photo_id": "lounge-wide", "subject": "lounge", "demand_driver_score": 80, "clarity_diagnosticity_score": 80, "crop_safety_score": 82},
        ],
        "evidence_refs": ["own-public", "comp-visuals"],
    })

    assert result["decision"] == "reject"
    assert result["board_status"] == "not_applicable"
    assert "not a recognized gallery CRO trigger" in result["do_not_use_reason"]


def test_fixture_case_study_replay_produces_experiment_template():
    module = load_module()

    result = module.evaluate_case_study_replay(load_fixture("case-study-photo-conversion-replay.json"))

    assert result["decision"] == "fix"
    assert result["validated_pattern"] is True
    assert result["experiment_template"]["review_window_days"] == 14
