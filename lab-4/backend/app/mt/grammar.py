"""The Russian grammatical facts the transfer stage needs: prepositions, cases, euphony.

Kept apart from `transfer.py` so the rules can be read - and corrected - as data rather
than as control flow.
"""

# English preposition -> (Russian preposition or None, case it governs).
#
# `None` means the preposition disappears and only the case survives, which is the single
# most important structural difference between the two languages here: English "of" and the
# possessive both become a bare Russian genitive, so "the author of the novel" and "the
# novel's author" converge on «автор романа».
PREPOSITIONS: dict[str, tuple[str | None, str]] = {
    "of": (None, "gen"),
    "by": (None, "ins"),
    "in": ("в", "prep"),
    "on": ("на", "prep"),
    "at": ("в", "prep"),
    "to": ("к", "dat"),
    "for": ("для", "gen"),
    "from": ("из", "gen"),
    "with": ("с", "ins"),
    "without": ("без", "gen"),
    "about": ("о", "prep"),
    "as": ("как", "nom"),
    "into": ("в", "acc"),
    "onto": ("на", "acc"),
    "through": ("через", "acc"),
    "throughout": ("на протяжении", "gen"),
    "between": ("между", "ins"),
    "among": ("среди", "gen"),
    "amongst": ("среди", "gen"),
    "under": ("под", "ins"),
    "beneath": ("под", "ins"),
    "below": ("ниже", "gen"),
    "over": ("над", "ins"),
    "above": ("над", "ins"),
    "before": ("до", "gen"),
    "after": ("после", "gen"),
    "during": ("во время", "gen"),
    "against": ("против", "gen"),
    "within": ("в пределах", "gen"),
    "across": ("через", "acc"),
    "toward": ("к", "dat"),
    "towards": ("к", "dat"),
    "upon": ("на", "prep"),
    "via": ("посредством", "gen"),
    "per": ("на", "acc"),
    "than": ("чем", "nom"),
    "like": ("как", "nom"),
    "unlike": ("в отличие от", "gen"),
    "since": ("с", "gen"),
    "until": ("до", "gen"),
    "till": ("до", "gen"),
    "despite": ("несмотря на", "acc"),
    "besides": ("кроме", "gen"),
    "except": ("кроме", "gen"),
    "beyond": ("за", "ins"),
    "near": ("около", "gen"),
    "behind": ("за", "ins"),
    "along": ("вдоль", "gen"),
    "around": ("вокруг", "gen"),
    "beside": ("рядом с", "ins"),
    "inside": ("внутри", "gen"),
    "outside": ("вне", "gen"),
    "regarding": ("относительно", "gen"),
    "concerning": ("относительно", "gen"),
    "including": ("включая", "acc"),
    "considering": ("учитывая", "acc"),
    "given": ("учитывая", "acc"),
    "versus": ("против", "gen"),
    "amid": ("среди", "gen"),
    "atop": ("на", "prep"),
    "off": ("с", "gen"),
    "out": ("из", "gen"),
    "up": ("вверх по", "dat"),
    "down": ("вниз по", "dat"),
    "onto ": ("на", "acc"),
}

# Multiword prepositions, matched before single ones.
COMPOUND_PREPOSITIONS: dict[str, tuple[str | None, str]] = {
    "according to": ("согласно", "dat"),
    "due to": ("из-за", "gen"),
    "owing to": ("из-за", "gen"),
    "because of": ("из-за", "gen"),
    "instead of": ("вместо", "gen"),
    "in spite of": ("несмотря на", "acc"),
    "such as": ("такой как", "nom"),
    "as well as": ("а также", "nom"),
    "in terms of": ("с точки зрения", "gen"),
    "in order to": ("чтобы", "nom"),
    "thanks to": ("благодаря", "dat"),
    "out of": ("из", "gen"),
    "next to": ("рядом с", "ins"),
    "close to": ("близко к", "dat"),
    "prior to": ("до", "gen"),
    "along with": ("вместе с", "ins"),
    "apart from": ("помимо", "gen"),
    "rather than": ("а не", "nom"),
    "by means of": ("посредством", "gen"),
    "in front of": ("перед", "ins"),
    "with respect to": ("по отношению к", "dat"),
}

