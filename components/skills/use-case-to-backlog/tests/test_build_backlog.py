import csv, os, tempfile, unittest
import build_backlog as B


class Backlog(unittest.TestCase):
    def test_builds_index_tickets_epics_csv_and_critical_path(self):
        with tempfile.TemporaryDirectory() as d:
            r = B.build(os.path.join(os.path.dirname(__file__), "..", "example_plan.py"), d)
            self.assertEqual((r["epics"], r["tickets"], r["points"]), (3, 5, 27))
            names = sorted(os.listdir(d))
            self.assertIn("README.md", names); self.assertIn("jira-import.csv", names); self.assertEqual(len(names), 10)
            idx = open(os.path.join(d, "README.md")).read()
            self.assertIn("3 epics · 5 tickets · 27 story points", idx)
            self.assertIn("BOT-11 (The bot on its own core) → BOT-12 (Correlated first read with citations) → BOT-21 (Write tools as W1) → BOT-22", idx)
            t21 = open(os.path.join(d, [n for n in names if n.startswith("BOT-21")][0])).read()
            self.assertIn("| Depends on | [BOT-12]", t21); self.assertIn("| Blocks | [BOT-22]", t21); self.assertIn("- [ ] Replay refused", t21)
            rows = list(csv.DictReader(open(os.path.join(d, "jira-import.csv"))))
            self.assertEqual(len(rows), 8); self.assertEqual(rows[0]["Issue Type"], "Epic"); self.assertEqual([r for r in rows if r["Issue ID"] == "BOT-21"][0]["Blocked by"], "BOT-12")

    def test_slug(self):
        self.assertEqual(B.slug("Meg on its own core: the action loop!"), "meg-on-its-own-core-the-action-loop")
