# -*- coding: utf-8 -*-
"""Автоматические тесты ядра системы реферирования.

Запуск:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summarizer.collection import Collection, Document          # noqa: E402
from summarizer.config import SummaryParams                     # noqa: E402
from summarizer.analysis import analyze                         # noqa: E402
from summarizer.metrics import rouge_l, rouge_n, selection_agreement  # noqa: E402
from summarizer.scs import to_identifier, to_scs                # noqa: E402
from summarizer.stemmer import stem                             # noqa: E402
from summarizer.summary import (position_in_document, position_in_paragraph,
                                score_sentences, select_sentences)      # noqa: E402
from summarizer.text import (detect_language, split_paragraphs,
                             split_sentences)                    # noqa: E402
from summarizer.tokenizer import tokenize                        # noqa: E402
from summarizer.weights import compute_term_weights, term_weight # noqa: E402


class TestStemmer(unittest.TestCase):
    def test_russian_forms_collapse(self):
        for word in ("заболевание", "заболевания", "заболеваний", "заболеваниями"):
            self.assertEqual(stem(word, "ru"), "заболеван")
        self.assertEqual(stem("нейронных", "ru"), stem("нейронная", "ru"))
        self.assertEqual(stem("алгоритмов", "ru"), "алгоритм")

    def test_russian_yo_normalised(self):
        self.assertEqual(stem("слоёв", "ru"), stem("слоев", "ru"))

    def test_english_porter2(self):
        cases = {"databases": "databas", "computing": "comput", "running": "run",
                 "flies": "fli", "national": "nation", "generalization": "general",
                 "learned": "learn", "relational": "relat"}
        for word, expected in cases.items():
            self.assertEqual(stem(word, "en"), expected, word)

    def test_short_words_unchanged(self):
        self.assertEqual(stem("он", "ru"), "он")
        self.assertEqual(stem("is", "en"), "is")


class TestSegmentation(unittest.TestCase):
    TEXT = ("Первый абзац. Он содержит т. д. и сокращения, напр. такие.\n\n"
            "Второй абзац начинается здесь. А. С. Пушкин — это инициалы, "
            "а 3.14 — число. Конец!")

    def setUp(self):
        self.paragraphs = split_paragraphs(self.TEXT)
        self.sentences = split_sentences(self.TEXT, self.paragraphs)

    def test_paragraph_count(self):
        self.assertEqual(len(self.paragraphs), 2)

    def test_offsets_match_source(self):
        for sentence in self.sentences:
            self.assertEqual(self.TEXT[sentence.start:sentence.end], sentence.text)

    def test_abbreviations_do_not_split(self):
        texts = [s.text for s in self.sentences]
        self.assertTrue(any("т. д." in t for t in texts))
        self.assertTrue(any("А. С. Пушкин" in t for t in texts))
        self.assertTrue(any("3.14" in t for t in texts))

    def test_paragraph_local_offsets(self):
        first_of_second = next(s for s in self.sentences if s.paragraph == 1)
        self.assertEqual(first_of_second.para_start, 0)
        self.assertEqual(first_of_second.para_len, len(self.paragraphs[1].text))

    def test_language_detection(self):
        self.assertEqual(detect_language("Это русский текст"), "ru")
        self.assertEqual(detect_language("This is English text"), "en")


class TestTokenizer(unittest.TestCase):
    def test_filters(self):
        tokens = tokenize("Это машинное обучение и 250 машин, method of learning.", "ru")
        forms = [t.norm for t in tokens]
        self.assertIn("машинное", forms)
        self.assertNotIn("это", forms)          # стоп-слово
        self.assertNotIn("250", forms)          # число
        self.assertNotIn("method", forms)       # латиница в русском тексте
        self.assertNotIn("и", forms)            # стоп-слово

    def test_english_filters(self):
        tokens = tokenize("The neural network learns from 1000 examples.", "en")
        forms = [t.norm for t in tokens]
        self.assertIn("neural", forms)
        self.assertNotIn("the", forms)
        self.assertNotIn("from", forms)
        self.assertNotIn("1000", forms)

    def test_accents_stripped(self):
        tokens = tokenize("Иску́сственный интелле́кт", "ru")
        self.assertEqual([t.norm for t in tokens], ["искусственный", "интеллект"])


class TestWeightFormula(unittest.TestCase):
    def test_matches_manual_computation(self):
        # w = 0.5 * (1 + 8/20) * ln(10/2)
        expected = 0.5 * (1 + 8 / 20) * math.log(10 / 2)
        self.assertAlmostEqual(term_weight(8, 20, 2, 10), expected, places=10)

    def test_term_in_every_document_has_zero_weight(self):
        self.assertEqual(term_weight(30, 30, 10, 10), 0.0)

    def test_weight_grows_with_rarity(self):
        rare = term_weight(5, 20, 1, 10)
        common = term_weight(5, 20, 5, 10)
        self.assertGreater(rare, common)


class TestPositionFunctions(unittest.TestCase):
    class FakeSentence:
        def __init__(self, start, para_start, para_len):
            self.start, self.para_start, self.para_len = start, para_start, para_len

    def test_first_sentence_gets_one(self):
        sentence = self.FakeSentence(0, 0, 500)
        self.assertEqual(position_in_document(sentence, 1000), 1.0)
        self.assertEqual(position_in_paragraph(sentence), 1.0)

    def test_middle_sentence(self):
        sentence = self.FakeSentence(500, 250, 500)
        self.assertAlmostEqual(position_in_document(sentence, 1000), 0.5)
        self.assertAlmostEqual(position_in_paragraph(sentence), 0.5)


class TestMetrics(unittest.TestCase):
    def test_rouge_identical(self):
        tokens = ["a", "b", "c", "d"]
        self.assertAlmostEqual(rouge_n(tokens, tokens, 1).f1, 1.0)
        self.assertAlmostEqual(rouge_l(tokens, tokens).f1, 1.0)

    def test_rouge_disjoint(self):
        self.assertEqual(rouge_n(["a"], ["b"], 1).f1, 0.0)

    def test_agreement(self):
        self.assertEqual(selection_agreement([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertAlmostEqual(selection_agreement([1, 2], [2, 3]), 1 / 3)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collection = Collection.load()

    def test_collection_loaded(self):
        self.assertEqual(self.collection.size, 10)
        self.assertTrue(all(d.sentences for d in self.collection.documents))

    def test_df_never_exceeds_collection_size(self):
        self.assertLessEqual(max(self.collection.df.values()), self.collection.size)

    def test_summary_structure(self):
        document = self.collection.get("ru_cs_ai")
        analysis = analyze(document, self.collection, SummaryParams())
        indices = analysis.primary.indices
        self.assertEqual(len(indices), 10)
        self.assertEqual(indices, sorted(indices))       # порядок исходного текста
        self.assertEqual(len(analysis.keywords), 15)
        for sentence_index in indices:                   # предложения взяты как есть
            self.assertIn(document.sentences[sentence_index].text, analysis.primary.text)

    def test_sentence_weight_equals_product(self):
        document = self.collection.get("en_cs_database")
        params = SummaryParams()
        weights = compute_term_weights(document, self.collection)
        for sentence in score_sentences(document, weights, params):
            self.assertAlmostEqual(sentence.weight,
                                   sentence.posd * sentence.posp * sentence.score, places=9)

    def test_alpha_zero_removes_position_bias(self):
        document = self.collection.get("en_lit_hamlet")
        biased = analyze(document, self.collection, SummaryParams())
        unbiased = analyze(document, self.collection, SummaryParams(alpha=0.0, beta=0.0))
        mean_biased = biased.quality()["position_bias"]["mean_relative_position"]
        mean_unbiased = unbiased.quality()["position_bias"]["mean_relative_position"]
        self.assertGreater(mean_unbiased, mean_biased)

    def test_user_document_extends_collection(self):
        text = ("Квантовые вычисления обещают ускорение переборных задач. " * 12 + "\n\n"
                "Кубит хранит суперпозицию состояний. " * 12)
        document = Document(doc_id="tmp", title="Тест", text=text, language="ru")
        self.collection.add_temporary(document)
        analysis = analyze(document, self.collection, SummaryParams(sentences=3, keywords=5),
                           temporary=True)
        self.assertEqual(analysis.db_size, self.collection.size + 1)
        self.assertLessEqual(len(analysis.primary.indices), 3)

    def test_scs_contains_required_relations(self):
        document = self.collection.get("ru_lit_war_and_peace")
        analysis = analyze(document, self.collection, SummaryParams(sentences=4, keywords=4))
        code = to_scs(analysis)
        for fragment in ("concept_text_document", "nrel_abstract", "nrel_key_word_set",
                         "nrel_text_language", "rrel_1", "nrel_tf_idf_weight", ";;"):
            self.assertIn(fragment, code)
        self.assertEqual(code.count("concept_sentence ->"), 4)
        self.assertEqual(code.count("concept_key_word ->"), 4)

    def test_identifier_transliteration(self):
        self.assertEqual(to_identifier("Война и мир"), "vojna_i_mir")
        self.assertEqual(to_identifier("Computer vision!"), "computer_vision")

    def test_selection_respects_count_and_order(self):
        document = self.collection.get("en_lit_moby_dick")
        params = SummaryParams(sentences=5)
        weights = compute_term_weights(document, self.collection)
        scores = score_sentences(document, weights, params)
        indices = select_sentences(scores, 5)
        self.assertEqual(len(indices), 5)
        self.assertEqual(indices, sorted(indices))

    def test_mmr_reduces_overlap(self):
        document = self.collection.get("en_cs_operating_system")
        weights = compute_term_weights(document, self.collection)
        scores = score_sentences(document, weights, SummaryParams())
        plain = select_sentences(scores, 10, mmr_lambda=1.0)
        diverse = select_sentences(scores, 10, mmr_lambda=0.6)
        self.assertEqual(len(diverse), 10)
        self.assertNotEqual(plain, diverse)


if __name__ == "__main__":
    unittest.main(verbosity=2)
