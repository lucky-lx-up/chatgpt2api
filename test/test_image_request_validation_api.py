from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.ai as ai_module
from services.config import config
from utils.helper import GPT_IMAGE_25_SUNBURST_MODEL


AUTH_HEADERS = {"Authorization": "Bearer chatgpt2api"}


class ImageRequestValidationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[dict] = []
        self.handler_patcher = mock.patch.object(
            ai_module.openai_v1_image_generations,
            "handle",
            side_effect=lambda payload: self.calls.append(payload) or {"created": 1, "data": []},
        )
        self.filter_patcher = mock.patch.object(ai_module, "filter_or_log", mock.AsyncMock())
        self.handler_patcher.start()
        self.filter_patcher.start()
        self.auth_key_patcher = mock.patch.dict(config.data, {"auth-key": "chatgpt2api"}, clear=False)
        self.auth_environment_patcher = mock.patch.dict(os.environ, {"CHATGPT2API_AUTH_KEY": "chatgpt2api"}, clear=False)
        self.auth_key_patcher.start()
        self.auth_environment_patcher.start()
        self.addCleanup(self.handler_patcher.stop)
        self.addCleanup(self.filter_patcher.stop)
        self.addCleanup(self.auth_key_patcher.stop)
        self.addCleanup(self.auth_environment_patcher.stop)
        app = FastAPI()
        app.include_router(ai_module.create_router())
        self.client = TestClient(app)

    def test_generation_rejects_unconfigured_gpt_image_25_model(self) -> None:
        with mock.patch.dict(
            config.data,
            {"gpt_image_25_sunburst_upstream_model_name": ""},
            clear=False,
        ):
            response = self.client.post(
                "/v1/images/generations",
                headers=AUTH_HEADERS,
                json={"model": GPT_IMAGE_25_SUNBURST_MODEL, "prompt": "draw", "size": "1024x1024"},
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("not configured", response.text)
        self.assertEqual(self.calls, [])

    def test_generation_validates_gpt_image_25_size_before_handler(self) -> None:
        with mock.patch.dict(
            config.data,
            {"gpt_image_25_sunburst_upstream_model_name": "upstream-sunburst"},
            clear=False,
        ):
            response = self.client.post(
                "/v1/images/generations",
                headers=AUTH_HEADERS,
                json={"model": GPT_IMAGE_25_SUNBURST_MODEL, "prompt": "draw", "size": "1024x1365"},
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("divisible by 16", response.text)
        self.assertEqual(self.calls, [])

    def test_generation_rejects_unimplemented_web_route_parameter(self) -> None:
        response = self.client.post(
            "/v1/images/generations",
            headers=AUTH_HEADERS,
            json={"model": "gpt-image-2", "prompt": "draw", "background": "transparent"},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("background", response.text)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
