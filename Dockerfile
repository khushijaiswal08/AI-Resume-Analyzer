FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first, from pyproject.toml alone, so this layer stays cached when only
# source code changes. tomllib is in the Python 3.12 standard library.
COPY pyproject.toml README.md LICENSE ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# Then the app itself; its dependencies are already installed.
COPY src ./src
RUN pip install --no-deps .

# Run as an unprivileged user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# GEMINI_API_KEY is optional and must be passed at runtime (docker run -e ...), never baked in.
# Hosts such as Render set PORT; locally it falls back to 8000. WEB_CONCURRENCY (uvicorn
# workers) is read by uvicorn itself; leave it unset on a free single-CPU instance.
CMD ["sh", "-c", "uvicorn resume_analyzer.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
