# -*- coding: utf-8 -*-
"""Консольный интерфейс системы реферирования.

Примеры запуска:

    python3 -m summarizer.cli --list
    python3 -m summarizer.cli --doc ru_cs_ai
    python3 -m summarizer.cli --doc en_lit_hamlet --sentences 7 --format html -o out.html
    python3 -m summarizer.cli --file статья.txt --keywords 20
    python3 -m summarizer.cli --url https://ru.wikipedia.org/wiki/Алгоритм
    python3 -m summarizer.cli --url <адрес> --add-to-collection
    python3 -m summarizer.cli --batch --csv data/output/collection_report.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

from . import config, export
from .analysis import analyze
from .collection import Collection, Document, save_document
from .config import SummaryParams
from .text import detect_language
from .webfetch import WebFetchError, fetch_url


def build_params(args: argparse.Namespace) -> SummaryParams:
    return SummaryParams(sentences=args.sentences, keywords=args.keywords,
                         alpha=args.alpha, beta=args.beta, method=args.method,
                         conflate_stems=not args.no_conflate,
                         mmr_lambda=args.mmr, length_norm=args.length_norm).clamp()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Автоматическое реферирование документов (sentence extraction + OSTIS)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--doc", help="идентификатор документа коллекции")
    source.add_argument("--file", help="путь к текстовому файлу")
    source.add_argument("--url", help="адрес веб-страницы для реферирования")
    source.add_argument("--list", action="store_true", help="показать состав коллекции")
    source.add_argument("--batch", action="store_true", help="обработать всю коллекцию")
    parser.add_argument("--add-to-collection", action="store_true",
                        help="сохранить документ (--file/--url) в коллекцию")
    parser.add_argument("--sentences", type=int, default=config.DEFAULT_SUMMARY_SENTENCES)
    parser.add_argument("--keywords", type=int, default=config.DEFAULT_KEYWORDS)
    parser.add_argument("--method", default="tfidf",
                        choices=["tfidf", "textrank", "hybrid", "lead"])
    parser.add_argument("--alpha", type=float, default=1.0, help="степень у Posd")
    parser.add_argument("--beta", type=float, default=1.0, help="степень у Posp")
    parser.add_argument("--mmr", type=float, default=1.0, help="коэффициент MMR")
    parser.add_argument("--no-conflate", action="store_true", help="без склейки основ")
    parser.add_argument("--length-norm", default="none", choices=["none", "sqrt", "linear"],
                        help="нормировка Score по длине предложения")
    parser.add_argument("--format", default="txt", choices=list(export.FORMATS))
    parser.add_argument("-o", "--output", help="файл для сохранения результата")
    parser.add_argument("--csv", help="файл таблицы показателей для режима --batch")
    args = parser.parse_args(argv)

    try:
        collection = Collection.load()
    except FileNotFoundError:
        print("Каталог коллекции не найден: " + config.COLLECTION_DIR, file=sys.stderr)
        return 1
    params = build_params(args)

    if args.list or not (args.doc or args.file or args.url or args.batch):
        print(f"Коллекция: {collection.size} документов "
              f"({collection.load_time * 1000:.0f} мс на индексацию)\n")
        print(f"{'идентификатор':26s} {'яз':3s} {'симв.':>7s} {'предл.':>7s}  название")
        for document in collection.documents:
            print(f"{document.doc_id:26s} {document.language:3s} {document.length:7d} "
                  f"{len(document.sentences):7d}  {document.title}")
        return 0

    if args.batch:
        rows = []
        for document in collection.documents:
            analysis = analyze(document, collection, params)
            quality = analysis.quality()
            rows.append({
                "id": document.doc_id, "title": document.title,
                "language": document.language, "domain": document.domain,
                "chars": document.length, "sentences": len(document.sentences),
                "terms": len(document.tf), "time_ms": round(analysis.timings["total_ms"], 2),
                "compression": quality["compression"],
                "keyword_coverage": quality["keyword_coverage"],
                "mean_position": quality["position_bias"]["mean_relative_position"],
                "top_keywords": " ".join(k.form for k in analysis.keywords[:5]),
            })
            print(f"{document.doc_id:26s} {analysis.timings['total_ms']:6.2f} мс  "
                  f"сжатие {quality['compression'] * 100:5.1f}%  "
                  f"покрытие {quality['keyword_coverage'] * 100:5.1f}%  "
                  f"{', '.join(k.form for k in analysis.keywords[:5])}")
        total = sum(r["time_ms"] for r in rows)
        print(f"\nВсего: {len(rows)} документов, {total:.1f} мс "
              f"({total / len(rows):.1f} мс на документ)")
        if args.csv:
            os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
            with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
            print(f"Таблица показателей сохранена: {args.csv}")
        return 0

    if args.file or args.url:
        if args.url:
            page = fetch_url(args.url)
            title, text, source = page["title"], page["text"], page["url"]
            doc_id = "url_document"
            print(f"Загружено: «{title}» — {len(text)} символов", file=sys.stderr)
        else:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
            title = os.path.basename(args.file)
            source = os.path.abspath(args.file)
            doc_id = os.path.splitext(os.path.basename(args.file))[0]

        if args.add_to_collection:
            record = save_document(text, title, source=source)
            print(f"Документ добавлен в коллекцию: {record['id']}", file=sys.stderr)
            collection = Collection.load()
            analysis = analyze(collection.get(record["id"]), collection, params)
        else:
            document = Document(doc_id=doc_id, title=title, text=text,
                                language=detect_language(text), source=source)
            collection.add_temporary(document)
            analysis = analyze(document, collection, params, temporary=True)
    else:
        document = collection.get(args.doc)
        if document is None:
            print(f"Документ не найден: {args.doc}", file=sys.stderr)
            return 1
        analysis = analyze(document, collection, params)

    body, _ = export.render(analysis, args.format)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"Сохранено: {args.output}")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WebFetchError as exc:
        print(f"Не удалось загрузить страницу: {exc}", file=sys.stderr)
        raise SystemExit(1)
