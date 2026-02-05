FROM python:3.12-slim

# Install ffmpeg & yt-dlp runtime deps
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    pip install --no-cache-dir \
        yt-dlp mutagen fastapi uvicorn[standard] \
        sqlmodel jinja2 python-multipart requests
WORKDIR /app
COPY src /app/src
RUN date +%Y-%m-%dT%H:%M:%S%z > /app/src/songripper/build_date.txt
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "main"]
