FROM python:3.12-slim

# Install ffmpeg & yt-dlp runtime deps
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    pip install --no-cache-dir \
        yt-dlp mutagen fastapi uvicorn[standard] \
        sqlmodel jinja2 python-multipart requests
WORKDIR /app
COPY src /app/src
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "main"]
