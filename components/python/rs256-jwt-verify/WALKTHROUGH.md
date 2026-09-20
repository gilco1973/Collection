# Walkthrough: rs256-jwt-verify

## 1. Run the live example

```
cd components/python/rs256-jwt-verify && python3 example.py
```

A token minted with a generated key verifies; expired, wrong-audience, `alg: none` and unknown-key tokens are refused with the reason.

## 2. Copy the file

```
cp jwt_rs256.py /path/to/your-service/
```

## 3. Point it at your issuer

```python
fetch = lambda url: json.load(urllib.request.urlopen(url, timeout=5))
jwks = J.Jwks(fetch, J.openid_jwks_url(fetch, ISSUER + "/.well-known/openid-configuration"))
```

Keys are cached by `kid`; an unknown `kid` refreshes once and then refuses.

## 4. Verify on every route but health

```python
claims = J.verify(bearer, jwks, issuers=(ISSUER,), audiences=(MY_AUDIENCE,))
```

Hand `claims["sub"]` and the roles claim to your identity layer. A 401 is the only answer to a bad token; never fall through.

## 5. Prove it

```
python3 -m unittest discover -s tests -t . -v
```

The tests mint tokens with a generated 1024-bit key; production never signs here.
