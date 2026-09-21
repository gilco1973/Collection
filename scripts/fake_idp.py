"""A stand-in OpenID Connect provider for proving the real sign-in path end to end, on the standard library.

    python3 scripts/fake_idp.py --port 9443 --cert cert.pem --key key.pem [--audience hub-api] [--client hub-web]

It speaks what the hub and hub-api need from a bank's provider and nothing more: discovery, a JWKS, the
authorization endpoint (Authorization Code with PKCE S256, `prompt=none` for silent renew against its own
session cookie), the token endpoint (RS256 access and id tokens), userinfo, and end-session. The people it knows
are query-selectable so a test can sign in as a lead, an AI security engineer, an employee, or someone whose
directory has too many groups to list (the overage a real provider signals with `_claim_names`). Nothing here is
a credential: the key pair is generated on start and thrown away.
"""
from __future__ import annotations
import argparse, hashlib, http.server, json, os, secrets, ssl, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "services", "hub-api"))
from hubapi.vendor import jwt_rs256 as J  # noqa: E402
from tests._rsa import keypair  # noqa: E402

PEOPLE = {
    "lead": {"sub": "sub-lead", "oid": "11111111-0000-0000-0000-000000000001", "name": "Gil Klainert", "preferred_username": "gil.klainert@bank.example", "groups": ["GROUP_ID_PAYMENTS_OPS_LEADS"]},
    "security": {"sub": "sub-sec", "oid": "11111111-0000-0000-0000-000000000002", "name": "Maya Chen", "preferred_username": "maya.chen@bank.example", "groups": ["GROUP_ID_AI_SECURITY"]},
    "employee": {"sub": "sub-emp", "oid": "11111111-0000-0000-0000-000000000003", "name": "Sam Okafor", "upn": "sam.okafor@bank.example", "groups": []},
    "overage": {"sub": "sub-many", "oid": "11111111-0000-0000-0000-000000000004", "name": "Many Groups", "preferred_username": "many.groups@bank.example",
                "_claim_names": {"groups": "src1"}, "_claim_sources": {"src1": {"endpoint": "https://graph.example/users/x/getMemberObjects"}}},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9443); ap.add_argument("--cert", required=True); ap.add_argument("--key", required=True)
    ap.add_argument("--audience", default="hub-api"); ap.add_argument("--client", default="hub-web"); ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    N, E, D = keypair(1024, seed=int(time.time()) % 100000)
    issuer = f"https://{a.host}:{a.port}"
    kid = "fake-" + secrets.token_hex(3)
    codes: dict[str, dict] = {}
    sessions: dict[str, str] = {}

    def jwt(claims: dict) -> str:
        h = J.b64url_encode(json.dumps({"alg": "RS256", "kid": kid, "typ": "JWT"}).encode())
        p = J.b64url_encode(json.dumps(claims).encode())
        return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(N, D, (h + "." + p).encode()))

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if os.environ.get("IDP_LOG"): sys.stderr.write("idp %s %s\n" % (self.command, self.path.split("?")[0])); sys.stderr.flush()

        def _send(self, status, body, ctype="application/json", headers=None):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*"); self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(raw)

        def _redirect(self, url):
            self.send_response(302); self.send_header("Location", url); self.send_header("Content-Length", "0"); self.end_headers()

        def _cookie(self):
            c = self.headers.get("Cookie") or ""
            for part in c.split(";"):
                k, _, v = part.strip().partition("=")
                if k == "idp_session": return v
            return ""

        def do_OPTIONS(self):
            self.send_response(204); self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
            self.send_header("Access-Control-Allow-Headers", "authorization, content-type"); self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS"); self.send_header("Content-Length", "0"); self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query))
            if u.path == "/.well-known/openid-configuration":
                return self._send(200, {"issuer": issuer, "authorization_endpoint": f"{issuer}/authorize", "token_endpoint": f"{issuer}/token", "userinfo_endpoint": f"{issuer}/userinfo",
                                        "jwks_uri": f"{issuer}/keys", "end_session_endpoint": f"{issuer}/endsession", "response_types_supported": ["code"],
                                        "code_challenge_methods_supported": ["S256"], "id_token_signing_alg_values_supported": ["RS256"], "scopes_supported": ["openid", "profile", "email", a.audience]})
            if u.path == "/keys":
                return self._send(200, {"keys": [{"kty": "RSA", "use": "sig", "kid": kid, "n": J.b64url_encode(N.to_bytes((N.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(E.to_bytes(3, "big"))}]})
            if u.path == "/authorize":
                if q.get("client_id") != a.client or q.get("response_type") != "code" or q.get("code_challenge_method") != "S256":
                    return self._send(400, {"error": "invalid_request"})
                who = q.get("persona") or self._cookie()
                sep = "&" if "?" in q.get("redirect_uri", "") else "?"
                if q.get("prompt") == "none" and not who:
                    return self._redirect(f"{q['redirect_uri']}{sep}error=login_required&state={urllib.parse.quote(q.get('state', ''))}")
                if not who:
                    who = "lead"  # the person the test did not choose: the default sign-in
                if who not in PEOPLE:
                    return self._send(400, {"error": "unknown_persona"})
                code = secrets.token_urlsafe(24)
                codes[code] = {"who": who, "challenge": q["code_challenge"], "redirect_uri": q["redirect_uri"], "nonce": q.get("nonce", ""), "scope": q.get("scope", "")}
                headers = {} if q.get("prompt") == "none" else {"Set-Cookie": f"idp_session={who}; Path=/; Secure; SameSite=None"}
                self.send_response(302); self.send_header("Location", f"{q['redirect_uri']}{sep}code={code}&state={urllib.parse.quote(q.get('state', ''))}")
                for k, v in headers.items(): self.send_header(k, v)
                self.send_header("Content-Length", "0"); self.end_headers(); return
            if u.path == "/userinfo":
                tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
                try:
                    claims = J.decode_unverified(tok)[1]
                except Exception:
                    return self._send(401, {"error": "invalid_token"})
                who = PEOPLE.get(sessions.get(claims.get("sub", ""), ""), {})
                return self._send(200, {k: v for k, v in who.items() if k in ("sub", "name", "preferred_username", "upn", "groups")} or {"sub": claims.get("sub")})
            if u.path == "/endsession":
                # End the provider's own session too, or the next silent renew would sign the person straight back in.
                self.send_response(302); self.send_header("Location", q.get("post_logout_redirect_uri", "/") or "/")
                self.send_header("Set-Cookie", "idp_session=; Path=/; Max-Age=0; Secure; SameSite=None"); self.send_header("Content-Length", "0"); self.end_headers(); return
            return self._send(404, {"error": "not_found"})

        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            form = dict(urllib.parse.parse_qsl(body))
            if u.path != "/token": return self._send(404, {"error": "not_found"})
            if form.get("grant_type") != "authorization_code": return self._send(400, {"error": "unsupported_grant_type"})
            c = codes.pop(form.get("code", ""), None)
            if not c: return self._send(400, {"error": "invalid_grant"})
            expect = J.b64url_encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
            if expect != c["challenge"] or form.get("client_id") != a.client or form.get("redirect_uri") != c["redirect_uri"]:
                return self._send(400, {"error": "invalid_grant", "error_description": "pkce or client mismatch"})
            who = PEOPLE[c["who"]]; now = int(time.time())
            sessions[who["sub"]] = c["who"]
            base = {"iss": issuer, "sub": who["sub"], "iat": now, "nbf": now - 5, "exp": now + 600}
            access = jwt({**base, "aud": a.audience, "scp": c["scope"], **{k: v for k, v in who.items() if k != "sub"}})
            idt = jwt({**base, "aud": a.client, "nonce": c["nonce"], "name": who["name"], "preferred_username": who.get("preferred_username") or who.get("upn")})
            return self._send(200, {"token_type": "Bearer", "access_token": access, "id_token": idt, "expires_in": 600, "scope": c["scope"]})

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(a.cert, a.key)
    httpd = http.server.ThreadingHTTPServer((a.host, a.port), H)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"fake idp listening issuer={issuer} kid={kid}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
