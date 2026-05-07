"""Skill router tests — prove domain skills route through authority."""
import json
import pytest
from pathlib import Path

from browser_harness.projections.skill_router import SkillRouter, SkillManifest
from browser_harness.capabilities.models import RiskLevel, RouteRule


class TestSkillRouter:
    def test_load_manifest_from_file(self, tmp_path):
        manifest_data = {
            "name": "test-skill",
            "version": "0.1.0",
            "domain": "test",
            "route_rules": [
                {
                    "origin": "https://example.com",
                    "path_pattern": "/api/.*",
                    "allowed_methods": ["GET"],
                    "risk_max": "public_read",
                    "transport": "public_http",
                }
            ],
            "risk_policies": {"discover": "public_read"},
            "extraction_fields": ["name", "price"],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        router = SkillRouter()
        manifest = router.load_manifest("test-skill", manifest_path)
        assert manifest is not None
        assert manifest.name == "test-skill"
        assert len(manifest.route_rules) == 1
        assert manifest.route_rules[0].origin == "https://example.com"

    def test_route_for_url(self, tmp_path):
        manifest_data = {
            "name": "food-delivery",
            "route_rules": [
                {"origin": "https://www.doordash.com", "path_pattern": "/v2/.*"},
            ],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        router = SkillRouter(skill_dir=tmp_path)
        router.load_manifest("food-delivery", manifest_path)

        matches = router.route_for_url("https://www.doordash.com/v2/merchant/123")
        assert len(matches) == 1
        assert matches[0].name == "food-delivery"

    def test_no_match_for_unknown_url(self, tmp_path):
        manifest_data = {
            "name": "food-delivery",
            "route_rules": [
                {"origin": "https://www.doordash.com", "path_pattern": "/v2/.*"},
            ],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        router = SkillRouter(skill_dir=tmp_path)
        router.load_manifest("food-delivery", manifest_path)

        matches = router.route_for_url("https://other.example.com/page")
        assert len(matches) == 0

    def test_risk_for_action(self, tmp_path):
        manifest_data = {
            "name": "food-delivery",
            "risk_policies": {
                "discover_apis": "authenticated_read",
                "export": "public_read",
            },
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        router = SkillRouter(skill_dir=tmp_path)
        router.load_manifest("food-delivery", manifest_path)

        assert router.risk_for_action("food-delivery", "discover_apis") == "authenticated_read"
        assert router.risk_for_action("food-delivery", "export") == "public_read"
        assert router.risk_for_action("food-delivery", "unknown_action") == "low_risk_write"

    def test_load_food_delivery_manifest(self):
        """Load the real food-delivery manifest from the repo."""
        manifest_path = Path(__file__).parent.parent / "domain-skills" / "food-delivery" / "manifest.json"
        if not manifest_path.exists():
            pytest.skip("food-delivery manifest not yet created")

        router = SkillRouter()
        manifest = router.load_manifest("food-delivery", manifest_path)
        assert manifest is not None
        assert manifest.domain == "food-delivery"
        assert len(manifest.route_rules) >= 1
        assert len(manifest.extraction_fields) >= 1
        assert "login_redirect" in manifest.handoff_triggers
        assert "stealth_session" in manifest.forbidden_patterns

    def test_malformed_manifest_returns_none(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not json")

        router = SkillRouter()
        result = router.load_manifest("broken", manifest_path)
        assert result is None
