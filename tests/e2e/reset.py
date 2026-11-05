"""Vacía y recrea el esquema de la base E2E antes de ejecutar la suite."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from sentinel.persistence.tables import Base


async def _reset(dsn: str) -> None:
    engine = create_async_engine(dsn)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_reset(os.environ["SENTINEL_E2E_DSN"]))
    print("base E2E reiniciada")
