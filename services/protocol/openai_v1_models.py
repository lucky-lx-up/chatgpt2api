from __future__ import annotations

from typing import Any

from services.account_service import account_service
from services.image_model_service import (
    enabled_image_model_ids,
    image_model_capability_payload,
    is_configurable_image_model_identifier,
)
from services.model_service import model_catalog_service
from utils.helper import (
    CODEX_IMAGE_MODEL,
    GPT_IMAGE_25_FLARE_MODEL,
    GPT_IMAGE_25_SUNBURST_MODEL,
    LEGACY_IMAGE_MODEL,
)


def list_models() -> dict[str, Any]:
    result = model_catalog_service.list_models()
    data = result.get("data")
    if not isinstance(data, list):
        return result
    data = [
        item
        for item in data
        if not (
            isinstance(item, dict)
            and is_configurable_image_model_identifier(item.get("id"))
        )
    ]
    result["data"] = data
    dynamic_models: set[str] = set()
    accounts = account_service.list_accounts()
    web_image_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) != "codex"
    ]
    codex_types = {
        normalized
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) == "codex"
           and (normalized := account_service._normalize_account_type(account.get("type")))
    }

    if web_image_accounts:
        dynamic_models.add(LEGACY_IMAGE_MODEL)
        for model in (GPT_IMAGE_25_SUNBURST_MODEL, GPT_IMAGE_25_FLARE_MODEL):
            if model in enabled_image_model_ids():
                dynamic_models.add(model)
    if codex_types & {"Plus", "Team", "Pro"}:
        dynamic_models.add(CODEX_IMAGE_MODEL)
    if "Plus" in codex_types:
        dynamic_models.add(f"plus-{CODEX_IMAGE_MODEL}")
    if "Team" in codex_types:
        dynamic_models.add(f"team-{CODEX_IMAGE_MODEL}")
    if "Pro" in codex_types:
        dynamic_models.add(f"pro-{CODEX_IMAGE_MODEL}")

    for model in sorted(dynamic_models):
        existing = next(
            (item for item in data if isinstance(item, dict) and str(item.get("id") or "").strip() == model),
            None,
        )
        if existing is not None:
            existing["chatgpt2api_capabilities"] = image_model_capability_payload(model)
            continue
        data.append({
            "id": model,
            "object": "model",
            "created": 0,
            "owned_by": "chatgpt2api",
            "permission": [],
            "root": model,
            "parent": None,
            "chatgpt2api_capabilities": image_model_capability_payload(model),
        })
    return result
