FROM python:3.13-alpine

RUN adduser -D -u 1001 appuser

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY vits_tts_hf2api/ vits_tts_hf2api/

USER appuser
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

CMD ["python", "-m", "vits_tts_hf2api"]
