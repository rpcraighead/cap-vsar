FROM python:3.12-slim

# L-10: this container ran as root while serving a participant-facing app
# through the front door. UID/GID are build args because /app/data and
# /app/charts are BIND MOUNTS: the container user must match whoever owns those
# directories on the host, or the planner cannot write its own database.
# 1000 is the deploy user on ms01. Build with
#   --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)
# if you deploy as a different user.
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid ${APP_GID} planner \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin planner

WORKDIR /app

# gunicorn is pinned in requirements.txt now, not installed loose here.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# So a container started with no bind mount still has somewhere to write.
RUN mkdir -p /app/data /app/charts && chown -R ${APP_UID}:${APP_GID} /app

# Cloud Run sets PORT env var
ENV PORT=8080

USER planner
EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 app:app
