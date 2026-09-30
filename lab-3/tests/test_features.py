# -*- coding: utf-8 -*-
"""Тесты возможностей, добавленных поверх базового реферирования:
загрузка документа по ссылке, управление составом коллекции и статистика.

Сетевые запросы в тестах не выполняются: разбор HTML проверяется на
локальном образце страницы.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summarizer import webfetch                                    # noqa: E402
from summarizer.collection import (Collection, delete_document,    # noqa: E402
                                   save_document)
from summarizer.stats import collection_statistics                 # noqa: E402
from summarizer.tokenizer import filter_report                     # noqa: E402

SAMPLE_PAGE = """
<!DOCTYPE html><html lang="ru"><head>
  <title>Пример статьи — Тестовый сайт</title>
  <script>var tracker = 1;</script><style>body{color:red}</style>
</head>
<body class="skin-vector vector-toc-available">
  <div id="mw-navigation"><ul><li><a href="/">Главная</a></li><li><a href="/x">Раздел</a></li></ul></div>
  <header class="tm-header">Шапка сайта с меню и кнопкой входа</header>
  <div class="tm-page__main_has-sidebar">
    <h1>Заголовок статьи</h1>
    <p>Первый абзац статьи содержит достаточно длинный связный текст
       со сноской<sup class="reference">[12]</sup>, которая не должна разрывать предложение.</p>
    <p>Второй абзац тоже содержательный и заканчивается точкой, поэтому он попадает в результат.</p>
    <div class="infobox"><p>Служебная карточка, которую нужно отбросить целиком, хотя текст длинный.</p></div>
    <ul><li>Пункт</li><li>Ещё</li></ul>
  </div>
  <footer>Подвал сайта с копирайтом и ссылками на разделы</footer>
</body></html>
"""


class TestHtmlExtraction(unittest.TestCase):
    def setUp(self):
        parser = webfetch._TextExtractor()
        parser.feed(SAMPLE_PAGE)
        parser.close()
        self.parser = parser
        self.text = webfetch.clean_paragraphs(parser.paragraphs)

    def test_title_extracted(self):
        self.assertIn("Пример статьи", self.parser.title)

    def test_article_text_kept(self):
        self.assertIn("Первый абзац статьи", self.text)
        self.assertIn("Второй абзац", self.text)

    def test_service_blocks_dropped(self):
        for fragment in ("Шапка сайта", "Подвал сайта", "Служебная карточка", "Главная"):
            self.assertNotIn(fragment, self.text, fragment)

    def test_main_content_not_mistaken_for_sidebar(self):
        # класс «tm-page__main_has-sidebar» не должен отбрасывать основной текст
        self.assertGreater(len(self.text), 150)

    def test_inline_reference_does_not_split_sentence(self):
        self.assertIn("со сноской, которая не должна разрывать предложение.", self.text)

    def test_reference_markers_removed(self):
        self.assertNotIn("[12]", self.text)

    def test_paragraph_structure(self):
        self.assertEqual(len(self.text.split("\n\n")), 2)


class TestUrlValidation(unittest.TestCase):
    def test_scheme_rejected(self):
        with self.assertRaises(webfetch.WebFetchError):
            webfetch._validate_url("ftp://example.com/file.txt")

    def test_local_address_rejected(self):
        with self.assertRaises(webfetch.WebFetchError):
            webfetch._validate_url("http://127.0.0.1:8765/")

    def test_unknown_host_rejected(self):
        with self.assertRaises(webfetch.WebFetchError):
            webfetch._validate_url("https://no-such-host.invalid/page")

    def test_cyrillic_path_encoded(self):
        url = webfetch._validate_url("https://ru.wikipedia.org/wiki/Алгоритм")
        self.assertTrue(url.startswith("https://ru.wikipedia.org/wiki/%D0"))


class TestCollectionManagement(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="yazis-collection-")
        for name in ("ru_cs_ai.txt", "en_lit_hamlet.txt"):
            shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "data", "collection", name),
                        os.path.join(self.directory, name))

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_save_and_delete_roundtrip(self):
        text = "Квантовые вычисления. " * 40
        record = save_document(text, "Квантовые вычисления", directory=self.directory)
        self.assertTrue(record["added_by_user"])
        self.assertEqual(record["language"], "ru")
        self.assertTrue(os.path.exists(os.path.join(self.directory, record["file"])))

        collection = Collection.load(self.directory)
        self.assertEqual(collection.size, 3)
        self.assertIsNotNone(collection.get(record["id"]))

        delete_document(record["id"], directory=self.directory)
        self.assertFalse(os.path.exists(os.path.join(self.directory, record["file"])))
        self.assertEqual(Collection.load(self.directory).size, 2)

    def test_short_document_rejected(self):
        with self.assertRaises(ValueError):
            save_document("слишком коротко", "Тест", directory=self.directory)

    def test_builtin_document_protected(self):
        save_document("Текст документа. " * 40, "Защита", directory=self.directory)
        with self.assertRaises(KeyError):
            delete_document("ru_cs_ai", directory=self.directory)

    def test_identifier_is_unique(self):
        # разные тексты с одинаковым названием получают разные идентификаторы
        first = save_document("Первый текст. " * 40, "Один и тот же заголовок",
                              directory=self.directory)
        second = save_document("Второй текст. " * 40, "Один и тот же заголовок",
                               directory=self.directory)
        self.assertNotEqual(first["id"], second["id"])

    def test_same_text_is_not_duplicated(self):
        text = "Повторно добавляемый документ. " * 40
        first = save_document(text, "Повтор", directory=self.directory)
        second = save_document(text, "Повтор", directory=self.directory)
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(first["existing"])
        self.assertTrue(second["existing"])
        self.assertEqual(Collection.load(self.directory).size, 3)

    def test_duplicate_check_can_be_disabled(self):
        text = "Намеренная копия документа. " * 40
        first = save_document(text, "Копия", directory=self.directory)
        second = save_document(text, "Копия", directory=self.directory, reuse_existing=False)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(Collection.load(self.directory).size, 4)


class TestStatistics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collection = Collection.load()
        cls.stats = collection_statistics(cls.collection)

    def test_filtering_parts_sum_to_total(self):
        f = self.stats["filtering"]
        self.assertEqual(f["kept"] + f["stopwords"] + f["short"] + f["foreign"], f["words"])

    def test_document_rows_match_collection(self):
        self.assertEqual(len(self.stats["documents"]), self.collection.size)

    def test_df_histogram_covers_all_terms(self):
        total = sum(row["terms"] for row in self.stats["df_histogram"])
        self.assertEqual(total, self.stats["unique_terms"])

    def test_zipf_exponent_is_positive(self):
        for lang, data in self.stats["zipf"].items():
            self.assertGreater(data["exponent"], 0.3, lang)
            self.assertLess(data["exponent"], 2.0, lang)

    def test_filter_report_counts_numbers(self):
        report = filter_report("В 2024 году было 3 случая и один разбор.", "ru")
        self.assertEqual(report["numbers"], 2)
        self.assertGreaterEqual(report["stopwords"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
