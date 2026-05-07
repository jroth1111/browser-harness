"""Skill router — domain skills as projections over the authority pipeline.

Domain skills should contain: surface maps, route manifests, field contracts,
risk policies, parsers, fixtures, and handoff rules. They should NOT own
transport authority (urllib, cdp, stealth_session, etc.).

The skill router loads domain skill manifests and routes their requests
through the AccessPlane.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..capabilities.models import RiskLevel, RouteRule, TransportType


@dataclass
class SkillManifest:
    name: str
    version: str = "0.1.0"
    domain: str = ""
    description: str = ""
    surfaces: list[dict[str, str]] = field(default_factory=list)
    route_rules: list[RouteRule] = field(default_factory=list)
    risk_policies: dict[str, str] = field(default_factory=dict)
    extraction_fields: list[str] = field(default_factory=list)
    handoff_triggers: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)


class SkillRouter:
    """Load and route domain skill requests through the authority pipeline."""

    def __init__(self, skill_dir: Path | None = None):
        self._skill_dir = skill_dir
        self._manifests: dict[str, SkillManifest] = {}

    def load_manifest(self, skill_name: str, manifest_path: Path | None = None) -> SkillManifest | None:
        """Load a domain skill manifest."""
        if manifest_path and manifest_path.exists():
            return self._parse_manifest(skill_name, manifest_path)

        if self._skill_dir:
            candidates = [
                self._skill_dir / skill_name / "manifest.json",
                self._skill_dir / skill_name / "skill.json",
            ]
            for path in candidates:
                if path.exists():
                    return self._parse_manifest(skill_name, path)

        return None

    def route_for_url(self, url: str) -> list[SkillManifest]:
        """Find skills that handle a given URL."""
        from urllib.parse import urlparse
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        matches = []
        for manifest in self._manifests.values():
            for rule in manifest.route_rules:
                if rule.origin == origin:
                    matches.append(manifest)
                    break

        return matches

    def risk_for_action(self, skill_name: str, action: str) -> str:
        """Get the risk level for an action in a skill."""
        manifest = self._manifests.get(skill_name)
        if manifest:
            return manifest.risk_policies.get(action, "low_risk_write")
        return "low_risk_write"

    def _parse_manifest(self, skill_name: str, path: Path) -> SkillManifest | None:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        rules = []
        for r in data.get("route_rules", []):
            rules.append(RouteRule(
                origin=r.get("origin", ""),
                path_pattern=r.get("path_pattern", ".*"),
                allowed_methods=r.get("allowed_methods", ["GET"]),
                risk_max=RiskLevel(r.get("risk_max", "public_read")),
                transport_preference=TransportType(r.get("transport", "public_http")),
                auth_required=r.get("auth_required", False),
                source="skill_manifest",
            ))

        manifest = SkillManifest(
            name=skill_name,
            version=data.get("version", "0.1.0"),
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            surfaces=data.get("surfaces", []),
            route_rules=rules,
            risk_policies=data.get("risk_policies", {}),
            extraction_fields=data.get("extraction_fields", []),
            handoff_triggers=data.get("handoff_triggers", []),
            forbidden_patterns=data.get("forbidden_patterns", []),
        )
        self._manifests[skill_name] = manifest
        return manifest
