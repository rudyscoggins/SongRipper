# src/songripper/models.py
from sqlmodel import SQLModel, Field
from typing import Optional
class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    playlist: str
    status: str = "queued"
class Track(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int
    artist: str
    title: str
    album: str
    filepath: str
    approved: bool = False
