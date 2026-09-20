# Builds the console, then packages the API + console with the knowledge base tree.
# Base images are tag-pinned; pinning their digests is an operator step (deploy/RUNBOOK.md,
# "Upgrade") because the build here has no registry access to resolve them.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/index.html web/vite.config.ts web/tsconfig.json web/tailwind.config.js web/postcss.config.js ./
COPY web/src ./src
COPY web/public ./public
RUN npm run build

FROM python:3.11-slim
# Release metadata: the version is the package version (pyproject); pass the repository URL at
# build time (`--build-arg IMAGE_SOURCE=<repo url>`) so the label never hard-codes a host here.
ARG IMAGE_VERSION=0.1.0
ARG IMAGE_SOURCE=""
LABEL org.opencontainers.image.title="knowledge-base" \
      org.opencontainers.image.description="Organisational AI knowledge base: API, console and the librarian agent in one process" \
      org.opencontainers.image.source="${IMAGE_SOURCE}" \
      org.opencontainers.image.version="${IMAGE_VERSION}"
# HOME is explicit: the Agent SDK's bundled CLI writes under it, and at runtime the home directory
# is a tmpfs/emptyDir because the root filesystem is mounted read-only.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 POETRY_VIRTUALENVS_CREATE=false HOME=/home/librarian
RUN pip install --no-cache-dir poetry==2.1.3 && useradd --create-home --uid 10001 librarian
WORKDIR /srv/knowledge-base
COPY pyproject.toml poetry.lock README.md ./
COPY kb_librarian ./kb_librarian
RUN poetry install --only main --no-interaction --no-ansi
COPY kb.config.yaml ./
COPY docs ./docs
COPY --from=web /web/dist ./web/dist
COPY deploy/serve.py ./deploy/serve.py
# `.librarian/` exists as the mount point for the state volume (the only writable path besides
# /tmp and $HOME once the root filesystem is read-only); the tree is owned by the runtime user.
RUN mkdir -p .librarian && chown -R librarian:librarian /srv/knowledge-base
USER librarian
EXPOSE 8765
# Liveness from inside the container: the slim image has no curl, urllib is enough (a non-200
# raises, which exits 1). Readiness lives at /api/health/ready and is the ingress's concern.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"]
# Runtime secrets come from the environment (secret manager); nothing is baked in.
# The image is dry-run only unless `docs/` is mounted read-write (see deploy/compose.yaml).
CMD ["python", "deploy/serve.py"]
