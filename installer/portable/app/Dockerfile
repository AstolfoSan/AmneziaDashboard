ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client ca-certificates && rm -rf /var/lib/apt/lists/* && useradd -u 10001 -M -s /usr/sbin/nologin portal
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY panel.py downloads.py portable_settings.py .
COPY static ./static
USER 10001:10001
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","3","--timeout","45","--worker-tmp-dir","/tmp","--no-control-socket","--max-requests","10000","--max-requests-jitter","500","--error-logfile","-","panel:create_app()"]
