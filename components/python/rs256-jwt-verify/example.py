"""Live example: mint a token with a generated key (tests only), verify it, then show four bad tokens being refused."""
import json, sys, time
sys.path.insert(0, "tests")
import jwt_rs256 as J
from _rsa import keypair
n, e, d = keypair(seed=11)
jwks = J.Jwks(lambda url: {"keys": [{"kty": "RSA", "kid": "k1", "use": "sig", "n": J.b64url_encode(n.to_bytes((n.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(e.to_bytes(3, "big"))}]}, "https://issuer.example/jwks")
def mint(payload, alg="RS256", kid="k1"):
    h = J.b64url_encode(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode()); p = J.b64url_encode(json.dumps(payload).encode())
    return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(n, d, (h + "." + p).encode()))
now = int(time.time()); good = {"iss": "https://issuer.example", "aud": "my-app", "sub": "u_dana", "exp": now + 300}
print("good token ->", J.verify(mint(good), jwks, ("https://issuer.example",), ("my-app",))["sub"])
for label, tok in [("expired", mint(good | {"exp": now - 120})), ("wrong audience", mint(good | {"aud": "other"})), ("alg none", mint(good, alg="none")), ("unknown key", mint(good, kid="k9"))]:
    try: J.verify(tok, jwks, ("https://issuer.example",), ("my-app",)); print(label, "-> accepted (never)")
    except J.JwtError as err: print(f"{label} -> refused: {err}")
