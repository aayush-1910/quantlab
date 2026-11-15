from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, Engine

from quantlab.common.db import get_engine
from quantlab.common.settings import Settings, get_settings
from quantlab.data.storage.lake import DataLake


def get_connection(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection


def get_lake(settings: Annotated[Settings, Depends(get_settings)]) -> DataLake:
    return DataLake(settings.data_dir)


DbConnection = Annotated[Connection, Depends(get_connection)]
Lake = Annotated[DataLake, Depends(get_lake)]
