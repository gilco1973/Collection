import json, os, sqlite3, tempfile, unittest
from audit import AuditChain, AuditError, GENESIS


class Chain(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:"); self.a = AuditChain(self.conn)

    def test_head_moves_and_verifies(self):
        self.assertEqual(self.a.head(), GENESIS)
        self.a.record(consumer="c", event="admit", decision="allow"); h1 = self.a.head()
        self.a.record(consumer="c", event="decision", tool="t___x", tier="R", decision="allow"); h2 = self.a.head()
        self.assertNotEqual(h1, h2); self.assertEqual(self.a.verify(), 2)
        self.assertEqual(self.a.query(event="decision")[0]["prev"], h1)

    def test_tampering_breaks_the_chain(self):
        self.a.record(consumer="c", event="decision", decision="allow"); self.a.record(consumer="c", event="stop", reason="turn.complete")
        self.conn.execute("UPDATE audit SET body = replace(body, 'allow', 'deny') WHERE seq=1"); self.conn.commit()
        with self.assertRaises(AuditError): self.a.verify()

    def test_query_by_column_and_by_body_field(self):
        self.a.record(consumer="c", event="decision", tool="a___b", session="s1"); self.a.record(consumer="c", event="decision", tool="a___c", session="s2")
        self.assertEqual(len(self.a.query(tool="a___b")), 1); self.assertEqual(self.a.query(session="s2")[0]["tool"], "a___c")

    def test_export_writes_json_lines_with_the_head(self):
        self.a.record(consumer="c", event="admit")
        with tempfile.TemporaryDirectory() as d:
            out = self.a.export(os.path.join(d, "chain.jsonl"))
            lines = open(out["path"]).read().splitlines()
        self.assertEqual(out["records"], 1); self.assertEqual(out["head"], self.a.head()); self.assertEqual(json.loads(lines[0])["event"], "admit"); self.assertFalse(out["signed"])
