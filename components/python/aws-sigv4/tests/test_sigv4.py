import datetime as dt, json, unittest
import sigv4


class SigV4(unittest.TestCase):
    def test_signing_key_matches_documented_vector(self):
        k = sigv4.signing_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20150830", "us-east-1", "iam")
        self.assertEqual(k.hex(), "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9")

    def test_signed_request_headers(self):
        creds = sigv4.Credentials("AKIDEXAMPLE", "secret", "tok")
        h = sigv4.sign_request(creds, "POST", "https://logs.us-east-1.amazonaws.com/", "us-east-1", "logs", {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "Logs_20140328.FilterLogEvents"}, b"{}", dt.datetime(2026, 9, 17, 12, 0, 0, tzinfo=dt.timezone.utc))
        self.assertTrue(h["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20260917/us-east-1/logs/aws4_request, SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date;x-amz-security-token;x-amz-target, Signature="))
        self.assertEqual(h["X-Amz-Security-Token"], "tok"); self.assertEqual(h["X-Amz-Date"], "20260917T120000Z")

    def test_credentials_from_task_role_then_environment(self):
        creds = sigv4.load_credentials(http_get=lambda u: json.dumps({"AccessKeyId": "A", "SecretAccessKey": "S", "Token": "T"})) if __import__("os").environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") else None
        import os
        os.environ["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"] = "/v2/credentials/x"
        try:
            creds = sigv4.load_credentials(http_get=lambda u: json.dumps({"AccessKeyId": "A", "SecretAccessKey": "S", "Token": "T"}))
            self.assertEqual((creds.access_key, creds.session_token), ("A", "T"))
        finally:
            del os.environ["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"]
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_CONTAINER_CREDENTIALS_FULL_URI"):
            os.environ.pop(k, None)
        with self.assertRaises(RuntimeError): sigv4.load_credentials()

    def test_aws_json_call_is_signed_per_request(self):
        seen = []
        class Http:
            def request(self, method, url, headers, body):
                seen.append((method, url, headers, body)); return 200, {}, b'{"SecretString": "v"}'
        aws = sigv4.AwsJson(Http(), "us-east-1", creds_loader=lambda: sigv4.Credentials("A", "S"))
        r = aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/key"})
        self.assertEqual(r["SecretString"], "v"); self.assertIn("Authorization", seen[0][2]); self.assertEqual(seen[0][2]["X-Amz-Target"], "secretsmanager.GetSecretValue")

    def test_task_role_credentials_reload_before_they_expire(self):
        soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        later = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        import os
        os.environ["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"] = "/v2/credentials/x"
        try:
            c = sigv4.load_credentials(http_get=lambda u: json.dumps({"AccessKeyId": "A1", "SecretAccessKey": "S", "Token": "T", "Expiration": soon}))
            self.assertTrue(c.expiring(), "two minutes from expiry counts as expiring")
            c2 = sigv4.load_credentials(http_get=lambda u: json.dumps({"AccessKeyId": "A2", "SecretAccessKey": "S", "Token": "T", "Expiration": later}))
            self.assertFalse(c2.expiring())
        finally:
            del os.environ["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"]
        self.assertFalse(sigv4.Credentials("A", "S").expiring(), "keys without an expiry are kept")
        loads = iter([c, c2])
        class Http:
            def request(self, method, url, headers, body): return 200, {}, b"{}"
        aws = sigv4.AwsJson(Http(), "us-east-1", creds_loader=lambda: next(loads))
        aws.call("secretsmanager", "secretsmanager", "x", {}); aws.call("secretsmanager", "secretsmanager", "x", {})
        self.assertEqual(aws.creds().access_key, "A2", "the expiring credentials were replaced on the next call")

    def test_an_error_document_is_an_error_and_throttling_is_retried(self):
        answers = iter([(400, b'{"__type":"ExpiredTokenException","message":"The security token included in the request is expired"}'),
                        (429, b'{"__type":"ThrottlingException"}'), (200, b'{"SecretString":"v"}'),
                        (500, b''), (500, b''), (500, b'')])
        class Http:
            def request(self, method, url, headers, body):
                s, b = next(answers); return s, {}, b
        slept = []
        aws = sigv4.AwsJson(Http(), "us-east-1", creds_loader=lambda: sigv4.Credentials("A", "S"), retries=2, sleep=slept.append)
        with self.assertRaises(sigv4.AwsError) as cm:
            aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/key"})
        self.assertEqual((cm.exception.type, cm.exception.status, cm.exception.expired), ("ExpiredTokenException", 400, True)); self.assertNotIn("security token", str(cm.exception))
        self.assertEqual(aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/key"}), {"SecretString": "v"}); self.assertEqual(slept, [0.5])
        with self.assertRaises(sigv4.AwsError) as cm:
            aws.call("kms", "kms", "TrentService.Sign", {})
        self.assertEqual((cm.exception.status, cm.exception.retryable), (500, True)); self.assertEqual(len(slept), 3)
