"""The single shared watchlist. There are no users yet, so it is not per-user data."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.dependencies import DbConnection
from apps.api.errors import ApiError
from quantlab.data.schemas import Instrument
from quantlab.data.storage import catalog

router = APIRouter(tags=["watchlist"])


class WatchlistItem(BaseModel):
    instrument: Instrument
    added_at: datetime


class Watchlist(BaseModel):
    items: list[WatchlistItem]


def _read(conn: DbConnection) -> Watchlist:
    return Watchlist(
        items=[
            WatchlistItem(instrument=instrument, added_at=added_at)
            for instrument, added_at in catalog.list_watchlist(conn)
        ]
    )


@router.get("/watchlist")
def get_watchlist(conn: DbConnection) -> Watchlist:
    return _read(conn)


@router.put("/watchlist/{instrument_id}")
def add_to_watchlist(instrument_id: str, conn: DbConnection) -> Watchlist:
    """Idempotent: adding an instrument that is already listed changes nothing."""
    if catalog.get_instrument(conn, instrument_id) is None:
        raise ApiError(404, "instrument_not_found", f"Instrument '{instrument_id}' does not exist.")
    catalog.add_to_watchlist(conn, instrument_id)
    conn.commit()
    return _read(conn)


@router.delete("/watchlist/{instrument_id}")
def remove_from_watchlist(instrument_id: str, conn: DbConnection) -> Watchlist:
    """Idempotent: removing an instrument that is not listed changes nothing."""
    catalog.remove_from_watchlist(conn, instrument_id)
    conn.commit()
    return _read(conn)
