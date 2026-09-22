"""The AI Playground: a test bench for any AI solution on its way into the collection.

An engineer points it at a solution (a chat API, an agent, a Python function, a command, an MCP tool server) and at
the candidate component's directory; it runs the collection's contract check, a library of adversarial and
robustness probes, and the tester's own cases, and writes a report with a verdict. An AI security engineer reads
the report, triages what needs a person, and cites it in the sign-off note. The report is evidence, never a sign-off.
"""
__version__ = "1.0.0"
