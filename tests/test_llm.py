import json
import unittest

from agent_runtime.llm import _api_to_response


class LLMResponseTests(unittest.TestCase):
    def test_tool_call_arguments_are_parsed_into_dict(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "parse-1",
                                "type": "function",
                                "function": {
                                    "name": "calculator",
                                    "arguments": json.dumps(
                                        {"expression": "1 + 2"}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        }

        response = _api_to_response(payload)

        self.assertIsNone(response.content)
        self.assertEqual(len(response.tool_calls), 1)

        call = response.tool_calls[0]
        self.assertEqual(call.id, "parse-1")
        self.assertEqual(call.name, "calculator")
        self.assertEqual(call.arguments, {"expression": "1 + 2"})

    def test_invalid_tool_arguments_are_rejected(self):
        cases = [
            ('{"expression":', "Invalid JSON arguments"),
            ("[]", "Tool arguments must be an object"),
            ("null", "Tool arguments must be an object"),
        ]

        for arguments_text, expected_error in cases:
            with self.subTest(arguments=arguments_text):
                payload = {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "invalid-parse-1",
                                        "type": "function",
                                        "function": {
                                            "name": "calculator",
                                            "arguments": arguments_text,
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }

                with self.assertRaisesRegex(ValueError, expected_error):
                    _api_to_response(payload)

    def test_empty_choices_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "LLM response has no choices",
        ):
            _api_to_response({"choices": []})