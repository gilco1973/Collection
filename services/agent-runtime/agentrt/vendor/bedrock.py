"""The Bedrock Converse adapter: the live drop-in for the model gateway's `FakeModel` (governed-action-loop).

`complete(model_id, system, user, max_tokens) -> (text, input_tokens, output_tokens)` is the exact signature the
gateway calls, so nothing above the gateway changes when the live adapter replaces the fake. The call is Bedrock
Converse (`POST /model/{modelId}/converse`) signed with SigV4 from the task role: no API key, no secret in code. An
application inference profile ARN travels as the `modelId`. Token usage is read from the Converse `usage` block and
returned for the session budget. A Bedrock Guardrail may be attached as a second injection and PII signal; the
caller's taint ceiling stays the control.
"""
from __future__ import annotations
import json, urllib.parse
from sigv4 import load_credentials, sign_request


class BedrockConverseError(Exception):
    pass


class BedrockConverseAdapter:
    def __init__(self, http, region: str, endpoint: str | None = None, anthropic_version: str = "bedrock-2023-05-31",
                 guardrail_id: str | None = None, guardrail_version: str | None = None, creds_loader=load_credentials):
        self.http, self.region = http, region
        self.endpoint = (endpoint or f"https://bedrock-runtime.{region}.amazonaws.com").rstrip("/")
        self.anthropic_version = anthropic_version
        self.guardrail_id, self.guardrail_version = guardrail_id, guardrail_version
        self._creds_loader, self._creds = creds_loader, None

    def creds(self):
        if self._creds is None:
            self._creds = self._creds_loader()
        return self._creds

    def complete(self, model_id: str, system: str, user: str, max_tokens: int) -> tuple[str, int, int]:
        url = f"{self.endpoint}/model/{urllib.parse.quote(model_id, safe='')}/converse"
        payload = {
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": int(max_tokens)},
            "additionalModelRequestFields": {"anthropic_version": self.anthropic_version},
        }
        if self.guardrail_id and self.guardrail_version:
            payload["guardrailConfig"] = {"guardrailIdentifier": self.guardrail_id, "guardrailVersion": self.guardrail_version}
        body = json.dumps(payload).encode()
        headers = sign_request(self.creds(), "POST", url, self.region, "bedrock", {"Content-Type": "application/json"}, body)
        _, _, data = self.http.request("POST", url, headers, body)
        try:
            resp = json.loads(data) if data else {}
            text = resp["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError, ValueError, TypeError):
            raise BedrockConverseError("Bedrock Converse returned no usable message")
        usage = resp.get("usage") or {}
        return text, int(usage.get("inputTokens") or 0), int(usage.get("outputTokens") or 0)
