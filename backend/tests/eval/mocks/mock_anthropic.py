"""
Mock Anthropic client for eval suite.

Returns structurally valid responses that match the shape expected by
tasks/p12_task.py and tasks/p12b_task.py:
  response.content[0].text  -> JSON string
  response.usage.input_tokens
  response.usage.output_tokens
  response.usage.cache_read_input_tokens  (optional attr)
"""

import json


class MockUsage:
    def __init__(self):
        self.input_tokens = 500
        self.output_tokens = 300
        self.cache_read_input_tokens = 0


class MockContentBlock:
    def __init__(self, text: str):
        self.text = text


class MockResponse:
    def __init__(self, text: str):
        self.content = [MockContentBlock(text)]
        self.usage = MockUsage()


class MockMessages:
    def __init__(self, call_responses: list):
        """
        call_responses: list of dicts to return as JSON text, in call order.
        After exhausting the list, the last entry is repeated.
        """
        self._responses = call_responses
        self._call_index = 0

    def create(self, **kwargs) -> MockResponse:
        idx = min(self._call_index, len(self._responses) - 1)
        payload = self._responses[idx]
        self._call_index += 1
        return MockResponse(json.dumps(payload, ensure_ascii=False))


class MockAnthropic:
    """Drop-in replacement for anthropic.Anthropic for eval purposes.

    Usage:
        mock = MockAnthropic(p12_response_dict, p12b_response_dict)
        # patch anthropic.Anthropic to return mock

    The constructor accepts per-call response dicts in order.
    """

    def __init__(self, *call_responses):
        if not call_responses:
            call_responses = [_default_p12_response()]
        self.messages = MockMessages(list(call_responses))

    # Make the class itself callable so it can replace anthropic.Anthropic(api_key=...)
    def __call__(self, *args, **kwargs):
        return self


def build_p12_response(post_text: str) -> dict:
    """Build a valid P12 output dict for a given post text."""
    return {
        "post": post_text,
        "alternative_opener": [
            "Noch ein anderer Einstieg fuer diesen Post.",
        ],
        "design_notizen": "Post folgt dem direkten Ton des Voice-Profils.",
        "ki_signal_check": {
            "gefunden": [],
            "bewertet": "keine KI-Signale gefunden",
        },
        "potenzielle_schwaechen": [],
    }


def build_p12b_response(post_text: str) -> dict:
    """Build a valid P12b output dict (decision=optimiert) for a given post text."""
    return {
        "decision": "optimiert",
        "optimierter_post": post_text,
        "begruendung": "Post entspricht dem Voice-Profil, keine Aenderungen noetig.",
    }


def _default_p12_response() -> dict:
    return build_p12_response("Das ist ein generischer Test-Post fuer die Eval-Suite.")
