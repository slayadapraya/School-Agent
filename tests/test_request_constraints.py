"""Explicit user requirements survive corrections and reject incompatible code."""

import io
import json
import unittest
from unittest.mock import patch
from app import request_constraints as c, server as s, preferences, artifacts


class RequestConstraints(unittest.TestCase):
    def test_actual_misspelling_and_repeated_correction(self):
        for question in (
            "Write a quick script that doesn tuse ultranalytics",
            "Write a script that doesn't involve ultralytics",
            "Use YOLO without Ultralytics",
            "Do not use ultralytics",
        ):
            contract = c.build(question, [])
            self.assertEqual(contract["excluded_dependencies"], ["ultralytics"])
            bad = "```python filename=no_ultralytics.py\nfrom ultralytics import YOLO\n```"
            self.assertEqual(c.violation(bad, contract), ["ultralytics"])

    def test_followup_inherits_but_new_task_and_explicit_change_do_not(self):
        history = [
            {"role": "user", "content": "Write a detector without ultralytics"},
            {
                "role": "assistant",
                "content": "```python\nfrom ultralytics import YOLO\n```",
            },
        ]
        self.assertEqual(
            c.build("Also make it save video", history)["excluded_dependencies"],
            ["ultralytics"],
        )
        self.assertEqual(
            c.build("Explain the water cycle", history)["excluded_dependencies"], []
        )
        self.assertEqual(
            c.build("Change it to use ultralytics instead", history)[
                "excluded_dependencies"
            ],
            [],
        )
        self.assertEqual(
            c.build("Change it but do not use ultralytics", history)[
                "excluded_dependencies"
            ],
            ["ultralytics"],
        )

    def test_executable_dependencies_not_mentions_filenames_or_quoted_sources(self):
        contract = c.build("Avoid ultralytics", [])
        for bad in (
            "```python\nimport os, ultralytics\n```",
            "```bash\npython -m pip install opencv-python ultralytics==1.0\n```",
            '```js\nconst y = require("ultralytics");\n```',
            "```text filename=requirements.txt\nultralytics>=1\n```",
        ):
            self.assertEqual(c.violation(bad, contract), ["ultralytics"])
        good = 'This avoids Ultralytics.\n```python filename=no_ultralytics.py\nimport cv2\nnet = cv2.dnn.readNetFromONNX("model.onnx")\n```'
        self.assertEqual(c.violation(good, contract), [])
        self.assertEqual(
            c.excluded("Read this example:\n```text\ndo not use ultralytics\n```"),
            set(),
        )
        self.assertEqual(
            c.violation(
                "```python\nimport cv2\n```", c.build("Without opencv-python", [])
            ),
            ["cv2"],
        )

    def response(self, answer):
        class Response(io.BytesIO):
            headers = {"Content-Type": "application/json"}

        return Response(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"answer": answer, "source_ids": []}
                                )
                            }
                        }
                    ]
                }
            ).encode()
        )

    def generate(self, replies):
        context = {
            "instance": "test",
            "transport": "chat",
            "generate_files": True,
            "request_message": "Write a detector without ultralytics",
            "request_constraints": c.build("Write a detector without ultralytics", []),
        }
        token = preferences.MODEL_CONTEXT.set(context)
        try:
            with (
                patch.object(
                    s,
                    "settings",
                    return_value={
                        "model_url": "http://127.0.0.1:1234/v1",
                        "model": "test",
                    },
                ),
                patch.object(
                    s,
                    "urlopen",
                    side_effect=[self.response(reply) for reply in replies],
                ) as network,
            ):
                value = s.model_json(
                    [
                        {
                            "role": "system",
                            "content": "Keep account permissions and required JSON format.",
                        },
                        {"role": "user", "content": context["request_message"]},
                    ],
                    1500,
                )
            return value, network
        finally:
            preferences.MODEL_CONTEXT.reset(token)

    def test_bad_dependency_is_repaired_once_with_original_policy(self):
        bad = "```python\nfrom ultralytics import YOLO\n```"
        good = '```python\nimport cv2\nnet=cv2.dnn.readNetFromONNX("model.onnx")\n```'
        value, network = self.generate([bad, good])
        self.assertEqual(value["answer"], good)
        self.assertEqual(network.call_count, 2)
        retry = json.loads(network.call_args.args[0].data)["messages"]
        self.assertIn("Keep account permissions", retry[0]["content"])
        self.assertIn("explicit requirements", " ".join(m["content"] for m in retry))
        self.assertEqual(
            json.loads(retry[-1]["content"])["current_request"],
            "Write a detector without ultralytics",
        )

    def test_repeated_violation_never_becomes_downloadable_file(self):
        bad = "```python\nfrom ultralytics import YOLO\n```"
        value, network = self.generate([bad, bad])
        self.assertIn("haven’t included", value["answer"])
        self.assertEqual(artifacts.extract(value["answer"]), [])
        self.assertEqual(network.call_count, 2)

    def test_compliant_answer_does_not_add_inference_calls(self):
        good = "```python\nimport cv2\n```"
        value, network = self.generate([good])
        self.assertEqual(value["answer"], good)
        self.assertEqual(network.call_count, 1)
