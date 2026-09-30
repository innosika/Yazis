"""Turn a short math expression (LaTeX or plain text) into words a speaker would say.

Covers what shows up in CS papers inline: variables with sub- and superscripts,
fractions, roots, sums and products with limits, relations, set operations, Greek
letters, decorations (hat, bar, tilde), common functions, norms and absolute values,
and conditional bars. It is deliberately a reader, not a full TeX parser: anything it
does not know it reads by its name, and it never raises.

    >>> speak(r"\\frac{QK^{T}}{\\sqrt{d_{k}}}")
    'Q K transpose over square root of d sub k'
    >>> speak("n log n")
    'n log n'
"""

from __future__ import annotations

import re

GREEK = {
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "delta": "delta",
    "epsilon": "epsilon",
    "varepsilon": "epsilon",
    "zeta": "zeta",
    "eta": "eta",
    "theta": "theta",
    "vartheta": "theta",
    "iota": "iota",
    "kappa": "kappa",
    "lambda": "lambda",
    "mu": "mu",
    "nu": "nu",
    "xi": "xi",
    "pi": "pi",
    "rho": "rho",
    "sigma": "sigma",
    "tau": "tau",
    "upsilon": "upsilon",
    "phi": "phi",
    "varphi": "phi",
    "chi": "chi",
    "psi": "psi",
    "omega": "omega",
    "Gamma": "capital gamma",
    "Delta": "capital delta",
    "Theta": "capital theta",
    "Lambda": "capital lambda",
    "Xi": "capital xi",
    "Pi": "capital pi",
    "Sigma": "capital sigma",
    "Phi": "capital phi",
    "Psi": "capital psi",
    "Omega": "capital omega",
}
UNICODE_GREEK = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ϵ": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "ϕ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    "Γ": "capital gamma",
    "Δ": "capital delta",
    "Θ": "capital theta",
    "Λ": "capital lambda",
    "Ξ": "capital xi",
    "Π": "capital pi",
    "Σ": "capital sigma",
    "Φ": "capital phi",
    "Ψ": "capital psi",
    "Ω": "capital omega",
}
SYMBOLS = {
    "≤": "less than or equal to",
    "≥": "greater than or equal to",
    "≠": "not equal to",
    "≈": "approximately equal to",
    "≡": "is equivalent to",
    "∼": "is distributed as",
    "∝": "proportional to",
    "∈": "in",
    "∉": "not in",
    "⊂": "subset of",
    "⊆": "subset of or equal to",
    "⊃": "superset of",
    "∪": "union",
    "∩": "intersection",
    "∅": "the empty set",
    "∀": "for all",
    "∃": "there exists",
    "¬": "not",
    "∧": "and",
    "∨": "or",
    "⊕": "x or",
    "→": "to",
    "⟶": "to",
    "↦": "maps to",
    "⇒": "implies",
    "⟹": "implies",
    "⇔": "if and only if",
    "↔": "if and only if",
    "×": "times",
    "·": "times",
    "⋅": "times",
    "∗": "times",
    "±": "plus or minus",
    "∓": "minus or plus",
    "√": "square root of",
    "∑": "the sum of",
    "∏": "the product of",
    "∫": "the integral of",
    "∞": "infinity",
    "∂": "partial",
    "∇": "gradient of",
    "−": "minus",
    "…": "through",
    "⋯": "through",
    "°": "degrees",
    "′": "prime",
    "‖": "norm",
    "∘": "composed with",
    "⌈": "ceiling of",
    "⌉": "",
    "⌊": "floor of",
    "⌋": "",
    "⊤": "transpose",
}
SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ", "0123456789+-ni")
SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋ᵢⱼₖₙ", "0123456789+-ijkn")

