# hub-api and the hub, one image. Standard library only: no pip, no network at build time beyond the base image.
# Build context: the repository root (the hub's dist/ is built beforehand with its production env; see deploy/README.md).
FROM python:3.11-slim@sha256:PIN_ME_TO_THE_BANK_BASE_IMAGE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HUB_ENV=production HUB_AUTH=oidc HUB_DB=/var/hub/hub.db HUB_STATIC_DIR=/app/hub-dist HUB_SECRETS=aws HUB_LISTEN_HOST=0.0.0.0
RUN useradd --system --uid 10001 --create-home hub && mkdir -p /var/hub /app/config && chown hub:hub /var/hub
WORKDIR /app
COPY services/hub-api/hubapi /app/hubapi
COPY services/hub-api/data /app/data
COPY services/hub-api/deploy/entrypoint.sh /app/entrypoint.sh
COPY hub/dist /app/hub-dist
RUN chmod 0555 /app/entrypoint.sh && python3 -m compileall -q /app/hubapi
USER hub
VOLUME ["/var/hub"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=2).status==200 else 1)"
ENTRYPOINT ["/app/entrypoint.sh"]
