"""Normalization rules for computer-science prose, applied in order.

Order matters: a rule only sees text no earlier rule has claimed. Pronunciation
entries come first (the user always wins), then the things that swallow whole spans
(math, URLs, citations, Big-O), then abbreviations and numbers, then symbols, code
identifiers and finally acronyms. Each rule's output is plain words, integers and
light punctuation - the only input the synthesizer's G2P is given.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.text.normalize.engine import Context, Replacer, Rule
from app.text.normalize.mathspeak import GREEK, SYMBOLS, UNICODE_GREEK, speak

LEXICON_FILE = Path(__file__).resolve().parent.parent / "data" / "lexicon.yaml"


@lru_cache(maxsize=1)
def builtin_lexicon() -> tuple[dict[str, str], frozenset[str]]:
    data: dict[str, Any] = yaml.safe_load(LEXICON_FILE.read_text(encoding="utf-8"))
    words = {str(k): str(v) for k, v in (data.get("words") or {}).items()}
    spell = frozenset(str(s) for s in (data.get("spell") or []))
    return words, spell


def _word_pattern(terms: list[str]) -> re.Pattern[str]:
    # Longest first so "PostgreSQL" wins over "SQL".
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w/.-])(?P<term>{alts})(?:-(?P<num>\d+))?(?![\w])")


def _lexicon_replacer(table: dict[str, str]) -> Replacer:
    def replace(m: re.Match[str], _ctx: Context) -> str:
        said = table[m.group("term")]
        return f" {said} {m.group('num')} " if m.group("num") else f" {said} "

    return replace


def _at_end(m: re.Match[str]) -> bool:
    rest = m.string[m.end() :]
    return not rest.strip() or bool(re.match(r"\s+[A-Z]", rest))


# --------------------------------------------------------------------------- lexicon


def user_lexicon_rule(ctx: Context) -> Rule | None:
    if not ctx.lexicon:
        return None
    table = dict(ctx.lexicon)
    return Rule("user-lexicon", _word_pattern(list(table)), _lexicon_replacer(table))


def builtin_lexicon_rule(ctx: Context) -> Rule:
    words, _ = builtin_lexicon()
    if ctx.acronyms == "spell":
        # "Spell every acronym" also overrides the built-in word readings (NASA, SLAM).
        words = {k: v for k, v in words.items() if not re.fullmatch(r"[A-Z]{2,}s?", k)}
    return Rule("lexicon", _word_pattern(list(words)), _lexicon_replacer(words))


# ------------------------------------------------------------------------------ math


def _math(m: re.Match[str], ctx: Context) -> str:
    if ctx.math == "skip":
        return " a formula "
    body = m.group("tex") if m.group("tex") is not None else m.group("dollar")
    spoken = speak(body)
    return f" {spoken} " if spoken else " "


MATH = Rule(
    "math",
    re.compile(r"\\\((?P<tex>.+?)\\\)|\$(?!\d)(?=\S)(?P<dollar>[^$\n]{1,300}?)(?<=\S)\$(?!\d)"),
    _math,
)

# ------------------------------------------------------------------ links, citations


def _url(m: re.Match[str], ctx: Context) -> str:
    if ctx.urls == "skip":
        return " "
    if ctx.urls == "link":
        return " a link "
    host = re.sub(r"^(?:https?://)?(?:www\.)?", "", m[0]).split("/")[0].split("?")[0]
    host = host.split(":")[0]
    return " a link to " + " dot ".join(p for p in host.split(".") if p) + " "


URL = Rule(
    "url",
    re.compile(r"\b(?:https?://|www\.)[^\s<>\"'\])]+(?<![.,;:!?])"),
    _url,
)
EMAIL = Rule(
    "email",
    re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    lambda m, c: " " if c.urls == "skip" else " an email address ",
)


def _citation(m: re.Match[str], ctx: Context) -> str:
    if ctx.citations == "skip":
        return " "
    inner = m[0].strip().strip("[]()")
    inner = re.sub(r"\s*[–-]\s*", " to ", inner)
    inner = re.sub(r"\bet al\.", "et al", inner)
    return f" citing {inner} "


_AUTHOR = r"(?:[A-Z][A-Za-z'’-]+(?:\s(?:and|&)\s[A-Z][A-Za-z'’-]+)?(?:\set\sal\.?)?)"
_YEAR = r"(?:19|20)\d{2}[a-z]?"
CITATION_NUMERIC = Rule(
    "citation-numeric",
    re.compile(r"\s?\[\d+[a-z]?(?:\s*[,;–-]\s*\d+[a-z]?)*\]"),
    _citation,
)
CITATION_ALPHA = Rule(
    "citation-alpha",
    re.compile(
        r"\s?\[[A-Z][A-Za-z+]{1,8}\d{2}[a-z]?(?:\s*[,;]\s*[A-Z][A-Za-z+]{1,8}\d{2}[a-z]?)*\]"
    ),
    _citation,
)
CITATION_AUTHOR_YEAR = Rule(
    "citation-author-year",
    re.compile(
        rf"\s?[(\[](?:(?:see|e\.g\.,?|cf\.)\s)?{_AUTHOR},?\s{_YEAR}(?:[;,]\s?(?:{_AUTHOR},?\s)?{_YEAR})*[)\]]"
    ),
    _citation,
)

# --------------------------------------------------------------------------- Big-O

_BIG_O_NAMES = {
    "O": "big O",
    "Θ": "big theta",
    "Ω": "big omega",
    "o": "little o",
    "ω": "little omega",
    "Theta": "big theta",
    "Omega": "big omega",
}


def _big_o(m: re.Match[str], _ctx: Context) -> str:
    name = _BIG_O_NAMES[m.group("name")]
    return f" {name} of {speak(m.group('arg'))} "


BIG_O = Rule(
    "big-o",
    re.compile(r"(?<![\w\\])\\?(?P<name>O|Θ|Ω|o|ω|Theta|Omega)\((?P<arg>(?:[^()]|\([^()]*\))+)\)"),
    _big_o,
)

# ------------------------------------------------------------------- abbreviations

_ABBR: dict[str, str] = {
    "e.g.": "for example",
    "i.e.": "that is",
    "et al.": "et al",
    "etc.": "etcetera",
    "cf.": "compare",
    "w.r.t.": "with respect to",
    "wrt.": "with respect to",
    "vs.": "versus",
    "resp.": "respectively",
    "approx.": "approximately",
    "a.k.a.": "also known as",
    "s.t.": "such that",
    "i.i.d.": "I I D",
    "w.l.o.g.": "without loss of generality",
    "viz.": "namely",
}
_REF_ABBR: dict[str, str] = {
    "Fig.": "Figure",
    "Figs.": "Figures",
    "Eq.": "Equation",
    "Eqs.": "Equations",
    "Sec.": "Section",
    "Secs.": "Sections",
    "Tab.": "Table",
    "Alg.": "Algorithm",
    "Thm.": "Theorem",
    "Def.": "Definition",
    "Lem.": "Lemma",
    "Prop.": "Proposition",
    "Cor.": "Corollary",
    "Ref.": "Reference",
    "Refs.": "References",
    "Ch.": "Chapter",
    "Chap.": "Chapter",
    "App.": "Appendix",
    "Appx.": "Appendix",
    "Vol.": "Volume",
    "No.": "number",
    "pp.": "pages",
    "p.": "page",
    "Ex.": "Example",
}
_TITLES = {
    "Dr.": "Doctor",
    "Prof.": "Professor",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Ms.": "Miz",
    "St.": "Saint",
}


def _abbr(m: re.Match[str], _ctx: Context) -> str:
    word = _ABBR[m[0].lower()]
    if m[0][0].isupper() and word[0].islower():
        word = word[0].upper() + word[1:]
    return f" {word}. " if _at_end(m) and m[0].lower() in {"etc.", "et al."} else f" {word} "


ABBREVIATIONS = Rule(
    "abbreviations",
    re.compile(
        r"(?<![\w.])(?:"
        + "|".join(re.escape(k) for k in sorted(_ABBR, key=len, reverse=True))
        + r")(?!\w)",
        re.IGNORECASE,
    ),
    _abbr,
)


def _ref_abbr(m: re.Match[str], _ctx: Context) -> str:
    word = _REF_ABBR[m.group("abbr")]
    num = m.group("num")
    num = re.sub(r"[()]", " ", num)
    num = re.sub(r"(\d)\.(\d)", r"\1 point \2", num)
    num = re.sub(r"(\d)([a-z])\b", r"\1 \2", num)
    num = re.sub(r"\s*[–-]\s*", " to ", num)
    return f" {word} {num.strip()} "


REF_ABBREVIATIONS = Rule(
    "reference-abbreviations",
    re.compile(
        r"(?<![\w.])(?P<abbr>"
        + "|".join(re.escape(k) for k in _REF_ABBR)
        + r")\s?(?P<num>\(\d+(?:\.\d+)*[a-z]?\)|\d+(?:\.\d+)*(?:[a-z]\b|\([a-z]\))?(?:\s?[–-]\s?\d+(?:\.\d+)*[a-z]?)?)"
    ),
    _ref_abbr,
)
# "Figure 3(b)", "Equation (2)", "Section 4.1" written out in full.
_REF_WORDS = "Figure|Figures|Equation|Equations|Section|Sections|Table|Tables|Algorithm|Appendix|Theorem|Lemma|Chapter|Line|Lines|Step"
REF_WORDS = Rule(
    "reference-words",
    re.compile(
        rf"\b(?P<w>{_REF_WORDS})\s(?P<num>\(\d+(?:\.\d+)*\)|\d+(?:\.\d+)*(?:\([a-z]\)|[a-z]\b)?)"
    ),
    lambda m, c: " {} {} ".format(
        m.group("w"),
        re.sub(r"(\d)\.(\d)", r"\1 point \2", re.sub(r"[()]", " ", m.group("num"))).strip(),
    ),
)
TITLES = Rule(
    "titles",
    re.compile(r"(?<![\w.])(?:Dr|Prof|Mr|Mrs|Ms|St)\.(?=\s[A-Z])"),
    lambda m, c: f" {_TITLES[m[0]]} ",
)
VERSUS = Rule("versus", re.compile(r"(?<![\w.])vs(?!\w|\.\d)"), lambda m, c: " versus ")

# -------------------------------------------------------------------------- numbers

_UNITS: dict[str, tuple[str, str]] = {
    "KB": ("kilobyte", "kilobytes"),
    "MB": ("megabyte", "megabytes"),
    "GB": ("gigabyte", "gigabytes"),
    "TB": ("terabyte", "terabytes"),
    "PB": ("petabyte", "petabytes"),
    "KiB": ("kibibyte", "kibibytes"),
    "MiB": ("mebibyte", "mebibytes"),
    "GiB": ("gibibyte", "gibibytes"),
    "TiB": ("tebibyte", "tebibytes"),
    "Kb": ("kilobit", "kilobits"),
    "Mb": ("megabit", "megabits"),
    "Gb": ("gigabit", "gigabits"),
    "kbps": ("kilobit per second", "kilobits per second"),
    "Kbps": ("kilobit per second", "kilobits per second"),
    "Mbps": ("megabit per second", "megabits per second"),
    "Gbps": ("gigabit per second", "gigabits per second"),
    "Hz": ("hertz", "hertz"),
    "kHz": ("kilohertz", "kilohertz"),
    "MHz": ("megahertz", "megahertz"),
    "GHz": ("gigahertz", "gigahertz"),
    "ns": ("nanosecond", "nanoseconds"),
    "µs": ("microsecond", "microseconds"),
    "μs": ("microsecond", "microseconds"),
    "us": ("microsecond", "microseconds"),
    "ms": ("millisecond", "milliseconds"),
    "sec": ("second", "seconds"),
    "secs": ("second", "seconds"),
    "s": ("second", "seconds"),
    "min": ("minute", "minutes"),
    "mins": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "hr": ("hour", "hours"),
    "hrs": ("hour", "hours"),
    "px": ("pixel", "pixels"),
    "fps": ("frame per second", "frames per second"),
    "dpi": ("dot per inch", "dots per inch"),
    "dB": ("decibel", "decibels"),
    "W": ("watt", "watts"),
    "kW": ("kilowatt", "kilowatts"),
    "mW": ("milliwatt", "milliwatts"),
    "nm": ("nanometer", "nanometers"),
    "mm": ("millimeter", "millimeters"),
    "cm": ("centimeter", "centimeters"),
    "km": ("kilometer", "kilometers"),
    "kg": ("kilogram", "kilograms"),
    "°C": ("degree Celsius", "degrees Celsius"),
    "K": ("thousand", "thousand"),
    "k": ("thousand", "thousand"),
    "M": ("million", "million"),
    "B": ("billion", "billion"),
    "T": ("trillion", "trillion"),
    "%": ("percent", "percent"),
}


def _spoken_number(num: str) -> str:
    num = num.replace(",", "")
    if "." in num:
        whole, frac = num.split(".", 1)
        return f"{whole or '0'} point {' '.join(frac)}"
    return num


def _unit(m: re.Match[str], _ctx: Context) -> str:
    num, unit = m.group("num"), m.group("unit")
    singular, plural = _UNITS[unit]
    word = singular if num.replace(",", "") in {"1", "1.0"} else plural
    return f" {_spoken_number(num)} {word} "


# Bare "s" and "h" only count as units when separated by a space ("10 s", not "1990s").
UNITS = Rule(
    "units",
    re.compile(
        r"(?<![\w.])(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
        r"(?:\s?(?P<unit>"
        + "|".join(
            re.escape(u) for u in sorted(_UNITS, key=len, reverse=True) if u not in {"s", "h", "%"}
        )
        + r")(?![\w])|\s(?P<unit_s>s|h)(?![\w])|\s?(?P<pct>%))"
        # "82M-parameter model": the hyphen joins a compound, it is not a minus sign.
        r"(?:-(?=[A-Za-z]))?"
    ),
    lambda m, c: _unit_dispatch(m, c),
)


def _unit_dispatch(m: re.Match[str], ctx: Context) -> str:
    num = m.group("num")
    if m.group("pct"):
        return f" {_spoken_number(num)} percent "
    unit = m.group("unit") or m.group("unit_s")
    singular, plural = _UNITS[unit]
    word = singular if num in {"1", "1.0"} else plural
    return f" {_spoken_number(num)} {word} "


SCIENTIFIC = Rule(
    "scientific",
    re.compile(
        r"(?<![\w.])(?P<m>\d+(?:\.\d+)?)(?:[eE](?P<e1>[+-]?\d+)|\s?[×x·]\s?10\^\{?(?P<e2>[+−-]?\d+)\}?)(?![\w])"
    ),
    lambda m, c: " {} times ten to the {} ".format(
        _spoken_number(m.group("m")),
        _exponent(m.group("e1") or m.group("e2") or "0"),
    ),
)
POWER_OF_TEN = Rule(
    "power-of-ten",
    re.compile(r"(?<![\w.])10\^\{?(?P<e>[+−-]?\d+)\}?(?![\w])"),
    lambda m, c: f" ten to the {_exponent(m.group('e'))} ",
)


def _exponent(e: str) -> str:
    e = e.replace("−", "-").lstrip("+")
    return f"minus {e[1:]}" if e.startswith("-") else e


DIMENSIONS = Rule(
    "dimensions",
    re.compile(r"(?<![\w.])(\d+)\s?[x×]\s?(\d+)(?:\s?[x×]\s?(\d+))?(?!\w|\.\d)"),
    lambda m, c: " " + " by ".join(g for g in m.groups() if g) + " ",
)
TIMES = Rule(
    "times",
    re.compile(r"(?<![\w.])(?P<num>\d+(?:\.\d+)?)\s?[x×](?![\w])"),
    lambda m, c: f" {_spoken_number(m.group('num'))} times ",
)
CURRENCY = Rule(
    "currency",
    re.compile(
        r"\$(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(?P<mult>[KMBT]|thousand|million|billion)?\b"
    ),
    lambda m, c: " {} {}dollars ".format(
        _spoken_number(m.group("num")),
        (_UNITS[m.group("mult")][1] + " ")
        if m.group("mult") in _UNITS
        else ((m.group("mult") + " ") if m.group("mult") else ""),
    ),
)
RANGE = Rule(
    "range",
    re.compile(
        r"(?<![\w.])(?:(?P<a>\d+)\s?[–—]\s?(?P<b>\d+)|(?P<c>(?:19|20)\d{2})-(?P<d>(?:19|20)\d{2}))(?!\w|\.\d)"
    ),
    lambda m, c: " {} to {} ".format(m.group("a") or m.group("c"), m.group("b") or m.group("d")),
)
_PRODUCTS = (
    "Python|Java|CUDA|PyTorch|TensorFlow|Ubuntu|Debian|Linux|HTTP|Node|React|Vue|Angular|iOS|"
    "Android|Windows|macOS|GPT|Llama|LLaMA|Gemini|Claude|Mistral|Qwen|Unicode|OpenGL|Vulkan|"
    "Bluetooth|USB|PHP|Perl|Ruby|Go|Rust|Swift|Kotlin|Scala|Julia|MATLAB|Spark|Hadoop|Kafka|"
    "Docker|Kubernetes|Postgres|PostgreSQL|MySQL|Redis|Django|Flask|Rails|NumPy|pandas|spaCy|"
    "ES|ECMAScript|HTML|CSS|TLS|SSL|OAuth|IPv|Chrome|Firefox|Safari|Edge|GCC|LLVM|Clang|Qt|GTK"
)


def _product_version(m: re.Match[str], _ctx: Context) -> str:
    words, _ = builtin_lexicon()
    name = m.group("name")
    return f" {words.get(name, name)} " + " point ".join(m.group("v").split(".")) + " "


PRODUCT_VERSION = Rule(
    "product-version",
    re.compile(rf"(?<![\w])(?P<name>{_PRODUCTS})[\s-]v?(?P<v>\d+(?:\.\d+)+)(?!\w|\.\d)"),
    _product_version,
)
VERSION = Rule(
    "version",
    re.compile(r"(?<![\w.])(?:[vV](?P<a>\d+(?:\.\d+)*)|(?P<b>\d+\.\d+\.\d+(?:\.\d+)*))(?!\w|\.\d)"),
    lambda m, c: (
        " version " + " point ".join((m.group("a") or "").split(".")) + " "
        if m.group("a") is not None
        else " " + " point ".join(m.group("b").split(".")) + " "
    ),
)
DECIMAL = Rule(
    "decimal",
    re.compile(r"(?<![\w.])(?P<num>\d*\.\d+)(?!\w|\.\d)"),
    lambda m, c: f" {_spoken_number(m.group('num'))} ",
)
THOUSANDS = Rule(
    "thousands",
    re.compile(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?![\w,])"),
    lambda m, c: " " + m[0].replace(",", "") + " ",
)
FRACTION = Rule(
    "fraction",
    re.compile(r"(?<![\w./])(?P<a>\d+)/(?P<b>\d+)(?![\w./])"),
    lambda m, c: f" {m.group('a')} over {m.group('b')} ",
)
PER_UNIT = Rule(
    "per-unit",
    re.compile(
        r"/(?P<u>s|sec|second|ms|min|h|hr|hour|day|epoch|step|iter|iteration|token|GPU|core|query|request|sample|image)\b"
    ),
    lambda m, c: " per {} ".format(
        {
            "s": "second",
            "sec": "second",
            "ms": "millisecond",
            "min": "minute",
            "h": "hour",
            "hr": "hour",
            "iter": "iteration",
        }.get(m.group("u"), m.group("u"))
    ),
)

# ---------------------------------------------------------------- scripts & symbols

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ", "0123456789+-ni")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋ᵢⱼₖₙ", "0123456789+-ijkn")

POWER = Rule(
    "power",
    re.compile(
        r"(?<![\w\\])(?P<base>[A-Za-z]{1,2}|\d+|\))\^(?P<exp>\{[^{}]{1,20}\}|[A-Za-z0-9]+|[+−-]\d+)"
    ),
    lambda m, c: f" {speak(m[0])} ",
)
SUBSCRIPT = Rule(
    "subscript",
    re.compile(
        r"(?<![\w\\])(?P<base>[A-Za-z])_(?P<sub>\{[^{}]{1,20}\}|[A-Za-z0-9]+)(?:\^(?P<exp>\{[^{}]{1,20}\}|[A-Za-z0-9]+))?"
    ),
    lambda m, c: f" {speak(m[0])} ",
)
CONDITIONAL = Rule(
    "conditional",
    re.compile(r"(?<![\w\\])[A-Za-z]\([^()|]{1,30}\|[^()]{1,30}\)"),
    lambda m, c: f" {speak(m[0])} ",
)
UNICODE_SCRIPTS = Rule(
    "unicode-scripts",
    re.compile(
        r"(?P<base>[A-Za-z0-9)])(?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ]+)|(?P<base2>[A-Za-z])(?P<sub>[₀₁₂₃₄₅₆₇₈₉ᵢⱼₖₙ]+)"
    ),
    lambda m, c: (
        " "
        + (
            speak(f"{m.group('base')}^{{{m.group('sup').translate(_SUP)}}}")
            if m.group("sup")
            else speak(f"{m.group('base2')}_{{{m.group('sub').translate(_SUB)}}}")
        )
        + " "
    ),
)
GREEK_LETTERS = Rule(
    "greek",
    re.compile("[" + "".join(UNICODE_GREEK) + "]"),
    lambda m, c: f" {UNICODE_GREEK[m[0]]} ",
)
LATEX_COMMAND = Rule(
    "latex-command",
    re.compile(r"\\(?P<name>" + "|".join(GREEK) + r")\b"),
    lambda m, c: f" {GREEK[m.group('name')]} ",
)
_ASCII_OPS = {
    "<=": "less than or equal to",
    ">=": "greater than or equal to",
    "!=": "not equal to",
    "==": "equals",
    "->": "to",
    "=>": "implies",
    "<->": "if and only if",
    "<-": "from",
    "~": "approximately",
    "≈": "approximately",
}
ASCII_OPERATORS = Rule(
    "ascii-operators",
    re.compile(r"(?<=\s)(?:<->|<=|>=|!=|==|->|=>|<-)(?=\s)|(?<![\w~])~(?=\s?\d)|≈(?=\s?\d)"),
    lambda m, c: f" {_ASCII_OPS[m[0]]} ",
)
_SPACED_OPS = {"<": "less than", ">": "greater than", "=": "equals", "+": "plus", "*": "times"}
SPACED_OPERATORS = Rule(
    "spaced-operators",
    re.compile(r"(?<!\S)(?P<op>[<>=+*])(?!\S)"),
    lambda m, c: f" {_SPACED_OPS[m.group('op')]} ",
)
MATH_SYMBOLS = Rule(
    "math-symbols",
    re.compile("[" + re.escape("".join(k for k, v in SYMBOLS.items() if len(k) == 1)) + "]"),
    lambda m, c: f" {SYMBOLS[m[0]]} " if SYMBOLS[m[0]] else " ",
)
DASHES = Rule(
    "dashes",
    re.compile(r"\s[–—]\s|—|(?<=\w)–(?=\w)"),
    lambda m, c: " " if m[0] == "–" else ", ",
)
AMPERSAND = Rule("ampersand", re.compile(r"(?<=\s)&(?=\s)|(?<=\w)&(?=\w)"), lambda m, c: " and ")
AT_SIGN = Rule("at", re.compile(r"(?<=\s)@(?=\w)"), lambda m, c: " at ")
NUMBER_SIGN = Rule(
    "number-sign",
    re.compile(r"#(?=\s?\d)|#(?=[a-z])"),
    lambda m, c: " number of " if m.string[m.end() : m.end() + 1].isalpha() else " number ",
)
SLASH = Rule(
    "slash",
    re.compile(r"(?<=[A-Za-z])/(?=[A-Za-z])"),
    lambda m, c: " or " if m.string[max(0, m.start() - 3) : m.start()] == "and" else " ",
)
FOOTNOTE_MARKS = Rule(
    "footnote-marks", re.compile(r"[†‡§¶]|(?<=\w)\*(?=[\s,.;:)]|$)"), lambda m, c: " "
)
ROMAN_ENUM = Rule(
    "roman-enumeration",
    re.compile(r"\((?P<r>i|ii|iii|iv|v|vi|vii|viii|ix|x)\)"),
    lambda m, c: " {} , ".format(
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][
            ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"].index(m.group("r"))
        ]
    ),
)

# -------------------------------------------------------------------- code & names


def _split_identifier(word: str) -> str:
    parts = re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", word)
    return " ".join(p if p.isupper() and len(p) > 1 else p.lower() for p in parts if p)


BACKTICK_CODE = Rule(
    "backtick-code",
    re.compile(r"`([^`\n]{1,80})`"),
    lambda m, c: (
        " " + re.sub(r"[()\[\]{};]", " ", _split_identifier(m.group(1)).replace(".", " dot ")) + " "
    ),
)
FILE_NAME = Rule(
    "file-name",
    re.compile(
        r"(?<![\w/])(?P<name>[\w-]+)\.(?P<ext>py|js|ts|tsx|jsx|cpp|cc|hpp|java|rs|go|rb|md|json|yaml|yml|toml|txt|csv|pdf|html|css|sh|ipynb|onnx|pt|pth|h5|c|h)(?![\w])"
    ),
    lambda m, c: f" {_split_identifier(m.group('name'))} dot {m.group('ext')} ",
)
FUNCTION_CALL = Rule(
    "function-call",
    re.compile(r"(?<![\w.])(?P<name>[a-z_][\w]*)\(\)"),
    lambda m, c: f" {_split_identifier(m.group('name'))} ",
)
SNAKE_CASE = Rule(
    "snake-case",
    re.compile(r"(?<![\w])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![\w])"),
    lambda m, c: f" {_split_identifier(m[0])} ",
)
CAMEL_CASE = Rule(
    "camel-case",
    re.compile(r"(?<![\w])[a-z]+(?:[A-Z][a-z0-9]+)+(?![\w])"),
    lambda m, c: f" {_split_identifier(m[0])} ",
)

# ----------------------------------------------------------------------- acronyms

_ONSETS = {
    "BL",
    "BR",
    "CL",
    "CR",
    "DR",
    "FL",
    "FR",
    "GL",
    "GR",
    "PL",
    "PR",
    "SC",
    "SK",
    "SL",
    "SM",
    "SN",
    "SP",
    "ST",
    "SW",
    "TR",
    "TW",
    "TH",
    "CH",
    "SH",
    "WH",
    "PH",
    "QU",
    "STR",
    "SPR",
    "SCR",
    "SPL",
    "SQU",
    "THR",
    "SHR",
}
_VOWELS = set("AEIOUY")


def pronounceable(word: str) -> bool:
    """Would an English reader say this all-caps acronym as a word (NASA, SLAM)?"""
    w = word.upper()
    if len(w) <= 3 or not any(c in _VOWELS for c in w):
        return False
    lead = re.match(r"[^AEIOUY]*", w)
    onset = lead.group(0) if lead else ""
    if len(onset) >= 2 and onset not in _ONSETS:
        return False
    if re.search(r"[^AEIOUY]{3,}", w[len(onset) :]):
        return False
    return not re.search(r"[AEIOU]{3,}", w)


def _spell(letters: str) -> str:
    out = []
    for ch in letters:
        if ch.isdigit():
            out.append(ch)
        elif ch.upper() == "A":
            out.append("ay")
        else:
            out.append(ch.upper())
    return " ".join(out)


def _acronym(m: re.Match[str], ctx: Context) -> str | None:
    word, plural = m.group("w"), m.group("pl") or ""
    _, spell_list = builtin_lexicon()
    head = re.match(r"[A-Z]+", word)
    letters = head.group(0) if head else word
    digits = word[len(letters) :]
    listed = word + plural in spell_list or word in spell_list
    if ctx.acronyms != "spell" and not listed and not digits and pronounceable(letters):
        return f" {(word + plural).lower()} "
    spelled = _spell(letters)
    if plural:
        spelled += "'s"
    if digits:
        spelled += " " + " ".join(re.findall(r"\d+|[A-Z]+", digits))
    return f" {spelled} "


ACRONYM = Rule(
    "acronym",
    re.compile(r"(?<![\w'’-])(?P<w>[A-Z]{2,}\d*(?:[A-Z]+\d*)*|[A-Z]\d+[A-Z]*)(?P<pl>s)?(?![\w'’])"),
    _acronym,
)
ACRONYM_HYPHEN = Rule(
    "acronym-hyphen-number",
    re.compile(r"(?<=[A-Z])-(?=\d)"),
    lambda m, c: " ",
)

# ------------------------------------------------------------------------- headings

HEADING_NUMBER = Rule(
    "heading-number",
    re.compile(r"^\s*(?P<n>(?:\d+|[A-Z]|[IVX]+)(?:\.\d+)*)\.?(?=\s)"),
    lambda m, c: (
        " Section {}. ".format(" point ".join(m.group("n").split("."))) if c.heading else None
    ),
)


def rules_for(ctx: Context) -> list[Rule]:
    rules: list[Rule] = []
    user = user_lexicon_rule(ctx)
    if user is not None:
        rules.append(user)
    rules += [
        HEADING_NUMBER,
        MATH,
        URL,
        EMAIL,
        CITATION_NUMERIC,
        CITATION_ALPHA,
        CITATION_AUTHOR_YEAR,
        BIG_O,
        PRODUCT_VERSION,
        builtin_lexicon_rule(ctx),
        BACKTICK_CODE,
        FILE_NAME,
        FUNCTION_CALL,
        REF_ABBREVIATIONS,
        REF_WORDS,
        ABBREVIATIONS,
        TITLES,
        VERSUS,
        ROMAN_ENUM,
        ASCII_OPERATORS,
        CURRENCY,
        SCIENTIFIC,
        POWER_OF_TEN,
        DIMENSIONS,
        TIMES,
        UNITS,
        RANGE,
        VERSION,
        FRACTION,
        PER_UNIT,
        THOUSANDS,
        DECIMAL,
        CONDITIONAL,
        UNICODE_SCRIPTS,
        SUBSCRIPT,
        POWER,
        LATEX_COMMAND,
        GREEK_LETTERS,
        SPACED_OPERATORS,
        MATH_SYMBOLS,
        DASHES,
        AMPERSAND,
        AT_SIGN,
        NUMBER_SIGN,
        SLASH,
        FOOTNOTE_MARKS,
        SNAKE_CASE,
        CAMEL_CASE,
        ACRONYM_HYPHEN,
        ACRONYM,
    ]
    return rules
