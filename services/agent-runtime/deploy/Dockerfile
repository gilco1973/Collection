# The agent runtime: one agent of the collection over MCP and a run API. Standard library only.
FROM python:3.11-slim@sha256:PIN_ME_TO_THE_BANK_BASE_IMAGE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENT_ENV=production AGENT_IDENTITY=oidc AGENT_SIGNING=kms AGENT_ENGINE=bedrock AGENT_DB=/var/agent/record.db AGENT_SECRETS=aws AGENT_LISTEN_HOST=0.0.0.0
RUN useradd --system --uid 10002 --create-home agent && mkdir -p /var/agent && chown agent:agent /var/agent
WORKDIR /app
COPY services/agent-runtime/agentrt /app/agentrt
COPY services/agent-runtime/deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/entrypoint.sh && python3 -m compileall -q /app/agentrt
USER agent
VOLUME ["/var/agent"]
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8081/ready', timeout=2).status==200 else 1)"
ENTRYPOINT ["/app/entrypoint.sh"]