# Dependency label -> case, for the roles that do not need a preposition.
DEP_CASE: dict[str, str] = {
    "nsubj": "nom",
    "nsubjpass": "nom",
    "csubj": "nom",
    "expl": "nom",
    "attr": "nom",
    "acomp": "nom",
    "dobj": "acc",
    "obj": "acc",
    "iobj": "dat",
    "dative": "dat",
    "poss": "gen",
    "nmod": "gen",
    "appos": "nom",
    "oprd": "ins",
    "npadvmod": "acc",
    "conj": "nom",
    "compound": "gen",
}

# Modal verbs. `frame` is what is inserted; the main verb goes to the infinitive.
MODALS: dict[str, tuple[str, str]] = {
    "can": ("мочь", "agree"),
    "could": ("мочь", "past"),
    "may": ("мочь", "agree"),
    "might": ("мочь", "agree"),
    "must": ("должен", "predicative"),
    "should": ("должен", "predicative"),
    "ought": ("должен", "predicative"),
    "need": ("нужно", "impersonal"),
}

# Frequent English function words a dictionary lookup handles badly. Fixing them here
# costs one line each and removes the most visible class of word-for-word artefacts.
FUNCTION_WORDS: dict[str, str] = {
    "not": "не",
    "n't": "не",
    "no": "нет",
    "and": "и",
    "or": "или",
    "but": "но",
    "if": "если",
    "that": "что",
    "because": "потому что",
    "while": "пока",
    "when": "когда",
    "where": "где",
    "how": "как",
    "why": "почему",
    "also": "также",
    "however": "однако",
    "therefore": "поэтому",
    "thus": "таким образом",
    "moreover": "более того",
    "furthermore": "кроме того",
    "nevertheless": "тем не менее",
    "nonetheless": "тем не менее",
    "although": "хотя",
    "though": "хотя",
    "whereas": "тогда как",
    "so": "поэтому",
    "then": "затем",
    "still": "всё же",
    "yet": "однако",
    "very": "очень",
    "more": "более",
    "most": "наиболее",
    "less": "менее",
    "least": "наименее",
    "both": "оба",
    "either": "либо",
    "neither": "ни",
    "such": "такой",
    "only": "только",
    "even": "даже",
    "already": "уже",
    "always": "всегда",
    "never": "никогда",
    "often": "часто",
    "usually": "обычно",
    "rather": "довольно",
    "quite": "довольно",
    "almost": "почти",
    "perhaps": "возможно",
    "maybe": "возможно",
    "indeed": "действительно",
    "instead": "вместо этого",
    "here": "здесь",
    "there": "там",
    "now": "сейчас",
    "yes": "да",
}

# Pronouns, which are too irregular to leave to a dictionary lookup plus a case rule.
PRONOUNS: dict[str, dict[str, str]] = {
    "i": {"nom": "я", "gen": "меня", "dat": "мне", "acc": "меня", "ins": "мной", "prep": "мне"},
    "we": {"nom": "мы", "gen": "нас", "dat": "нам", "acc": "нас", "ins": "нами", "prep": "нас"},
    "you": {"nom": "вы", "gen": "вас", "dat": "вам", "acc": "вас", "ins": "вами", "prep": "вас"},
    "he": {"nom": "он", "gen": "его", "dat": "ему", "acc": "его", "ins": "им", "prep": "нём"},
    "she": {"nom": "она", "gen": "её", "dat": "ей", "acc": "её", "ins": "ей", "prep": "ней"},
    "it": {"nom": "оно", "gen": "его", "dat": "ему", "acc": "его", "ins": "им", "prep": "нём"},
    "they": {"nom": "они", "gen": "их", "dat": "им", "acc": "их", "ins": "ими", "prep": "них"},
    "me": {"nom": "я", "gen": "меня", "dat": "мне", "acc": "меня", "ins": "мной", "prep": "мне"},
    "him": {"nom": "он", "gen": "его", "dat": "ему", "acc": "его", "ins": "им", "prep": "нём"},
    "her": {"nom": "она", "gen": "её", "dat": "ей", "acc": "её", "ins": "ей", "prep": "ней"},
    "us": {"nom": "мы", "gen": "нас", "dat": "нам", "acc": "нас", "ins": "нами", "prep": "нас"},
    "them": {"nom": "они", "gen": "их", "dat": "им", "acc": "их", "ins": "ими", "prep": "них"},
    "this": {
        "nom": "это",
        "gen": "этого",
        "dat": "этому",
        "acc": "это",
        "ins": "этим",
        "prep": "этом",
    },
    "that": {"nom": "то", "gen": "того", "dat": "тому", "acc": "то", "ins": "тем", "prep": "том"},
    "these": {
        "nom": "эти",
        "gen": "этих",
        "dat": "этим",
        "acc": "эти",
        "ins": "этими",
        "prep": "этих",
    },
    "those": {"nom": "те", "gen": "тех", "dat": "тем", "acc": "те", "ins": "теми", "prep": "тех"},
    "which": {
        "nom": "который",
        "gen": "которого",
        "dat": "которому",
        "acc": "который",
        "ins": "которым",
        "prep": "котором",
    },
    "who": {"nom": "кто", "gen": "кого", "dat": "кому", "acc": "кого", "ins": "кем", "prep": "ком"},
    "what": {"nom": "что", "gen": "чего", "dat": "чему", "acc": "что", "ins": "чем", "prep": "чём"},
}

