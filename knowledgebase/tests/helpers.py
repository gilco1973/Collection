"""Test helpers."""

import json


def payload(result: dict):
    """Extract the JSON payload from a data_result envelope."""
    text = result["content"][0]["text"]
    start, end = text.index("<kb-data>") + len("<kb-data>"), text.index("</kb-data>")
    return json.loads(text[start:end])
