# TODO (2026-10-10 review, section 7 improvements): pin this base image by digest, as the Mumble and Caddy
# images in docker-compose.yml are (O-5): FROM python:3.12-slim@sha256:<digest>.
# Left as a tag because no digest could be resolved offline (no local image, and
# resolving one needs a registry round trip). On a machine with network:
#   docker buildx imagetools inspect python:3.12-slim | head -3
# Use the SAME digest in all three services/*/Dockerfile.
FROM python:3.12-slim

# The board is an engineering surface holding the lane locks, the dispatch
# queue and every agent handoff. Same reasoning as services/exercise: it runs
# as a non-root user whose UID matches the owner of the mounted repository
# clone, or git cannot write the commit it is being asked to make.
#
# Build with --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g) if the
# deploy user is not 1000 (it is 1000 on ms01).
ARG APP_UID=1000
ARG APP_GID=1000

# git and openssh-client are the runtime, not build tooling: the service keeps
# docs/BOARD.md in step with Gitea by pulling and pushing over SSH.
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid ${APP_GID} capvsar \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin capvsar

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/

# The mount point for the capvsar working clone. Created here so a container
# started with no volume fails on a missing board file with a clear message
# rather than on a missing directory.
RUN mkdir -p /repo && chown -R ${APP_UID}:${APP_GID} /repo /app

ENV PYTHONUNBUFFERED=1
USER capvsar
EXPOSE 8770
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8770"]
