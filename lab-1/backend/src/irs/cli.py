"""Command-line interface.

Every operation the Makefile and ``./irs`` expose runs through here, so there is one
implementation of "seed the corpus" or "rebuild the index" rather than one per entry
point. Uses stdlib ``argparse`` deliberately — a CLI framework would be another
dependency for a handful of subcommands.

    python -m irs.cli index
    python -m irs.cli crawl --url https://example.com --pages 50
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult

from irs.db.session import dispose_engine, get_sessionmaker
from irs.logging import configure_logging, get_logger

log = get_logger("irs.cli")

SEEDS_DIR = Path("/app/seeds")
#: Tried in order. `corpus.jsonl.gz` is the frozen crawl snapshot — the real collection
#: for variant 34. `dev-corpus.jsonl` is a small hand-written fixture that lets the
#: indexer and rankers be exercised before any crawl has been run.
SEED_CANDIDATES = ("corpus.jsonl.gz", "dev-corpus.jsonl")


def resolve_seed_path(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    for name in SEED_CANDIDATES:
        candidate = SEEDS_DIR / name
        if candidate.exists():
            return candidate
    return None


# --------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------


def _print_table(title: str, rows: list[tuple[str, Any]]) -> None:
    """Small aligned key/value table, so CLI output is readable in a terminal."""
    width = max((len(key) for key, _ in rows), default=0)
    print(f"\n{title}")
    print("-" * (width + 24))
    for key, value in rows:
        print(f"  {key.ljust(width)}  {value}")
    print()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y"):
        try:
            return datetime.strptime(value[:10] if fmt != "%Y" else value[:4], fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------------
# seed
# --------------------------------------------------------------------------------


async def cmd_seed(args: argparse.Namespace) -> int:
    """Load the frozen document snapshot.

    The snapshot exists so the collection — and therefore every metric computed over it
    — is reproducible, and so the system can be demonstrated without internet access.
    Variant 34 still requires a real crawler; this is the frozen output of one, not a
    replacement for it.
    """
    from irs.db.models import Document
    from irs.index.builder import IndexBuilder

    path = resolve_seed_path(args.path)
    if path is None:
        log.warning("seed_file_missing", searched=[str(SEEDS_DIR / n) for n in SEED_CANDIDATES])
        print(
            f"no snapshot found in {SEEDS_DIR} (tried: {', '.join(SEED_CANDIDATES)})\n"
            "  Crawl some pages and freeze them instead:\n"
            "    make crawl url=https://en.wikipedia.org/wiki/Information_retrieval\n"
            "    make snapshot",
            file=sys.stderr,
        )
        return 0

    opener = gzip.open if path.suffix == ".gz" else open
    records: list[dict[str, Any]] = []
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))

    log.info("seed_started", path=str(path), records=len(records))

    sessionmaker = get_sessionmaker()
    inserted = skipped = 0

    async with sessionmaker() as session:
        if args.replace:
            deleted = await session.execute(delete(Document))
            log.info(
                "seed_cleared_existing",
                deleted=cast("CursorResult[Any]", deleted).rowcount,
            )

        existing = {row[0] for row in (await session.execute(select(Document.url))).all()}

        for record in records:
            url = record.get("url")
            if not url or url in existing:
                skipped += 1
                continue

            session.add(
                Document(
                    url=url,
                    source_domain=record.get("source_domain") or "",
                    title=record.get("title") or "",
                    text=record.get("text") or "",
                    published_at=_parse_date(record.get("published_at")),
                    fetched_at=(
                        datetime.fromisoformat(record["fetched_at"]).replace(tzinfo=None)
                        if record.get("fetched_at")
                        else datetime.now(UTC).replace(tzinfo=None)
                    ),
                    language=record.get("language") or "en",
                    author=record.get("author"),
                    description=record.get("description"),
                    http_status=record.get("http_status") or 200,
                    byte_size=record.get("byte_size"),
                    content_hash=record.get("content_hash") or "",
                    simhash=record.get("simhash"),
                )
            )
            existing.add(url)
            inserted += 1

        await session.commit()
        log.info("seed_documents_written", inserted=inserted, skipped=skipped)

        if inserted and not args.no_index:
            stats = await IndexBuilder(session).rebuild()
            await session.commit()
            _print_table(
                "Seeded and indexed",
                [
                    ("documents inserted", inserted),
                    ("documents skipped", skipped),
                    ("collection size N", stats.document_count),
                    ("dictionary size D", stats.term_count),
                    ("postings", stats.posting_count),
                ],
            )
            return 0

    _print_table("Seeded", [("documents inserted", inserted), ("documents skipped", skipped)])
    return 0


# --------------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------------


async def cmd_index(args: argparse.Namespace) -> int:
    """Rebuild the inverted index and every term weight."""
    from irs.index.builder import IndexBuilder

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stats = await IndexBuilder(session).rebuild(reanalyze=not args.weights_only)
        await session.commit()

    _print_table(
        "Index rebuilt",
        [
            ("collection size N", stats.document_count),
            ("dictionary size D", stats.term_count),
            ("postings", stats.posting_count),
            ("average length", f"{stats.average_document_length:.1f} terms"),
            ("index version", stats.index_version),
            ("logarithm base", stats.log_base),
            ("duration", f"{stats.duration_ms:.0f} ms"),
        ],
    )
    return 0


# --------------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------------


async def cmd_embed(args: argparse.Namespace) -> int:
    """Compute the dense embeddings the semantic ranker needs."""
    from irs.index.builder import IndexBuilder

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        embedded = await IndexBuilder(session).embed_pending()
        await session.commit()

    _print_table("Embeddings", [("documents embedded", embedded)])
    return 0


async def cmd_stats(_: argparse.Namespace) -> int:
    """Print collection statistics."""
    from irs.db.models import Document, Posting, Term
    from irs.index.builder import get_collection_stat

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stat = await get_collection_stat(session)
        documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        terms = (await session.execute(select(func.count()).select_from(Term))).scalar_one()
        postings = (await session.execute(select(func.count()).select_from(Posting))).scalar_one()

        top_terms = (
            await session.execute(
                select(Term.lemma, Term.document_frequency, Term.idf)
                .order_by(Term.document_frequency.desc())
                .limit(10)
            )
        ).all()

    _print_table(
        "Collection",
        [
            ("documents (live)", documents),
            ("documents (indexed N)", stat.document_count),
            ("dictionary (live)", terms),
            ("dictionary (indexed D)", stat.term_count),
            ("postings", postings),
            ("average length", f"{stat.average_document_length:.1f} terms"),
            ("index version", stat.index_version),
            ("logarithm base", stat.log_base),
            ("built at", stat.built_at or "never"),
            ("embedded documents", stat.embedded_document_count),
        ],
    )

    if documents != stat.document_count or terms != stat.term_count:
        print("  ! the index is stale — run `make index`\n", file=sys.stderr)

    if top_terms:
        print("Most frequent terms (highest N_k, therefore lowest weight):")
        for lemma, df, idf in top_terms:
            print(f"  {lemma:<24} N_k={df:<6} B_i={idf:.4f}")
        print()
    return 0


# --------------------------------------------------------------------------------
# placeholders wired up by later phases
# --------------------------------------------------------------------------------


async def cmd_crawl(args: argparse.Namespace) -> int:
    from irs.crawler.service import run_crawl_from_cli

    return await run_crawl_from_cli(
        seed_urls=[args.url],
        max_pages=args.pages,
        max_depth=args.depth,
        same_domain_only=not args.any_domain,
    )


async def cmd_snapshot(args: argparse.Namespace) -> int:
    from irs.crawler.snapshot import write_snapshot

    return await write_snapshot(Path(args.out) if args.out else SEEDS_DIR / "corpus.jsonl.gz")


async def cmd_evaluate(args: argparse.Namespace) -> int:
    from irs.eval.service import run_full_evaluation

    return int(await run_full_evaluation(collection=args.collection))


async def cmd_report(args: argparse.Namespace) -> int:
    from irs.report.generate import generate_report

    return int(await generate_report(Path(args.out)))


async def _resolve_collection(session: Any, name: str | None) -> Any:
    """Look a test collection up by name; default to the topical one."""
    from irs.config import settings
    from irs.db.models import TestCollection

    target = name or settings.evaluation.topical_collection_name
    collection = (
        await session.execute(select(TestCollection).where(TestCollection.name == target))
    ).scalar_one_or_none()
    if collection is None:
        print(f"no test collection named {target!r}", flush=True)
    return collection


async def cmd_topics(args: argparse.Namespace) -> int:
    from irs.eval import topics as topics_module

    async with get_sessionmaker()() as session:
        if args.topics_command == "seed":
            path = Path(args.path) if args.path else SEEDS_DIR / "topics.yaml"
            if not path.exists():
                print(f"topics file not found: {path}", flush=True)
                return 2
            file = topics_module.load_topic_file(path)
            collection, inserted = await topics_module.seed_topics(
                session, file, replace=args.replace
            )
            await session.commit()
            counts = await topics_module.topic_counts(session, collection.id)
            _print_table(
                f"Topics seeded into {collection.name!r}",
                [("inserted", inserted), ("in file", len(file.topics))]
                + [
                    (f"{category}", f"{c['total']} ({c['judged']} judged)")
                    for category, c in sorted(counts.items())
                ],
            )
            return 0

        collection = await _resolve_collection(session, args.collection)
        if collection is None:
            return 2
        try:
            selected = await topics_module.select_judged(
                session, collection.id, count=args.count, seed=args.seed
            )
        except ValueError as exc:
            print(str(exc), flush=True)
            return 2
        await session.commit()
        frozen = collection.frozen_at
        print(f"\nSelected {len(selected)} topics for judging (runs frozen at {frozen}):")
        for topic in selected:
            print(f"  {topic.ext_id:>3}  {topic.category:<20} {topic.title}")
        return 0


async def cmd_pool(args: argparse.Namespace) -> int:
    from irs.eval import pooling

    async with get_sessionmaker()() as session:
        collection = await _resolve_collection(session, args.collection)
        if collection is None:
            return 2

        if args.pool_command == "build":
            stats = await pooling.build_pool(
                session,
                collection.id,
                depth=args.depth,
                random_size=args.random,
                replace=args.replace,
            )
            await session.commit()
            _print_table(
                f"Pool built for {collection.name!r}",
                [
                    ("topics", stats.topics),
                    ("entries", stats.entries),
                    ("rankers", ", ".join(stats.rankers)),
                    ("oracle ranker", stats.oracle_ranker),
                    ("depth", stats.depth),
                    ("random sample / topic", stats.random_size),
                    ("duration", f"{stats.duration_ms / 1000:.1f}s"),
                ]
                + [(f"source: {k}", v) for k, v in sorted(stats.by_source.items())],
            )
            return 0

        coverage = await pooling.pool_stats(session, collection.id)
        rows: list[tuple[str, Any]] = [
            ("unique documents", coverage.unique_documents),
            ("entries", coverage.total_entries),
        ]
        for source, bucket in sorted(coverage.by_source.items()):
            rows.append(
                (
                    f"{source}",
                    f"{int(bucket['entries'])} entries, {int(bucket['judged'])} judged, "
                    f"{int(bucket['relevant'])} relevant ({bucket['relevant_rate']:.0%})",
                )
            )
        _print_table(f"Pool of {collection.name!r}", rows)
        print("  per topic (ext_id: size / judged / relevant):")
        for topic in coverage.per_topic:
            flag = "*" if topic["is_judged"] else " "
            print(
                f"  {flag}{topic['ext_id']:>3}  {topic['total']:>3} / {topic['judged']:>3} / "
                f"{topic['relevant']:>3}   {topic['title'][:60]}"
            )
        print("  (* = selected for judging)")
        return 0


async def cmd_judge(args: argparse.Namespace) -> int:
    from irs.eval.assessor import LlmAssessor, build_prompt
    from irs.eval.judging import (
        build_views,
        create_judging_job,
        get_or_create_llm_assessor,
        pending_pairs,
        run_judging_job,
    )

    assessor = LlmAssessor()
    async with get_sessionmaker()() as session:
        collection = await _resolve_collection(session, args.collection)
        if collection is None:
            return 2
        assessor_row = await get_or_create_llm_assessor(session, assessor)
        await session.commit()

        if args.dry_run:
            from irs.db.models import Document, Query

            pairs = await pending_pairs(session, collection.id, assessor_row.id, limit=1)
            if not pairs:
                print("nothing pending — every pool pair is judged", flush=True)
                return 0
            topic = await session.get(Query, pairs[0][0])
            document = await session.get(Document, pairs[0][1])
            assert topic is not None and document is not None
            views = await build_views(topic, document, assessor.config.max_document_chars)
            for message in build_prompt(*views):
                print(f"\n--- {message['role']} ---\n{message['content']}")
            remaining = len(await pending_pairs(session, collection.id, assessor_row.id))
            print(f"\n{remaining} pairs pending for {assessor.assessor_name}")
            return 0

        job = await create_judging_job(session, collection.id, assessor_row.id, limit=args.limit)
        await session.commit()
        job_id = job.id
        print(
            f"judging job {job_id}: {job.total_pairs} pairs with {assessor.assessor_name}",
            flush=True,
        )

    started = datetime.now(UTC)

    async def progress(payload: dict[str, Any]) -> None:
        if payload.get("event") != "judged":
            return
        done = int(payload.get("judged", 0)) + int(payload.get("failed", 0))
        total = int(payload.get("total", 0)) or 1
        elapsed = (datetime.now(UTC) - started).total_seconds()
        eta = elapsed / done * (total - done) if done else 0.0
        print(
            f"  {done:>4}/{total}  q={payload.get('query_id')} d={payload.get('document_id')}"
            f"  elapsed {elapsed / 60:.1f} min  eta {eta / 60:.1f} min",
            flush=True,
        )

    try:
        outcome = await run_judging_job(
            job_id, assessor=assessor, limit=args.limit, on_progress=progress
        )
    except Exception as exc:
        print(f"judging failed: {exc}", flush=True)
        return 1
    _print_table(
        "Judging finished",
        [
            ("judged", outcome.judged),
            ("failed", outcome.failed),
            ("duration", f"{outcome.duration_ms / 60000:.1f} min"),
        ]
        + [(f"grade {k}", v) for k, v in sorted(outcome.grades.items())],
    )
    return 0


async def cmd_lsa(args: argparse.Namespace) -> int:
    from irs.index.matrix import build_lsa

    async with get_sessionmaker()() as session:
        stats = await build_lsa(session, components=args.components)
        await session.commit()
    _print_table("Latent-semantic projection", list(stats.as_dict().items()))
    return 0


# --------------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------------


def _add_collection_commands(subparsers: Any) -> None:
    """Subcommands of the topical test-collection pipeline."""
    topics = subparsers.add_parser("topics", help="hand-authored topical test collection")
    topics_sub = topics.add_subparsers(dest="topics_command", required=True)
    topics_seed = topics_sub.add_parser("seed", help="load backend/seeds/topics.yaml")
    topics_seed.add_argument("--path")
    topics_seed.add_argument("--replace", action="store_true", help="drop existing topics first")
    topics_select = topics_sub.add_parser(
        "select", help="choose the judged subset (only after the pool exists)"
    )
    topics_select.add_argument("--collection", default=None)
    topics_select.add_argument("--count", type=int, default=None)
    topics_select.add_argument("--seed", type=int, default=None)
    topics.set_defaults(handler=cmd_topics)

    pool = subparsers.add_parser("pool", help="judgment pool: every ranker + oracle + random")
    pool_sub = pool.add_subparsers(dest="pool_command", required=True)
    pool_build = pool_sub.add_parser("build", help="run every ranker and build the pool")
    pool_build.add_argument("--collection", default=None)
    pool_build.add_argument("--depth", type=int, default=None)
    pool_build.add_argument("--random", type=int, default=None)
    pool_build.add_argument("--replace", action="store_true")
    pool_stats = pool_sub.add_parser("stats", help="coverage and relevance rate by source")
    pool_stats.add_argument("--collection", default=None)
    pool.set_defaults(handler=cmd_pool)

    judge = subparsers.add_parser("judge", help="judge pending pool pairs with the LLM assessor")
    judge.add_argument("--collection", default=None)
    judge.add_argument("--limit", type=int, default=None, help="judge at most this many pairs")
    judge.add_argument("--dry-run", action="store_true", help="print the prompt for one pair")
    judge.set_defaults(handler=cmd_judge)

    lsa = subparsers.add_parser("lsa", help="build the latent-semantic projection")
    lsa.add_argument("--components", type=int, default=None)
    lsa.set_defaults(handler=cmd_lsa)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m irs.cli",
        description="Information retrieval system — administrative commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="load the frozen document snapshot")
    seed.add_argument(
        "--path", help=f"snapshot file (default: first of {', '.join(SEED_CANDIDATES)})"
    )
    seed.add_argument("--replace", action="store_true", help="delete existing documents first")
    seed.add_argument("--no-index", action="store_true", help="skip the index rebuild afterwards")
    seed.set_defaults(handler=cmd_seed)

    index = subparsers.add_parser("index", help="rebuild the index and term weights")
    index.add_argument(
        "--weights-only",
        action="store_true",
        help="keep existing term counts and recompute only the weights",
    )
    index.set_defaults(handler=cmd_index)

    embed = subparsers.add_parser("embed", help="compute dense embeddings for the semantic ranker")
    embed.set_defaults(handler=cmd_embed)

    stats = subparsers.add_parser("stats", help="print collection statistics")
    stats.set_defaults(handler=cmd_stats)

    crawl = subparsers.add_parser("crawl", help="crawl live pages from a seed URL")
    crawl.add_argument("--url", required=True)
    crawl.add_argument("--pages", type=int, default=50)
    crawl.add_argument("--depth", type=int, default=2)
    crawl.add_argument(
        "--any-domain",
        action="store_true",
        help="follow links off the seed's host (off by default, to bound the crawl)",
    )
    crawl.set_defaults(handler=cmd_crawl)

    snapshot = subparsers.add_parser("snapshot", help="freeze the corpus to a file")
    snapshot.add_argument("--out")
    snapshot.set_defaults(handler=cmd_snapshot)

    evaluate = subparsers.add_parser("evaluate", help="score every ranker")
    evaluate.add_argument("--collection", default=None)
    evaluate.set_defaults(handler=cmd_evaluate)

    _add_collection_commands(subparsers)

    report = subparsers.add_parser("report", help="regenerate the report")
    report.add_argument("--out", default="/app/docs")
    report.set_defaults(handler=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], Awaitable[int]] = args.handler

    async def run() -> int:
        try:
            return await handler(args)
        finally:
            await dispose_engine()

    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except ModuleNotFoundError as exc:
        # A subcommand belonging to a component that is not built yet.
        log.error("command_unavailable", command=args.command, missing=str(exc))
        print(
            f"`{args.command}` is not available yet: {exc}",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        log.exception("command_failed", command=args.command)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
