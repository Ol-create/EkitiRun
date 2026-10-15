"""Pydantic request/response models for results."""

from typing import Literal

from pydantic import BaseModel


class ResultItem(BaseModel):
    position: int
    bib_number: str
    full_name: str
    gender: Literal["M", "F"]
    category_code: str
    status: Literal["started", "finished", "dnf"]
    last_checkpoint: str | None
    elapsed_seconds: int | None
    finish_seconds: int | None = None


class ResultsPage(BaseModel):
    items: list[ResultItem]
    total: int


class ScanEvent(BaseModel):
    """Data of an `event: scan` message on /stream/results."""

    bib_number: str
    checkpoint_id: int
    elapsed_seconds: int
