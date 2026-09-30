"""Freeze the collection to a file, and the reverse.

The snapshot is what makes the evaluation reproducible. Variant 34 requires the
collection to come from the web, but a crawl is not repeatable — pages change, hosts go
down, and a metric computed against a moving collection cannot be compared with one
computed last week. So the crawl's output is frozen once and committed, and every
reported number refers to that frozen collection.

It also means the system can be demonstrated without network access.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from irs.db.models import Document
from irs.db.session import get_sessionmaker
from irs.logging import get_logger

log = get_logger("irs.crawler.snapshot")

#: Written one JSON object per line, gzipped: streamable, appendable, and diffable
#: enough to review in a pull request.
BATCH = 200


async def write_snapshot(path: Path) -> int:
    """Write every stored document to ``path`` as gzipped JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sessionmaker = get_sessionmaker()

    written = 0
    async with sessionmaker() as session:
        total = int(
            (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        )
        if not total:
            print("the collection is empty — nothing to snapshot", flush=True)
            return 1

        with gzip.open(path, "wt", encoding="utf-8") as handle:
            offset = 0
            while True:
                documents = (
                    (
                        await session.execute(
                            select(Document).order_by(Document.id).offset(offset).limit(BATCH)
                        )
                    )
                    .scalars()
                    .all()
                )
                if not documents:
                    break

                for document in documents:
                    handle.write(
                        json.dumps(
                            {
                                "url": document.url,
                                "source_domain": document.source_domain,
                                "title": document.title,
                                "text": document.text,
                                "published_at": (
                                    document.published_at.isoformat()
                                    if document.published_at
                                    else None
                                ),
                                "fetched_at": (
                                    document.fetched_at.isoformat() if document.fetched_at else None
                                ),
                                "language": document.language,
                                "author": document.author,
                                "description": document.description,
                                "http_status": document.http_status,
                                "byte_size": document.byte_size,
                                "content_hash": document.content_hash,
                                "simhash": document.simhash,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    written += 1

                offset += BATCH

    # os.stat off the event loop would need a thread; the file was just written by
    # this coroutine and is local, so the read is immediate and not worth one.
    size_kib = await asyncio.to_thread(lambda: path.stat().st_size / 1024)
    log.info("snapshot_written", path=str(path), documents=written, size_kib=round(size_kib))
    print(
        f"\nSnapshot written\n{'-' * 46}\n"
        f"  path             {path}\n"
        f"  documents        {written}\n"
        f"  size             {size_kib:.0f} KiB\n"
        f"  created          {datetime.now(UTC).isoformat(timespec='seconds')}\n",
        flush=True,
    )
    return 0