COMMANDS = {
    "leq": "less than or equal to",
    "le": "less than or equal to",
    "geq": "greater than or equal to",
    "ge": "greater than or equal to",
    "neq": "not equal to",
    "ne": "not equal to",
    "approx": "approximately equal to",
    "equiv": "is equivalent to",
    "sim": "is distributed as",
    "propto": "proportional to",
    "in": "in",
    "notin": "not in",
    "subset": "subset of",
    "subseteq": "subset of or equal to",
    "supset": "superset of",
    "cup": "union",
    "cap": "intersection",
    "emptyset": "the empty set",
    "varnothing": "the empty set",
    "forall": "for all",
    "exists": "there exists",
    "neg": "not",
    "lnot": "not",
    "land": "and",
    "wedge": "and",
    "lor": "or",
    "vee": "or",
    "oplus": "x or",
    "otimes": "tensor",
    "to": "to",
    "rightarrow": "to",
    "longrightarrow": "to",
    "mapsto": "maps to",
    "leftarrow": "from",
    "Rightarrow": "implies",
    "implies": "implies",
    "Leftrightarrow": "if and only if",
    "iff": "if and only if",
    "times": "times",
    "cdot": "times",
    "ast": "times",
    "pm": "plus or minus",
    "mp": "minus or plus",
    "infty": "infinity",
    "partial": "partial",
    "nabla": "gradient of",
    "ldots": "through",
    "cdots": "through",
    "dots": "through",
    "circ": "composed with",
    "prime": "prime",
    "top": "transpose",
    "intercal": "transpose",
    "mid": "given",
    "vert": "",
    "lvert": "",
    "rvert": "",
    "Vert": "norm",
    "lVert": "norm",
    "rVert": "",
    "langle": "",
    "rangle": "",
    "log": "log",
    "lg": "log",
    "ln": "natural log",
    "exp": "exp",
    "sin": "sine",
    "cos": "cosine",
    "tan": "tangent",
    "tanh": "tanch",
    "sigmoid": "sigmoid",
    "det": "determinant of",
    "dim": "dimension of",
    "min": "min",
    "max": "max",
    "argmin": "arg min",
    "argmax": "arg max",
    "sup": "supremum",
    "inf": "infimum",
    "Pr": "probability of",
    "lceil": "ceiling of",
    "rceil": "",
    "lfloor": "floor of",
    "rfloor": "",
    "ell": "ell",
}
IGNORED = {
    "left",
    "right",
    "big",
    "Big",
    "bigg",
    "Bigg",
    "bigl",
    "bigr",
    "Bigl",
    "Bigr",
    "displaystyle",
    "textstyle",
    "scriptstyle",
    "limits",
    "nolimits",
    "quad",
    "qquad",
    "mathstrut",
    "nonumber",
    "label",
    "tag",
}
FONT_WRAPPERS = {
    "mathbf",
    "mathrm",
    "mathit",
    "mathsf",
    "mathtt",
    "boldsymbol",
    "bm",
    "mathbb",
    "mathcal",
    "mathscr",
    "mathfrak",
    "text",
    "textrm",
    "textit",
    "textbf",
    "texttt",
    "operatorname",
    "mbox",
    "hbox",
    "rm",
    "bf",
    "it",
}
DECORATIONS = {
    "hat": "hat",
    "widehat": "hat",
    "bar": "bar",
    "overline": "bar",
    "tilde": "tilde",
    "widetilde": "tilde",
    "dot": "dot",
    "ddot": "double dot",
    "vec": "vector",
}
BIG_OPERATORS = {
    "sum": "the sum",
    "prod": "the product",
    "int": "the integral",
    "lim": "the limit",
    "bigcup": "the union",
    "bigcap": "the intersection",
}
FUNCTION_WORDS = {
    "log",
    "ln",
    "exp",
    "max",
    "min",
    "sqrt",
    "softmax",
    "argmax",
    "argmin",
    "sin",
    "cos",
    "tanh",
    "relu",
    "sigmoid",
    "poly",
    "polylog",
    "lg",
    "det",
}
OPERATORS = {
    "+": "plus",
    "-": "minus",
    "*": "times",
    "/": "over",
    "=": "equals",
    "<": "less than",
    ">": "greater than",
    ":": "such that",
    ";": ",",
}

_TOKEN = re.compile(r"\\[A-Za-z]+|\\[,;:! ]|\\\{|\\\}|\\\||\d+(?:\.\d+)?|[A-Za-z]+|\.\.\.|\S")


