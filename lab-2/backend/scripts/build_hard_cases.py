"""Сложные документы для тестовой коллекции — случаи, на которых методы ошибаются.

Каждый документ получает истинный язык (ru/en), группу "hard" и пояснение, чем он сложен.
Запуск: python scripts/build_hard_cases.py  (дописывает hard_*.html в data/test и обновляет manifest.json)
"""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
TEST_DIR = DATA_DIR / "test"

# --- вспомогательные преобразования -------------------------------------------------
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}
HOMOGLYPH_RU2LAT = str.maketrans("аеорсухАЕОРСУХ", "aeopcyxAEOPCYX")
HOMOGLYPH_LAT2RU = str.maketrans("aeopcyxAEOPCYX", "аеорсухАЕОРСУХ")


def translit(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in TRANSLIT:
            t = TRANSLIT[low]
            out.append(t.capitalize() if ch.isupper() else t)
        else:
            out.append(ch)
    return "".join(out)


def first_paragraphs(path: Path, n_chars: int) -> str:
    text = path.read_text(encoding="utf-8")
    text = text.split("\n", 1)[1] if text.startswith("#") else text
    paras = [p for p in text.split("\n") if len(p) > 80]
    acc, out = 0, []
    for p in paras:
        out.append(p); acc += len(p)
        if acc >= n_chars:
            break
    return "\n".join(out)


def strip_html_paragraphs(path: Path, n_chars: int) -> str:
    raw = path.read_text(encoding="utf-8")
    paras = re.findall(r"<p>(.*?)</p>", raw, flags=re.S)
    paras = [html.unescape(p) for p in paras if not p.startswith("Источник")]
    acc, out = 0, []
    for p in paras:
        out.append(p); acc += len(p)
        if acc >= n_chars:
            break
    return "\n".join(out)


# --- тексты, написанные вручную -----------------------------------------------------
RU_IT_MIXED = """Мы мигрировали backend с Django REST Framework на FastAPI, потому что async endpoints и Pydantic models дают заметный прирост throughput. Deploy идёт через GitHub Actions: build Docker image, push в registry, затем rolling update в Kubernetes cluster. Для кэширования используем Redis, для очередей — RabbitMQ, а логи собираем в Elasticsearch через Filebeat.
Frontend написан на React с TypeScript. State management — Redux Toolkit, роутинг — React Router, стили — Tailwind CSS. Тесты: Jest и React Testing Library для unit tests, Playwright для e2e. CI прогоняет lint, type-check и coverage report на каждый pull request.
Monitoring: Prometheus собирает metrics, Grafana строит dashboards, alerts уходят в Slack. Для tracing используем OpenTelemetry. SLA по latency держим на уровне p95 меньше 200 ms.
Code review обязателен: минимум два approve от senior developers. Merge только через squash, commit message по Conventional Commits. Release notes генерируются автоматически из changelog."""

EN_RU_NAMES = """Fyodor Dostoevsky wrote Преступление и наказание in 1866, and its protagonist Родион Раскольников has become one of the most discussed characters in world literature. The novel first appeared in the journal Русский вестник, edited by Михаил Катков. Dostoevsky's later works — Идиот, Бесы and Братья Карамазовы — were written in Санкт-Петербург and Старая Русса.
Leo Tolstoy (Лев Николаевич Толстой) began Война и мир in 1863 at his estate Ясная Поляна. The opening chapters, set in the salon of Анна Павловна Шерер, are famously written partly in French. Tolstoy later renounced his novels, writing Исповедь and В чём моя вера?
Anton Chekhov (Антон Павлович Чехов) transformed the short story and the stage: Чайка, Дядя Ваня, Три сестры and Вишнёвый сад premiered at the Московский Художественный театр under Константин Станиславский and Владимир Немирович-Данченко."""

RU_SHORT = "Купил iPhone 15 Pro и MacBook Air в DNS, доставка через СДЭК до Wildberries-пункта — ок?"
EN_SHORT = "Ok, c u at 5 by the café near Тверская — bring the USB-C cable pls :)"

EN_SMS = """hey m8 how r u? i m gr8 thx. did u c the game l8r? omg it was lit af, ngl. btw r we still on 4 2nite? idk if jen can make it, she s kinda busy w/ work rn. lmk asap pls.
brb gotta go, ttyl. oh n dont 4get 2 bring da snacks lol. cya! xoxo
ps: ur pic on ig was fire fr fr, no cap. tbh i cant even. gg wp. afk 4 a bit, bbl. imho da new update sux, smh. ftw tho, yolo. rofl."""

RU_OLD = """Въ началѣ было Слово, и Слово было у Бога, и Слово было Богъ. Оно было въ началѣ у Бога. Все чрезъ Него начало быть, и безъ Него ничто не начало быть, что начало быть.
Въ Немъ была жизнь, и жизнь была свѣтъ человѣковъ. И свѣтъ во тьмѣ свѣтитъ, и тьма не объяла его. Былъ человѣкъ, посланный отъ Бога; имя ему Іоаннъ.
Онъ пришелъ для свидѣтельства, чтобы свидѣтельствовать о Свѣтѣ, дабы всѣ увѣровали чрезъ него. Онъ не былъ свѣтъ, но былъ посланъ, чтобы свидѣтельствовать о Свѣтѣ. Былъ Свѣтъ истинный, Который просвѣщаетъ всякаго человѣка, приходящаго въ міръ. Въ мірѣ былъ, и міръ чрезъ Него началъ быть, и міръ Его не позналъ."""

RU_CODE = '''# Загружаем конфигурацию и запускаем обработку очереди
import asyncio
import json
from pathlib import Path

CONFIG_PATH = Path("config.json")  # путь к файлу настроек


def load_config(path: Path) -> dict:
    """Читает настройки из JSON. Если файла нет — возвращает значения по умолчанию."""
    if not path.exists():
        return {"workers": 4, "timeout": 30}
    return json.loads(path.read_text(encoding="utf-8"))


async def worker(name: str, queue: asyncio.Queue) -> None:
    # Каждый воркер берёт задачу из очереди и обрабатывает её
    while True:
        task = await queue.get()
        try:
            await asyncio.sleep(task["delay"])  # имитация полезной работы
            print(f"{name}: задача {task['id']} выполнена")
        finally:
            queue.task_done()


async def main() -> None:
    config = load_config(CONFIG_PATH)
    queue: asyncio.Queue = asyncio.Queue()
    for i in range(10):
        queue.put_nowait({"id": i, "delay": 0.1})  # добавляем задачи
    workers = [asyncio.create_task(worker(f"worker-{n}", queue)) for n in range(config["workers"])]
    await queue.join()  # ждём, пока очередь опустеет
    for w in workers:
        w.cancel()


if __name__ == "__main__":
    asyncio.run(main())'''

EN_IN_CYRILLIC = """Хеллоу эврибади, май нейм из Джон энд ай эм фром Лондон. Ай лайк ту трэвел энд мит нью пипл. Ласт саммер ай визитед Москоу энд Сэнт-Питерсбург — ит воз эмейзинг!
Ай спик инглиш, э литтл бит оф спэниш энд ай эм лёрнинг рашн нау. Ит из вери дификалт бикоз оф зе кейсес энд зе вербс оф моушн, бат ай трай май бест эври дэй.
Ин май фри тайм ай плей гитар энд рид букс. Май фэйворит райтер из Джордж Оруэлл. Вот эбаут ю? Ду ю лайк ридинг? Лет ми ноу ин зе комментс билоу энд донт форгет ту сабскрайб."""

EN_WITH_PROVERBS = """Russian proverbs often surprise English speakers with their imagery. Where we say "when pigs fly", a Russian says «когда рак на горе свистнет» — when the crayfish whistles on the mountain. Our "kill two birds with one stone" becomes «убить двух зайцев» — to kill two hares.
Some sayings translate almost literally: «не всё то золото, что блестит» is "all that glitters is not gold", and «лучше поздно, чем никогда» is "better late than never". Others have no equivalent at all: «на безрыбье и рак — рыба» ("when there is no fish, even a crayfish is a fish") describes making do with what you have.
Learners love «первый блин комом» — "the first pancake is a lump", meaning first attempts rarely succeed — and «без труда не вытащишь и рыбку из пруда», "without effort you won't even pull a fish out of the pond". Perhaps the most famous is «тише едешь — дальше будешь»: "the slower you go, the further you'll get"."""


def page(title: str, lang: str, text: str, note: str) -> str:
    paras = "\n".join(f"    <p>{html.escape(p)}</p>" for p in text.split("\n") if p.strip())
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="description" content="Сложный документ: {html.escape(note)}">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 720px; margin: 40px auto; line-height: 1.55; color: #222; }}
  h1 {{ font-size: 1.6rem; }} .note {{ color: #92400e; background: #fffbeb; padding: 8px 12px; border-radius: 6px; font-size: .9rem; }}
  pre {{ white-space: pre-wrap; }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
{paras}
</body>
</html>
"""


def main() -> None:
    ru_para = first_paragraphs(DATA_DIR / "train" / "ru" / "ru_07.txt", 900)   # Байкал
    en_para = strip_html_paragraphs(TEST_DIR / "en_05.html", 900)              # Antarctica
    cases = [
        ("hard_01", "ru", "Русский текст в транслите", translit(ru_para),
         "русский текст записан латиницей (транслит); алфавитный метод видит только латинские буквы"),
        ("hard_02", "ru", "Русский текст с латинскими гомоглифами", ru_para.translate(HOMOGLYPH_RU2LAT),
         "буквы а, е, о, р, с, у, х заменены на похожие латинские a, e, o, p, c, y, x — приём спам-обфускации"),
        ("hard_03", "en", "English text with Cyrillic homoglyphs", en_para.translate(HOMOGLYPH_LAT2RU),
         "латинские a, e, o, p, c, y, x заменены на кириллические гомоглифы; текст выглядит как английский, но половина букв — кириллица"),
        ("hard_04", "ru", "Русская статья, перегруженная IT-терминами", RU_IT_MIXED,
         "русский текст, где больше трети слов — английские технические термины и названия"),
        ("hard_05", "en", "English essay with Russian titles and names", EN_RU_NAMES,
         "английский текст с большим числом кириллических названий, имён и цитат"),
        ("hard_06", "ru", "Короткое сообщение с брендами", RU_SHORT,
         "очень короткий русский текст, наполовину состоящий из латинских названий брендов"),
        ("hard_07", "en", "Short chat message", EN_SHORT,
         "очень короткое английское сообщение с сокращениями и одним кириллическим словом"),
        ("hard_08", "en", "English SMS slang", EN_SMS,
         "английский интернет-сленг: сокращения и цифры вместо слов не встречаются в тренировочном корпусе"),
        ("hard_09", "ru", "Русский текст в дореформенной орфографии", RU_OLD,
         "орфография до 1918 года: буквы ѣ, і, ъ на конце слов отсутствуют в современном алфавите и корпусе"),
        ("hard_10", "ru", "Python-код с русскими комментариями", RU_CODE,
         "исходный код: английские ключевые слова и идентификаторы против русских комментариев и строк"),
        ("hard_11", "en", "English written in Cyrillic letters", EN_IN_CYRILLIC,
         "английская речь, записанная кириллицей по звучанию: алфавит русский, а N-граммы и лексика — английские"),
        ("hard_12", "en", "English article quoting Russian proverbs", EN_WITH_PROVERBS,
         "английская статья, примерно на 40% состоящая из русских цитат"),
    ]
    manifest_path = TEST_DIR / "manifest.json"
    manifest = [m for m in json.loads(manifest_path.read_text(encoding="utf-8")) if not m["id"].startswith("hard_")]
    for f in TEST_DIR.glob("hard_*.html"):
        f.unlink()
    for doc_id, lang, title, text, note in cases:
        (TEST_DIR / f"{doc_id}.html").write_text(page(title, lang, text, note), encoding="utf-8")
        manifest.append({"id": doc_id, "file": f"{doc_id}.html", "title": title, "lang": lang,
                         "source": "synthetic", "chars": len(text), "group": "hard", "note": note})
        print(f"  {doc_id} [{lang}] {title} — {len(text)} симв.")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest: {len(manifest)} документов")


if __name__ == "__main__":
    main()
