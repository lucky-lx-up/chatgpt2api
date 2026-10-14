from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException

from services.config import config
from services.image_model_service import (
    image_model_upstream_route,
    is_image_model_enabled,
    validate_image_request,
)
from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI
from utils.helper import GPT_IMAGE_25_FLARE_MODEL, GPT_IMAGE_25_SUNBURST_MODEL


class GptImage25ModelTests(unittest.TestCase):
    def test_variants_default_to_official_upstream_routes(self) -> None:
        for override in (
            {
                "gpt_image_25_sunburst_upstream_model_name": "",
                "gpt_image_25_flare_upstream_model_name": "",
            },
            {},
        ):
            with self.subTest(override=override), mock.patch.dict(config.data, override, clear=not override):
                self.assertTrue(is_image_model_enabled(GPT_IMAGE_25_SUNBURST_MODEL))
                self.assertTrue(is_image_model_enabled(GPT_IMAGE_25_FLARE_MODEL))
                self.assertEqual(
                    image_model_upstream_route(GPT_IMAGE_25_SUNBURST_MODEL),
                    GPT_IMAGE_25_SUNBURST_MODEL,
                )
                self.assertEqual(
                    image_model_upstream_route(GPT_IMAGE_25_FLARE_MODEL),
                    GPT_IMAGE_25_FLARE_MODEL,
                )
                self.assertEqual(
                    validate_image_request(GPT_IMAGE_25_SUNBURST_MODEL, size="1024x1024", quality="high"),
                    GPT_IMAGE_25_SUNBURST_MODEL,
                )

    def test_variant_uses_its_configured_upstream_route(self) -> None:
        with mock.patch.dict(
            config.data,
            {
                "gpt_image_25_sunburst_upstream_model_name": "upstream-sunburst",
                "gpt_image_25_flare_upstream_model_name": "upstream-flare",
            },
            clear=False,
        ):
            self.assertTrue(is_image_model_enabled(GPT_IMAGE_25_SUNBURST_MODEL))
            self.assertEqual(image_model_upstream_route(GPT_IMAGE_25_FLARE_MODEL), "upstream-flare")
            backend = OpenAIBackendAPI(access_token="test-token")
            self.assertEqual(backend._image_model_settings(GPT_IMAGE_25_SUNBURST_MODEL), ("upstream-sunburst", ""))
            backend.close()

    def test_gpt_image_25_validates_quality_and_dimensions(self) -> None:
        with mock.patch.dict(
            config.data,
            {"gpt_image_25_sunburst_upstream_model_name": "upstream-sunburst"},
            clear=False,
        ):
            self.assertEqual(
                validate_image_request(GPT_IMAGE_25_SUNBURST_MODEL, size="1536x1024", quality="xhigh"),
                GPT_IMAGE_25_SUNBURST_MODEL,
            )
            for size, error in (
                ("1024x1365", "divisible by 16"),
                ("4096x1024", "cannot exceed 3840"),
                ("1024x512", "between 655360 and 8294400 pixels"),
                ("1024x4096", "cannot exceed 3840"),
            ):
                with self.subTest(size=size), self.assertRaises(HTTPException) as context:
                    validate_image_request(GPT_IMAGE_25_SUNBURST_MODEL, size=size, quality="high")
                self.assertIn(error, str(context.exception.detail))
            with self.assertRaises(HTTPException) as context:
                validate_image_request(GPT_IMAGE_25_SUNBURST_MODEL, size="1024x1024", quality="ultra")
        self.assertIn("quality must be one of", str(context.exception.detail))

    def test_gpt_image_25_uses_configured_route_for_prepare_and_start(self) -> None:
        payloads: list[dict] = []

        class FakeResponse:
            status_code = 200

            def __init__(self, data: dict | None = None) -> None:
                self._data = data or {}

            def json(self) -> dict:
                return self._data

        backend = OpenAIBackendAPI(access_token="test-token")
        backend.session.post = mock.Mock(side_effect=[FakeResponse({"conduit_token": "conduit"}), FakeResponse()])
        requirements = ChatRequirements(token="requirements")

        with mock.patch.dict(
            config.data,
            {"gpt_image_25_sunburst_upstream_model_name": "upstream-sunburst"},
            clear=False,
        ):
            conduit = backend._prepare_image_conversation("draw", requirements, GPT_IMAGE_25_SUNBURST_MODEL)
            backend._start_image_generation("draw", requirements, conduit, GPT_IMAGE_25_SUNBURST_MODEL)

        for call in backend.session.post.call_args_list:
            payloads.append(call.kwargs["json"])
        backend.close()

        self.assertEqual(conduit, "conduit")
        self.assertEqual([payload["model"] for payload in payloads], ["upstream-sunburst", "upstream-sunburst"])


if __name__ == "__main__":
    unittest.main()
