"""Provider registry — browser providers are adapters, not authority.

Provider choice is made by ProviderPolicy, not by domain scripts.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable


class ProviderCapability(enum.Flag):
    VISIBLE_UI = enum.auto()
    USER_PROFILE = enum.auto()
    CDP = enum.auto()
    SCREENSHOTS = enum.auto()
    STEALTH = enum.auto()
    ISOLATED_PROFILE = enum.auto()
    IDENTITY_COHERENT_HTTP = enum.auto()
    HEADLESS = enum.auto()


@dataclass
class ProviderInfo:
    provider_id: str
    capabilities: ProviderCapability = ProviderCapability(0)
    description: str = ""
    launch_fn: Callable[..., Any] | None = None


class ProviderRegistry:
    """Registry of browser providers. Domain skills cannot launch providers directly."""

    def __init__(self):
        self._providers: dict[str, ProviderInfo] = {}

    def register(self, info: ProviderInfo) -> None:
        self._providers[info.provider_id] = info

    def get(self, provider_id: str) -> ProviderInfo | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ProviderInfo]:
        return list(self._providers.values())

    def find_by_capability(self, cap: ProviderCapability) -> list[ProviderInfo]:
        return [p for p in self._providers.values() if cap in p.capabilities]

    def launch(self, provider_id: str, **kwargs: Any) -> Any:
        provider = self._providers.get(provider_id)
        if not provider:
            raise ValueError(f"unknown provider: {provider_id}")
        if not provider.launch_fn:
            raise RuntimeError(f"provider {provider_id} has no launch function")
        return provider.launch_fn(**kwargs)


def default_registry() -> ProviderRegistry:
    """Build a registry with built-in provider definitions."""
    registry = ProviderRegistry()

    registry.register(ProviderInfo(
        provider_id="local_chrome",
        capabilities=(
            ProviderCapability.VISIBLE_UI
            | ProviderCapability.USER_PROFILE
            | ProviderCapability.CDP
            | ProviderCapability.SCREENSHOTS
            | ProviderCapability.HEADLESS
        ),
        description="Local Chrome via CDP",
    ))

    def _launch_patchright(**kwargs):
        from ..stealth_helpers import stealth_session
        return stealth_session(
            headless=kwargs.get("headless", False),
            user_data_dir=kwargs.get("user_data_dir"),
            channel=kwargs.get("channel"),
        )

    registry.register(ProviderInfo(
        provider_id="patchright",
        capabilities=(
            ProviderCapability.CDP
            | ProviderCapability.SCREENSHOTS
            | ProviderCapability.STEALTH
            | ProviderCapability.ISOLATED_PROFILE
            | ProviderCapability.IDENTITY_COHERENT_HTTP
            | ProviderCapability.HEADLESS
        ),
        description="Patchright stealth browser",
        launch_fn=_launch_patchright,
    ))

    def _launch_camoufox(**kwargs):
        from ..stealth_helpers import camoufox_session
        return camoufox_session(
            headless=kwargs.get("headless", False),
            user_data_dir=kwargs.get("user_data_dir"),
            proxy=kwargs.get("proxy"),
        )

    registry.register(ProviderInfo(
        provider_id="camoufox",
        capabilities=(
            ProviderCapability.SCREENSHOTS
            | ProviderCapability.STEALTH
            | ProviderCapability.ISOLATED_PROFILE
            | ProviderCapability.IDENTITY_COHERENT_HTTP
            | ProviderCapability.HEADLESS
        ),
        description="Camoufox anti-detect browser (Firefox-based, engine-level fingerprinting)",
        launch_fn=_launch_camoufox,
    ))

    registry.register(ProviderInfo(
        provider_id="kernel",
        capabilities=(
            ProviderCapability.VISIBLE_UI
            | ProviderCapability.CDP
            | ProviderCapability.SCREENSHOTS
            | ProviderCapability.HEADLESS
            | ProviderCapability.ISOLATED_PROFILE
        ),
        description="Kernel Chromium Docker (isolated local Chromium via CDP)",
    ))

    registry.register(ProviderInfo(
        provider_id="lightpanda",
        capabilities=(
            ProviderCapability.CDP
            | ProviderCapability.HEADLESS
        ),
        description="Lightpanda lightweight browser engine",
    ))

    return registry
