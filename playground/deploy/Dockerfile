# The AI Playground as a pipeline step: the command line, standard library only, nothing fetched at build time
# beyond the base image. Build context: the repository root. The bank passes its approved, digest-pinned base with
# --build-arg BASE=<registry>/python:3.11-slim@sha256:<digest>.
#   docker build -f playground/deploy/Dockerfile -t ai-playground .
#   docker run --rm -v "$PWD:/work" -w /work -e MODEL_GATEWAY_TOKEN ai-playground run --target t.json --component . --out reports
# The browser interface listens on loopback only; in a container use the command line, or `--network host` on Linux.
ARG BASE=python:3.11-slim
FROM ${BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/playground
RUN useradd --system --uid 10002 --create-home playground
COPY playground/aiplayground /opt/playground/aiplayground
COPY playground/examples /opt/playground/examples
RUN python3 -m compileall -q /opt/playground/aiplayground
USER playground
ENTRYPOINT ["python3", "-m", "aiplayground"]
CMD ["--help"]
