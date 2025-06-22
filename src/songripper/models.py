# src/songripper/models.py
"""Database models (with graceful fallback when ``sqlmodel`` is missing)."""

from typing import Optional

try:  # pragma: no cover - the real dependency isn't available in CI
    from sqlmodel import SQLModel, Field  # type: ignore

    def orm_model(cls):
        """Return the class unmodified when ``sqlmodel`` is present."""

        return cls

except Exception:  # pragma: no cover - executed when ``sqlmodel`` not installed
    # Provide light-weight stand-ins so tests can run without the dependency.
    from dataclasses import dataclass, field

    class SQLModel:
        def __init_subclass__(cls, **kwargs):  # type: ignore[override]
            # Ignore ``table=True`` and other kwargs used by SQLModel.
            return super().__init_subclass__()

    def Field(default=None, primary_key=False):  # noqa: D401 - mimic sqlmodel
        """Replacement for ``sqlmodel.Field`` when unavailable."""

        return field(default=default)

    def orm_model(cls):
        return dataclass(cls)


@orm_model
class Job(SQLModel, table=True):
    playlist: str
    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = "queued"


@orm_model
class Track(SQLModel, table=True):
    job_id: int
    artist: str
    title: str
    album: str
    filepath: str
    id: Optional[int] = Field(default=None, primary_key=True)
    approved: bool = False
    # base64 encoded album art from the MP3's ID3 tag.  May be ``None`` when
    # no cover image is found or when tag parsing dependencies are missing.
    cover: Optional[str] = None

