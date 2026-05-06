"""Registry of known providers, lazy-imported.

Each provider package lives under ``providers/<id>/`` and exports a single
class implementing ``lib.provider_base.Provider``. The registry maps the
short provider id used on the CLI (and stored in the ``providers`` table)
to that class.

Lazy-imported because:
  * a missing optional dep in one provider shouldn't break ``--provider X``;
  * the harvest script wants to enumerate cookie domains without paying the
    import cost of every provider.
"""
from __future__ import annotations

import importlib
from typing import Type

from .provider_base import Provider


_PROVIDERS: dict[str, str] = {
    "chatgpt":    "providers.chatgpt:ChatGPTProvider",
    "claude":     "providers.claude:ClaudeProvider",
    "perplexity": "providers.perplexity:PerplexityProvider",
    "grok":       "providers.grok:GrokProvider",
    "gemini":     "providers.gemini:GeminiProvider",
}


def list_provider_ids() -> list[str]:
    return list(_PROVIDERS.keys())


def load_provider(provider_id: str) -> Type[Provider]:
    spec = _PROVIDERS.get(provider_id)
    if spec is None:
        raise KeyError(f"unknown provider: {provider_id}")
    module_name, _, class_name = spec.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    if not issubclass(cls, Provider):
        raise TypeError(f"{spec} is not a Provider subclass")
    return cls


def cookie_domains(provider_id: str) -> list[str]:
    """Used by harvest to filter raw cookie sweeps before authenticating."""
    return load_provider(provider_id).cookie_domains
