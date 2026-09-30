#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Запуск системы автоматического реферирования документов.

    python3 run.py              — запустить сервер и открыть браузер
    python3 run.py --port 9000  — другой порт
    python3 run.py --no-browser — не открывать браузер автоматически
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from server.app import get_collection, serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Автоматическое реферирование документов")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("Индексация коллекции документов…")
    collection = get_collection(True)
    print(f"  загружено документов: {collection.size}, "
          f"время индексации: {collection.load_time * 1000:.0f} мс")

    try:
        httpd = serve(args.host, args.port)
    except OSError as exc:
        print(f"\nНе удалось занять порт {args.port}: {exc}\n"
              f"Возможно, система уже запущена в другом окне. "
              f"Откройте http://{args.host}:{args.port}/ "
              f"или запустите с другим портом: python3 run.py --port {args.port + 1}",
              file=sys.stderr)
        return 1
    url = f"http://{args.host}:{args.port}/"
    print(f"\nСистема доступна по адресу: {url}\nОстановить: Ctrl+C\n")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
