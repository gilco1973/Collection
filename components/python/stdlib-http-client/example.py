"""Live example: a client that retries a flaky upstream, never keeps a credential in its recording, and strips the query from an error."""
from httpclient import Http, HttpError, RecordingTransport
calls = {"n": 0}
def flaky(method, url, body):
    calls["n"] += 1
    return (503, {"error": "busy"}) if calls["n"] < 3 else (200, {"incidents": [{"id": "PD-1"}]})
t = RecordingTransport({("GET", "https://api.example/incidents"): flaky, ("GET", "https://api.example/forbidden"): (403, {"error": "no"})})
http = Http(t, retries=3, sleep=lambda s: print(f"  backoff {s}s"))
print("result:", http.json("GET", "https://api.example/incidents?token=SECRET", {"Authorization": "Token SECRET"}), "after", calls["n"], "attempts")
print("recorded header:", t.calls[0]["headers"]["Authorization"])
try:
    http.json("GET", "https://api.example/forbidden?api_key=SECRET")
except HttpError as e:
    print("error message:", e, "| carries the key:", "SECRET" in str(e))