def _tokens(expr: str) -> list[str]:
    expr = expr.translate({0x2009: " ", 0x00A0: " "}).replace("\\_", " ")
    out: list[str] = []
    for tok in _TOKEN.findall(expr):
        if tok in {"\\,", "\\;", "\\:", "\\!", "\\ "}:
            continue
        if any(c in SUPERSCRIPTS_CHARS for c in tok) and len(tok) == 1:
            out += ["^", tok.translate(SUPERSCRIPTS)]
            continue
        if any(c in SUBSCRIPTS_CHARS for c in tok) and len(tok) == 1:
            out += ["_", tok.translate(SUBSCRIPTS)]
            continue
        out.append(tok)
    return out


SUPERSCRIPTS_CHARS = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ")
SUBSCRIPTS_CHARS = set("₀₁₂₃₄₅₆₇₈₉₊₋ᵢⱼₖₙ")


class _Reader:
    def __init__(self, tokens: list[str]) -> None:
        self.t = tokens
        self.i = 0

    def peek(self, k: int = 0) -> str | None:
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    def next(self) -> str | None:
        tok = self.peek()
        self.i += 1
        return tok

    # A group is {...}, or a single token when there are no braces.
    def group(self) -> list[str]:
        tok = self.peek()
        if tok == "{":
            self.i += 1
            return self.until("}")
        if tok is None:
            return []
        self.i += 1
        if tok.startswith("\\") and tok[1:] in FONT_WRAPPERS | set(DECORATIONS):
            return self.command(tok[1:])
        return self.atom(tok)

    def until(self, closer: str) -> list[str]:
        words: list[str] = []
        while (tok := self.peek()) is not None and tok != closer:
            words += self.item()
        if self.peek() == closer:
            self.i += 1
        return words

    def item(self) -> list[str]:
        tok = self.next()
        if tok is None:
            return []
        words = self.atom(tok)
        if self.peek() == "(" and tuple(words) in _ASYMPTOTIC:
            self.i += 1
            return [_ASYMPTOTIC[tuple(words)], "of", *self.until(")")]
        words = self.postfix(words)
        # Function application: f(x), P(y | x), \sigma(z), \mathrm{FFN}(x) -> "f of x".
        if self.peek() == "(" and (_is_function(tok) or tok[1:] in _NAMED):
            self.i += 1
            words = [*words, "of", *self.until(")")]
        return words

    def postfix(self, base: list[str]) -> list[str]:
        words = base
        while (tok := self.peek()) in {"^", "_", "!", "'"}:
            self.i += 1
            if tok == "!":
                words = [*words, "factorial"]
            elif tok == "'":
                words = [*words, "prime"]
            elif tok == "_":
                sub = self.group()
                words = [*words, "sub", *sub] if sub else words
            else:
                words = [*words, *power(self.group())]
        return words

    def atom(self, tok: str) -> list[str]:
        if tok.startswith("\\") and len(tok) > 1 and tok[1].isalpha():
            return self.command(tok[1:])
        if tok in {"\\{", "\\}"}:
            return []
        if tok == "\\|":
            return ["norm"]
        if tok == "{":
            return self.until("}")
        if tok in {"(", "["}:
            inner = self.until(")" if tok == "(" else "]")
            return inner
        if tok in {")", "]", "}"}:
            return []
        if tok == "|":
            return self.bars()
        if tok == "...":
            return ["through"]
        if tok == ",":
            return [","]
        if tok in OPERATORS:
            return [OPERATORS[tok]]
        if tok in SYMBOLS:
            return [SYMBOLS[tok]] if SYMBOLS[tok] else []
        if tok in UNICODE_GREEK:
            return [UNICODE_GREEK[tok]]
        if re.fullmatch(r"\d+\.\d+", tok):
            whole, frac = tok.split(".")
            return [whole, "point", " ".join(frac)]
        if tok.isdigit():
            return [tok]
        if tok.isalpha():
            return letters(tok)
        return []

    def bars(self) -> list[str]:
        # |x| is a size/absolute value; a lone bar is "given" (P(y | x)).
        depth = 0
        for j in range(self.i, len(self.t)):
            t = self.t[j]
            if t in {"(", "[", "{"}:
                depth += 1
            elif t in {")", "]", "}"}:
                if depth == 0:
                    break
                depth -= 1
            elif t == "|" and depth == 0:
                inner = self.t[self.i : j]
                self.i = j + 1
                sub = _Reader(inner).all()
                return ["the size of", *sub]
        return ["given"]

    def command(self, name: str) -> list[str]:
        if name in IGNORED:
            if name in {"label", "tag"}:
                self.group()
            return []
        if name in GREEK:
            return [GREEK[name]]
        if name in FONT_WRAPPERS:
            inner = self.group()
            return inner
        if name in DECORATIONS:
            inner = self.group()
            word = DECORATIONS[name]
            return [word, *inner] if word == "vector" else [*inner, word]
        if name in {"frac", "dfrac", "tfrac"}:
            num, den = self.group(), self.group()
            return [*num, "over", *den]
        if name == "sqrt":
            if self.peek() == "[":
                self.i += 1
                degree = self.until("]")
                return [*_ordinal_root(degree), *self.group()]
            return ["square root of", *self.group()]
        if name == "binom":
            n, k = self.group(), self.group()
            return [*n, "choose", *k]
        if name in BIG_OPERATORS:
            return self.big_operator(name)
        if name in {"min", "max", "argmin", "argmax", "arg"} and self.peek() == "_":
            self.i += 1
            over = self.group()
            return [COMMANDS.get(name, name), "over", *over, "of"]
        if name == "mathcal" or name == "mathbb":
            return self.group()
        if name in COMMANDS:
            word = COMMANDS[name]
            return [word] if word else []
        return letters(name)

    def big_operator(self, name: str) -> list[str]:
        lower: list[str] = []
        upper: list[str] = []
        while self.peek() in {"_", "^", "\\limits"}:
            tok = self.next()
            if tok == "_":
                lower = self.group()
            elif tok == "^":
                upper = self.group()
        words = [BIG_OPERATORS[name]]
        if name == "lim":
            if lower:
                words += ["as", *[("approaches" if w == "to" else w) for w in lower]]
            return [*words, "of"]
        if lower:
            words += ["over" if not upper else "from", *lower]
        if upper:
            words += ["to", *upper]
        return [*words, "of"]

    def all(self) -> list[str]:
        words: list[str] = []
        while self.peek() is not None:
            words += self.item()
        return words