# Possessive determiners. Russian «свой» would often be better, but it depends on
# coreference, which a sentence-local transfer system cannot resolve reliably.
POSSESSIVES: dict[str, str] = {
    "my": "мой",
    "your": "ваш",
    "his": "его",
    "her": "её",
    "its": "его",
    "our": "наш",
    "their": "их",
    "whose": "чей",
}

# Determiners that carry meaning and must survive the article drop.
KEPT_DETERMINERS: dict[str, str] = {
    "this": "этот",
    "that": "тот",
    "these": "эти",
    "those": "те",
    "each": "каждый",
    "every": "каждый",
    "all": "весь",
    "some": "некоторый",
    "any": "любой",
    "no": "никакой",
    "another": "другой",
    "other": "другой",
    "such": "такой",
    "both": "оба",
    "many": "многие",
    "much": "много",
    "few": "немногие",
    "several": "несколько",
}

ARTICLES = frozenset({"the", "a", "an"})

# Verbs whose Russian equivalent governs a case other than the accusative. Without this the
# translator produces «управлять систему» instead of «управлять системой».
VERB_GOVERNMENT: dict[str, str] = {
    "управлять": "ins",
    "пользоваться": "ins",
    "владеть": "ins",
    "заниматься": "ins",
    "являться": "ins",
    "становиться": "ins",
    "стать": "ins",
    "руководить": "ins",
    "обладать": "ins",
    "помогать": "dat",
    "помочь": "dat",
    "мешать": "dat",
    "следовать": "dat",
    "соответствовать": "dat",
    "принадлежать": "dat",
    "верить": "dat",
    "доверять": "dat",
    "радоваться": "dat",
    "достигать": "gen",
    "достичь": "gen",
    "требовать": "gen",
    "избегать": "gen",
    "лишать": "gen",
    "касаться": "gen",
    "зависеть": "gen",
}


def euphonic(preposition: str, following: str) -> str:
    """Choose between «в»/«во», «с»/«со», «к»/«ко», «о»/«об».

    Russian inserts a vowel when a one-consonant preposition would otherwise collide with a
    consonant cluster, and «о» gains a consonant before a vowel. Skipping this is the kind
    of detail that makes otherwise correct output read as machine output.
    """
    word = (following or "").lower().lstrip("«\"'(")
    if not word:
        return preposition

    first, second = word[0], word[1:2]
    vowels = "аеёиоуыэюя"
    cluster = bool(second) and second not in vowels

    if preposition == "о":
        if first in "аиоуэ":
            return "об"
        if word.startswith(("мне", "всём", "всем")):
            return "обо"
        return "о"
    if preposition == "в" and cluster and first in "вф":
        return "во"
    if preposition == "с" and cluster and first in "сзшж":
        return "со"
    if preposition == "к" and cluster and first in "кг":
        return "ко"
    if preposition == "из" and cluster and first in "з":
        return "изо"
    if preposition == "под" and cluster and first in "мл":
        return "подо"
    if preposition == "над" and cluster and first in "мл":
        return "надо"
    return preposition
