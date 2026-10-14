from __future__ import annotations

import base64
import unittest
from unittest import mock

from fastapi import HTTPException

from services.config import config
from services.protocol import openai_v1_response
from services.protocol.conversation import ImageOutput
from utils.helper import GPT_IMAGE_25_SUNBURST_MODEL


class ResponsesImageToolTests(unittest.TestCase):
    def test_tool_model_controls_image_engine_without_changing_response_model(self) -> None:
        first = base64.b64encode(b"first-image").decode("ascii")
        second = base64.b64encode(b"second-image").decode("ascii")
        body = {
            "model": "gpt-5-text",
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "combine these images"},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{first}"},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{second}"},
                ],
            }],
            "tools": [{
                "type": "image_generation",
                "model": GPT_IMAGE_25_SUNBURST_MODEL,
                "action": "edit",
                "size": "1536x1024",
                "quality": "xhigh",
            }],
        }
        captured = {}

        def fake_outputs(request):
            captured["request"] = request
            return iter([
                ImageOutput(
                    kind="result",
                    model=request.model,
                    index=1,
                    total=1,
                    data=[{"b64_json": base64.b64encode(b"generated").decode("ascii")}],
                ),
            ])

        with (
            mock.patch.dict(
                config.data,
                {"gpt_image_25_sunburst_upstream_model_name": "upstream-sunburst"},
                clear=False,
            ),
            mock.patch.object(openai_v1_response, "stream_image_outputs_with_pool", side_effect=fake_outputs),
        ):
            result = openai_v1_response.handle(body)

        self.assertEqual(result["model"], "gpt-5-text")
        self.assertEqual(captured["request"].model, GPT_IMAGE_25_SUNBURST_MODEL)
        self.assertEqual(captured["request"].size, "1536x1024")
        self.assertEqual(captured["request"].quality, "xhigh")
        self.assertEqual(len(captured["request"].images or []), 2)

    def test_edit_action_requires_an_input_image(self) -> None:
        body = {
            "model": "gpt-5-text",
            "input": "edit an image",
            "tools": [{"type": "image_generation", "action": "edit"}],
        }

        with self.assertRaises(HTTPException) as context:
            list(openai_v1_response.response_events(body))

        self.assertIn("requires an input image", str(context.exception.detail))

    def test_generate_action_rejects_input_images(self) -> None:
        encoded = base64.b64encode(b"reference").decode("ascii")
        body = {
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "draw"},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"},
                ],
            }],
            "tools": [{"type": "image_generation", "action": "generate"}],
        }

        with self.assertRaises(HTTPException) as context:
            list(openai_v1_response.response_events(body))

        self.assertIn("generate does not support input images", str(context.exception.detail))

    def test_rejects_unsupported_response_image_parameters(self) -> None:
        body = {
            "input": "draw",
            "previous_response_id": "resp_old",
            "tools": [{"type": "image_generation"}],
        }

        with self.assertRaises(HTTPException) as context:
            list(openai_v1_response.response_events(body))

        self.assertIn("previous_response_id", str(context.exception.detail))

    def test_rejects_file_id_and_mask_image_inputs(self) -> None:
        for input_value, expected in (
            ({"type": "input_image", "file_id": "file_123"}, "file_id"),
            ({"type": "input_image", "input_image_mask": {"file_id": "file_123"}}, "input_image_mask"),
        ):
            with self.subTest(expected=expected), self.assertRaises(HTTPException) as context:
                list(openai_v1_response.response_events({
                    "input": input_value,
                    "tools": [{"type": "image_generation"}],
                }))
            self.assertIn(expected, str(context.exception.detail))


if __name__ == "__main__":
    unittest.main()
