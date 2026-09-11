FROM python:3.12-slim

# X-8: this container ran as root. It holds beacon truth, the auth tokens and
# the exercise database, and it is reachable by every tablet on the LAN.
#
# UID/GID are build args because /data is a BIND MOUNT: the container user must
# match whoever owns that directory on the host, or the console cannot write
# its own database. 1000 is the deploy user on ms01. If you deploy as a
# different user, build with --build-arg APP_UID=$(id -u) --build-arg
# APP_GID=$(id -g).
#
# One-time step on an existing host: Docker created ./services/exercise/data as
# root when the bind mount was first used, so it needs
#     sudo chown -R 1000:1000 services/exercise/data
# before the first non-root start, or the container exits on a read-only
# database. A fresh host that creates the directory itself is already correct.
ARG APP_UID=1000
ARG APP_GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends libopus0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid ${APP_GID} capvsar \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin capvsar

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/

# So a container started with no bind mount still has somewhere to write.
RUN mkdir -p /data && chown -R ${APP_UID}:${APP_GID} /data /app

ENV PYTHONUNBUFFERED=1
USER capvsar
EXPOSE 8700
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8700"]
