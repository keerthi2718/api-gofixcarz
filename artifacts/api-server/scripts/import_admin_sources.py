"""Import authentic source records into development only; never fabricate source data."""
import argparse
import asyncio
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.database.session import async_session
from app.schemas.admin_operations import SourceBatch
from app.services.admin_source_import import import_sources


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if settings.ENVIRONMENT != "development" or make_url(settings.DATABASE_URL).host != "helium":
        raise SystemExit("Only internal development source ingestion is permitted")
    batch = SourceBatch.model_validate_json(args.file.read_text())
    async with async_session() as session:
        async with session.begin():
            result = await import_sources(session, batch)
    print(f"Imported {result['accounts']} customer accounts and {result['records']} source records")


if __name__ == "__main__":
    asyncio.run(main())
