# SongRipper

SongRipper is a small FastAPI service that converts YouTube playlists into tagged MP3 files.
It downloads each video, extracts the audio, fetches metadata such as artist, title and album
information and writes ID3 tags with cover art.  Tracks are placed in a staging directory until
approved, after which they are moved to the final music library.

## Running with Docker

Use the provided `docker-compose.yml` to build and run the service.  By default it exposes the
web UI on port `5423` and stores data under `./data`.  The `NAS_PATH` volume should point to your
music collection.

```bash
docker compose up --build
```

The web UI allows you to submit a YouTube playlist URL and to approve all staged tracks.

## Environment Variables

- `DATA_DIR` – directory where temporary downloads are stored (default: `/data`).
- `NAS_PATH` – destination path for approved tracks (default: `/music`).

These can be customised in `docker-compose.yml` or when running the container manually.

## Development

Install the requirements and start the API with Uvicorn:

```bash
pip install -r requirements.txt
python -m main
```

The API will be available at `http://localhost:8000`.
