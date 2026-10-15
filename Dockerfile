FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home assistant
WORKDIR /app
COPY land_assistant ./land_assistant
COPY examples ./examples
RUN mkdir /app/data && chown assistant:assistant /app/data
USER assistant
VOLUME ["/app/data"]
CMD ["python", "-m", "land_assistant", "bot"]
