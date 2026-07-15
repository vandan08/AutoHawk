FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY autohawk ./autohawk
COPY profile.example.yaml ./
RUN pip install --no-cache-dir .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# All runtime state (profile.yaml, DB, reports, letters) lives in /data
ENV AUTOHAWK_DB=/data/autohawk.db
WORKDIR /data

ENTRYPOINT ["/entrypoint.sh"]
