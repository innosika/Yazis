import pytest

from app.corpus import load_training_corpus
from app.methods import AlphabetDetector, NeuralDetector, NGramDetector
from app.methods.ngram import build_profile, extract_ngrams, out_of_place
from app.preprocessing import html_to_text, normalize

RU = "Москва — столица России, крупнейший по численности населения город страны и её субъект."
EN = "London is the capital and largest city of England and the United Kingdom, located on the Thames."


@pytest.fixture(scope="session")
def corpus():
    corpus, stats = load_training_corpus()
    for lang in ("ru", "en"):
        assert 20_000 <= stats[lang]["bytes"] <= 120_000, "корпус должен быть 20–120 КБ"
    return corpus


@pytest.fixture(scope="session")
def detectors(corpus, tmp_path_factory):
    ds = [NGramDetector(), AlphabetDetector(), NeuralDetector(models_dir=tmp_path_factory.mktemp("m"))]
    for d in ds:
        d.fit(corpus)
    return ds


def test_normalize():
    assert normalize("Привет, Мир! 123 hello_world") == "привет мир hello world"


def test_html_to_text():
    html = "<html><head><style>p{}</style><script>x=1</script></head><body><h1>Заголовок</h1><p>Текст <b>жирный</b>.</p></body></html>"
    assert html_to_text(html) == "Заголовок Текст жирный ."


def test_ngrams_and_out_of_place():
    grams = extract_ngrams("ab")
    assert grams["_ab_"] == 1 and grams["a"] == 1 and grams["_a"] == 1
    lang = build_profile("the the the of of and")
    rank = {g: i for i, g in enumerate(lang)}
    assert out_of_place(lang, rank) == 0
    assert out_of_place(["zzz"], rank) == 300


@pytest.mark.parametrize("text,expected", [(RU, "ru"), (EN, "en")])
def test_all_methods_agree(detectors, text, expected):
    for d in detectors:
        det = d.predict(normalize(text))
        assert det.lang == expected, f"{d.id} ошибся на {expected}"
        assert 0 <= det.confidence <= 1
        assert det.elapsed_ms >= 0


def test_short_text(detectors):
    for d in detectors:
        assert d.predict("привет").lang == "ru"
        assert d.predict("hello").lang == "en"


def test_neural_cache(corpus, tmp_path):
    d1 = NeuralDetector(models_dir=tmp_path); d1.fit(corpus)
    d2 = NeuralDetector(models_dir=tmp_path); d2.fit(corpus)
    assert d2.train_info["hash"] == d1.train_info["hash"]
    assert d1.train_info["val_accuracy"] > 0.97
