"""Live example: a record that cannot be quietly edited. Writes three events, verifies, exports, then tampers and shows the failure."""
import sqlite3, tempfile, os
from audit import AuditChain, AuditError

conn = sqlite3.connect(":memory:"); chain = AuditChain(conn)
chain.record(consumer="agent:helper", event="admit", session="ses_1", decision="allow")
chain.record(consumer="agent:helper", event="intent", session="ses_1", tool="tickets___comment", tier="W1")
chain.record(consumer="agent:helper", event="decision", session="ses_1", tool="tickets___comment", tier="W1", decision="allow")
print("head:", chain.head()[:24] + "...")
print("verified records:", chain.verify())
with tempfile.TemporaryDirectory() as d:
    out = chain.export(os.path.join(d, "evidence.jsonl")); print("export:", out["records"], "records, signed =", out["signed"])
conn.execute("UPDATE audit SET body = replace(body, '\"allow\"', '\"deny\"') WHERE seq = 3"); conn.commit()
try:
    chain.verify(); print("tampering went unnoticed (this line never prints)")
except AuditError as e:
    print("after tampering with record 3:", e)
