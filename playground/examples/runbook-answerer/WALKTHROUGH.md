# Walkthrough: runbook-answerer

1. Run the live example: `python3 example.py`. The first answer names `runbook-ach-late-file §3`; the second refuses.
2. Run the tests: `python3 -m unittest discover -s tests -t .`.
3. Put it through the playground from the `playground/` directory:
   `python3 -m aiplayground run --target examples/python-function.json --component examples/runbook-answerer --suite examples/runbook-suite.json`.
4. Read the report it prints the path of; the verdict should be `clear`.
5. Copy `answerer.py` into your project and call `answer(question, context=extract)`.
