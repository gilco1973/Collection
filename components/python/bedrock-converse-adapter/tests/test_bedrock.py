import json, unittest
from bedrock import BedrockConverseAdapter, BedrockConverseError
from sigv4 import Credentials


class Http:
    def __init__(self, body): self.body, self.calls = body, []
    def request(self, method, url, headers, body):
        self.calls.append((method, url, headers, body)); return 200, {}, self.body


class Adapter(unittest.TestCase):
    def adapter(self, body, **kw):
        return BedrockConverseAdapter(Http(body), "us-east-1", creds_loader=lambda: Credentials("A", "S", "T"), **kw)

    def test_converse_request_shape_and_usage(self):
        a = self.adapter(json.dumps({"output": {"message": {"content": [{"text": "{\"answer\": 1}"}]}}, "usage": {"inputTokens": 12, "outputTokens": 3}}).encode(), guardrail_id="g", guardrail_version="1")
        text, tin, tout = a.complete("arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/example", "system", "user", 500)
        self.assertEqual((text, tin, tout), ('{"answer": 1}', 12, 3))
        method, url, headers, body = a.http.calls[0]
        self.assertEqual(url, "https://bedrock-runtime.us-east-1.amazonaws.com/model/arn%3Aaws%3Abedrock%3Aus-east-1%3A000000000000%3Aapplication-inference-profile%2Fexample/converse")
        self.assertIn("Authorization", headers); self.assertEqual(headers["X-Amz-Security-Token"], "T")
        p = json.loads(body); self.assertEqual(p["inferenceConfig"]["maxTokens"], 500); self.assertEqual(p["system"][0]["text"], "system"); self.assertEqual(p["guardrailConfig"]["guardrailIdentifier"], "g")

    def test_no_usable_message_is_an_error(self):
        with self.assertRaises(BedrockConverseError): self.adapter(b'{"output": {}}').complete("m", "s", "u", 10)
        with self.assertRaises(BedrockConverseError): self.adapter(b"not json").complete("m", "s", "u", 10)

    def test_custom_endpoint(self):
        a = self.adapter(json.dumps({"output": {"message": {"content": [{"text": "ok"}]}}}).encode(), endpoint="https://bedrock.internal.example/")
        a.complete("m", "s", "u", 10); self.assertTrue(a.http.calls[0][1].startswith("https://bedrock.internal.example/model/m/converse"))
