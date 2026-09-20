"""Live example: sign a Secrets Manager call with fixed credentials and show the headers; no network."""
import datetime as dt, json
from sigv4 import AwsJson, Credentials, sign_request
creds = Credentials("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "SESSION-TOKEN-PLACEHOLDER")
body = json.dumps({"SecretId": "app/pagerduty-api"}).encode()
h = sign_request(creds, "POST", "https://secretsmanager.us-east-1.amazonaws.com/", "us-east-1", "secretsmanager",
                 {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "secretsmanager.GetSecretValue"}, body, dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc))
for k in ("X-Amz-Date", "X-Amz-Content-Sha256", "Authorization"): print(f"{k}: {h[k][:110]}")
class FakeHttp:
    def request(self, method, url, headers, body): print("POST", url, "signed:", headers["Authorization"][:40] + "..."); return 200, {}, b'{"SecretString": "value-from-the-vault"}'
print("secret:", AwsJson(FakeHttp(), "us-east-1", creds_loader=lambda: creds).call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/pagerduty-api"})["SecretString"])
