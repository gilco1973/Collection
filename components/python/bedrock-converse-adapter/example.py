"""Live example: the adapter's request as Bedrock Converse would receive it, against a fake HTTP double; no account needed."""
import json
from bedrock import BedrockConverseAdapter
from sigv4 import Credentials
class Http:
    def request(self, method, url, headers, body):
        print(method, url); print("signed by:", headers["Authorization"].split(",")[0]); print("payload:", json.dumps(json.loads(body))[:160] + "...")
        return 200, {}, json.dumps({"output": {"message": {"content": [{"text": json.dumps({"answer": "cited", "claims": [{"text": "x", "citations": ["s0"]}]})}]}}, "usage": {"inputTokens": 42, "outputTokens": 9}}).encode()
a = BedrockConverseAdapter(Http(), "us-east-1", creds_loader=lambda: Credentials("AKIDEXAMPLE", "secret", "token"), guardrail_id="gr-placeholder", guardrail_version="1")
text, tin, tout = a.complete("arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/example", "You reason and you cite.", "<source id=\"s0\">...</source>", 800)
print("text:", text); print("tokens in/out:", tin, tout)
