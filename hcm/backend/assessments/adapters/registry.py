from __future__ import annotations

from .base import AssessmentProviderAdapter
from .sandbox import SandboxAdapter

_ADAPTER_CLASSES: dict[str, type[AssessmentProviderAdapter]] = {
    SandboxAdapter.provider_key: SandboxAdapter,
}


def get_active_adapter() -> AssessmentProviderAdapter:
    """Resolves the adapter via ProviderConfig (DB-driven, not a settings
    import) — an HR/sysadmin flipping which row has active=True swaps the
    provider without a code change or redeploy, per the Sprint 12
    acceptance criterion."""
    from ..models import ProviderConfig

    config = ProviderConfig.objects.filter(active=True).first()
    provider_key = config.provider_key if config is not None else SandboxAdapter.provider_key
    adapter_cls = _ADAPTER_CLASSES.get(provider_key)
    if adapter_cls is None:
        raise ValueError(f"No adapter registered for provider_key={provider_key!r}")
    return adapter_cls()
