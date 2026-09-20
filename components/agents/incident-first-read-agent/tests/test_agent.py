"""One test per line of the template's `never`, plus the happy path, all through `example.build()`."""
import unittest
from actionloop.harness import HarnessError, Stop
from agent import catalog_from, load_template, tool_name
import example as X


class Template(unittest.TestCase):
    def test_loads_and_names_everything_an_agent_needs(self):
        t = load_template()
        for k in ("name", "role", "ladder", "stages", "tools", "never", "budget"):
            self.assertIn(k, t)
        self.assertEqual(len(t["never"]), 4)

    def test_the_catalog_is_built_from_the_template(self):
        w = X.build()
        names = {e["name"] for e in w.harness.catalog.payload["tools"]}
        self.assertEqual(names, {tool_name(t) for t in w.template["tools"]})
        decls, ops, shapes = catalog_from(w.template)
        self.assertEqual(set(shapes), names)
        self.assertIn("tickets.comment", ops)


class Run(unittest.TestCase):
    def setUp(self):
        self.w = X.build()
        self.s = self.w.harness.admit(self.w.token("u_dana"), board="checkout", ticket_key="INC-7", budget=X.budget_from(self.w.template))

    def test_reads_thinks_with_citations_and_parks_the_write(self):
        r = self.w.agent.run(self.s, "INC-7", "checkout")
        self.assertIn("4822", r["first_read"]["hypothesis"])
        self.assertTrue(all(c["citations"] for c in r["first_read"]["claims"]))
        self.assertEqual(r["proposal"]["kind"], "rollback")
        self.assertIsNotNone(r["parked"]); self.assertIsNone(r["blocked"])
        self.assertEqual(len(self.w.tickets.comments), 0)  # never: nothing posted without a person

    def test_the_person_confirms_the_exact_call_once(self):
        r = self.w.agent.run(self.s, "INC-7", "checkout")
        with self.assertRaises(HarnessError):
            self.w.harness.confirm(self.s, "u_dana", "0" * 64)  # a different call is not what was parked
        posted = self.w.agent.post(self.s, "u_dana", r["parked"])
        self.assertEqual(posted["data"]["id"], "c1")
        self.assertEqual(self.w.tickets.comments[0]["by"], "u_dana")
        with self.assertRaises(HarnessError):
            self.w.agent.post(self.s, "u_dana", r["parked"])  # the confirmation was consumed

    def test_a_tainted_context_refuses_the_proposal_and_blocks_the_write(self):
        s = self.w.harness.admit(self.w.token("u_dana"), board="checkout", ticket_key="INC-8", budget=X.budget_from(self.w.template))
        r = self.w.agent.run(s, "INC-8", "checkout")
        self.assertTrue(r["tainted"])
        self.assertEqual(r["proposal"]["kind"], "none"); self.assertIn("tainted", r["proposal"]["refused"])
        self.assertEqual(r["blocked"], "taint.forbids_tier"); self.assertIsNone(r["parked"])
        self.assertEqual(len(self.w.tickets.comments), 0)

    def test_nothing_outside_the_template_can_be_called(self):
        with self.assertRaises(Exception):
            self.w.harness.call(self.s, "deploys___rollback", {"run_id": 4822})

    def test_the_model_only_sees_projected_masked_sources(self):
        self.w.tickets.tickets["INC-7"]["body"] += " reporter dana@example.test, card 4111111111111111"
        seen = []
        class Engine:
            def answer(self, stage, ctx, payload=None):
                seen.append(ctx.fenced()); return {"summary": "", "hypothesis": "", "claims": [], "confidence": 0.0, "kind": "none"}
        self.w.agent.engine = Engine()
        self.w.agent.run(self.s, "INC-7", "checkout")
        self.assertNotIn("dana@example.test", seen[0]); self.assertNotIn("4111111111111111", seen[0])
        self.assertIn('<source id="s0"', seen[0])

    def test_the_chain_records_every_step_and_verifies(self):
        r = self.w.agent.run(self.s, "INC-7", "checkout"); self.w.agent.post(self.s, "u_dana", r["parked"]); self.w.harness.end(self.s, "turn.complete")
        self.assertGreaterEqual(self.w.audit.verify(), 6)