_NAMED = {"mathrm", "operatorname", "text", "textrm", "mathit", "mathsf"}
_ASYMPTOTIC: dict[tuple[str, ...], str] = {
    ("O",): "big O",
    ("capital theta",): "big theta",
    ("capital omega",): "big omega",
    ("o",): "little o",
    ("omega",): "little omega",
}


def _is_function(tok: str) -> bool:
    if tok.startswith("\\"):
        return tok[1:] in {"log", "ln", "exp", "max", "min", "Pr", "sin", "cos", "tanh", "det"} or (
            tok[1:] in GREEK
        )
    return tok.isalpha() and (len(tok) == 1 or tok.lower() in FUNCTION_WORDS)


def _ordinal_root(degree: list[str]) -> list[str]:
    names = {"2": "square", "3": "cube", "4": "fourth", "n": "n-th", "k": "k-th"}
    d = " ".join(degree)
    return [f"{names.get(d, d + '-th')} root of"]


def power(exp: list[str]) -> list[str]:
    e = " ".join(exp)
    if e == "2":
        return ["squared"]
    if e == "3":
        return ["cubed"]
    if e in {"transpose", "T"}:
        return ["transpose"]
    if e in {"minus 1", "- 1"}:
        return ["inverse"]
    if e in {"times", "*"}:
        return ["star"]
    if e == "prime":
        return ["prime"]
    if len(exp) == 1:
        return ["to the", e]
    return ["to the power of", *exp, ","]


def letters(word: str) -> list[str]:
    """Read an identifier: known function names as words, short runs as letters."""
    low = word.lower()
    # "num", "pos", "lrate" read as words; "QK", "xy", "FFN" as separate letters.
    is_wordlike = word.islower() and len(word) >= 3 and any(c in "aeiouy" for c in word)
    if low in FUNCTION_WORDS or len(word) >= 4 or is_wordlike:
        return ["square root of"] if low == "sqrt" else [word]
    if len(word) == 1:
        return ["ay"] if word in {"a", "A"} else [word]
    # "QK", "xy", "nm": products of single-letter variables.
    return [("ay" if c in "aA" else c) for c in word]


def speak(expr: str) -> str:
    words = _Reader(_tokens(expr)).all()
    text = " ".join(w for w in words if w)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*through\s*,", " through", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text
