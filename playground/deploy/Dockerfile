# The AI Playground as a pipeline step: the command line, standard library only, nothing fetched at build time
# beyond the base image. Build context: the repository root. The bank passes its approved, digest-pinned base with
# --build-arg BASE=<registry>/python:3.11-slim@sha256:<digest>.
#   docker build -f playground/deploy/Dockerfile -t ai-playground .
# Run it from the candidate's directory, as your own user (so the reports it writes into the bind mount are yours and
# the mount is writable), with the candidate mounted at a directory of its own name (the contract check requires the
# directory to be named as the manifest's `name`; `/work` itself would fail that check):
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work/$(basename "$PWD")" -w "/work/$(basename "$PWD")" \
#     -e MODEL_GATEWAY_TOKEN ai-playground run --target t.json --component . --out reports
# The image is Python only: no node, npm, npx or git. A TypeScript candidate's tests and example do not run in it
# (the contract check reports them failed); run those checks outside the container or on an image that adds Node.
# The browser interface listens on loopback only; in a container use the command line, or `--network host` on Linux.
ARG BASE=python:3.11-slim
FROM ${BASE}
# HOME=/tmp: under an arbitrary --user there is no home directory in /etc/passwd; /tmp is writable by any user.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/playground HOME=/tmp
RUN useradd --system --uid 10002 --no-create-home --home-dir /tmp playground
COPY playground/aiplayground /opt/playground/aiplayground
COPY playground/examples /opt/playground/examples
RUN python3 -m compileall -q /opt/playground/aiplayground && chmod -R a+rX /opt/playground
USER playground
ENTRYPOINT ["python3", "-m", "aiplayground"]
CMD ["--help"]
