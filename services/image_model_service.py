from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from services.config import config
from utils.helper import (
    CODEX_IMAGE_MODEL,
    GPT_IMAGE_25_FLARE_MODEL,
    GPT_IMAGE_25_SUNBURST_MODEL,
    LEGACY_IMAGE_MODEL,
    PREFIXED_CODEX_IMAGE_MODELS,
    image_model_capabilities,
    split_image_model,
)

UNSUPPORTED_WEB_IMAGE_PARAMETERS = {
    "background",
    "output_format",
    "output_compression",
    "moderation",
    "partial_images",
    "input_image_mask",
    "previous_response_id",
}

_IMAGE_SIZE_RE = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)$", re.IGNORECASE)


def is_configurable_image_model_identifier(model: object) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized == "gpt-image-2.5" or normalized.startswith("gpt-image-2.5-")


def image_model_upstream_route(model: object) -> str:
    _, base_model = split_image_model(model)
    if base_model == LEGACY_IMAGE_MODEL:
        return config.default_upstream_model_name
    if base_model == GPT_IMAGE_25_SUNBURST_MODEL:
        return config.gpt_image_25_sunburst_upstream_model_name
    if base_model == GPT_IMAGE_25_FLARE_MODEL:
        return config.gpt_image_25_flare_upstream_model_name
    if base_model == CODEX_IMAGE_MODEL:
        return CODEX_IMAGE_MODEL
    return ""


def is_image_model_enabled(model: object) -> bool:
    _, base_model = split_image_model(model)
    if not base_model:
        return False
    if base_model in {GPT_IMAGE_25_SUNBURST_MODEL, GPT_IMAGE_25_FLARE_MODEL}:
        return bool(image_model_upstream_route(base_model))
    return True


def enabled_image_model_ids() -> set[str]:
    models = {LEGACY_IMAGE_MODEL, CODEX_IMAGE_MODEL, *PREFIXED_CODEX_IMAGE_MODELS}
    for model in (GPT_IMAGE_25_SUNBURST_MODEL, GPT_IMAGE_25_FLARE_MODEL):
        if is_image_model_enabled(model):
            models.add(model)
    return models


def image_model_capability_payload(model: object) -> dict[str, object]:
    capabilities = image_model_capabilities(model)
    return {
        "quality_values": list(capabilities.get("quality_values") or ()),
        "max_resolution": bool(capabilities.get("max_resolution")),
        "strict_dimensions": bool(capabilities.get("strict_dimensions")),
    }


def reject_unsupported_web_image_parameters(parameters: object) -> None:
    if not isinstance(parameters, dict):
        return
    unsupported = sorted(
        key
        for key in UNSUPPORTED_WEB_IMAGE_PARAMETERS
        if key in parameters and parameters.get(key) is not None
    )
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported image parameter for the ChatGPT web image route: " + ", ".join(unsupported),
            },
        )


def validate_image_request(
    model: object,
    *,
    size: object = None,
    quality: object = "auto",
    parameters: object = None,
) -> str:
    normalized_model = str(model or "").strip().lower()
    _, base_model = split_image_model(normalized_model)
    if not base_model:
        raise HTTPException(status_code=400, detail={"error": f"unsupported image model: {normalized_model or model}"})
    if not is_image_model_enabled(normalized_model):
        raise HTTPException(
            status_code=400,
            detail={"error": f"image model '{base_model}' is not configured with an upstream route"},
        )

    reject_unsupported_web_image_parameters(parameters)

    capabilities = image_model_capabilities(base_model)
    normalized_quality = str(quality or "auto").strip().lower() or "auto"
    if capabilities.get("strict_dimensions"):
        allowed_quality_values = {str(value) for value in capabilities.get("quality_values") or ()}
        if normalized_quality not in allowed_quality_values:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "quality must be one of: " + ", ".join(sorted(allowed_quality_values)),
                },
            )
        _validate_gpt_image_25_size(size)

    return base_model


def _validate_gpt_image_25_size(size: object) -> None:
    value = str(size or "").strip().lower()
    if not value:
        return
    match = _IMAGE_SIZE_RE.fullmatch(value)
    if not match:
        raise HTTPException(status_code=400, detail={"error": "size must use WIDTHxHEIGHT for GPT Image 2.5"})

    width = int(match.group("width"))
    height = int(match.group("height"))
    if width % 16 or height % 16:
        raise HTTPException(status_code=400, detail={"error": "GPT Image 2.5 size dimensions must be divisible by 16"})
    if max(width, height) > 3840:
        raise HTTPException(status_code=400, detail={"error": "GPT Image 2.5 size dimensions cannot exceed 3840"})
    if max(width, height) > min(width, height) * 3:
        raise HTTPException(status_code=400, detail={"error": "GPT Image 2.5 aspect ratio must be between 1:3 and 3:1"})
    pixels = width * height
    if not 655_360 <= pixels <= 8_294_400:
        raise HTTPException(
            status_code=400,
            detail={"error": "GPT Image 2.5 image size must contain between 655360 and 8294400 pixels"},
        )
