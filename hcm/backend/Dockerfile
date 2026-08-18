FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements.lock is the pip-compile output of requirements.txt (pinned,
# reproducible); regenerate with `pip-compile --strip-extras
# --output-file requirements.lock requirements.txt` after editing requirements.txt.
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

RUN python manage.py collectstatic --noinput || true

# media/ is a named volume in docker-compose (uploaded policy documents,
# performance evidence). Create it here, owned by appuser, so Docker seeds a
# fresh named volume with that ownership — otherwise the volume is root-owned
# and the non-root app can't write uploads (found in H1: seed_demo_data failed).
RUN useradd --create-home --shell /bin/false appuser \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
