from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.api.dependencies import DbConnection
from apps.api.errors import ApiError
from quantlab.data.schemas import Exchange, Instrument
from quantlab.data.storage import catalog

router = APIRouter(tags=["instruments"])


class InstrumentList(BaseModel):
    # When set, only symbol mappings in effect on this date were matched.
    as_of: date | None
    limit: int
    offset: int
    instruments: list[Instrument]


@router.get("/instruments")
def list_instruments(
    conn: DbConnection,
    q: Annotated[str | None, Query(max_length=100, description="Symbol or name contains")] = None,
    exchange: Exchange | None = None,
    as_of: Annotated[
        date | None, Query(description="Match only symbol mappings in effect on this date")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InstrumentList:
    found = catalog.search_instruments(conn, q, exchange, as_of, limit, offset)
    return InstrumentList(as_of=as_of, limit=limit, offset=offset, instruments=found)


@router.get("/instruments/{instrument_id}")
def get_instrument(instrument_id: str, conn: DbConnection) -> Instrument:
    instrument = catalog.get_instrument(conn, instrument_id)
    if instrument is None:
        raise ApiError(404, "instrument_not_found", f"Instrument '{instrument_id}' does not exist.")
    return instrument
