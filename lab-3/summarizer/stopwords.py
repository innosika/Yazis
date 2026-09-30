# -*- coding: utf-8 -*-
"""Списки стоп-слов для русского и английского языков.

Стоп-слова — служебные и общеупотребительные слова (предлоги, союзы,
местоимения, частицы, вспомогательные глаголы), которые встречаются
практически в любом тексте и поэтому не несут информации о его теме.
Согласно методическим указаниям такие слова при вычислении весов
не учитываются.

Списки собраны на основе классических списков NLTK / Snowball и расширены
частотными служебными словами научного и литературоведческого стилей.
"""
from __future__ import annotations

RUSSIAN_STOPWORDS: frozenset[str] = frozenset("""
а август авось авторы бы был была были было быть в вам вами вас ваш ваша ваше ваши
вдоль вдруг ведь везде весь вместе вне вниз внизу во вокруг вон вообще вопреки вот
временами всё все всегда всего всей всем всеми всему всех вся всю всюду вы г где гг
да давай давать даже далее далёкий дальше даром де для до довольно долго должен
должна должно должны другая другие других друго другое другой его ее её ей ем ему
если есть ещё еще ею же за зачем здесь и из из-за или им ими имеет имели имело имеют
иметь имени иначе иногда их к каждая каждое каждые каждый кажется как какая какие
каков какой какому кем когда кого ком кому которая которого которое которой котором
которому которые который которых кто куда ли либо лишь между меля менее меньше меня
мне мной много могут мог могла могли может можем можете можешь можно мои мой мочь моя
моё мы на наверху над надо назад наиболее наконец нам нами нас наш наша наше наши не
него нее неё ней нельзя нем нём нему непрерывно нередко несколько нет нею ни нибудь
ниже низко никогда никуда ним ними них ничего но ну нужно о об оба обычно один одна
одни одним одними одних одно одного одной одном одному одну она они оно от отсюда
очень первый перед по под подобный подобная подобное подобные поем позже пока помимо
поскольку после потом потому почему почти при про просто против процентов пусть путём
раз разве ранее ровно рядом с сам сама сами самим самими самих само самого самой самом
самому саму свое своё своего своей своем своём своему свои своих свой свою себе себя
сегодня сейчас сказал сказала сказать сквозь сколько слишком снова со собой собою
совсем спасибо стал стала стали стало стать так такая также таки такие таким такими
таких такое такой там твой те тебе тебя тем теми теперь тех то тобой тобою тогда того
тоже той только том тому тот тою три тут ты тысяч у уж уже хотя хоть хочешь чаще чего
чего-то чем через чём что чтоб чтобы чуть эта эти этим этими этих это этого этой этом
этому этот эту я является являются явно
""".split())

ENGLISH_STOPWORDS: frozenset[str] = frozenset("""
a about above after again against all almost along already also although always am
among an and another any anyone anything are aren't around as at back be became because
become becomes been before behind being below best better between beyond both but by
came can cannot can't could couldn't did didn't do does doesn't doing done don't down
due during each either else enough especially etc even ever every everyone everything
except far few first five for former found four from further gave get given gives go
goes going gone got had hadn't has hasn't have haven't having he hence her here hers
herself him himself his how however i if in indeed instead into is isn't it its it's
itself just keep kept last later latter least less let like likely made mainly make
makes many may maybe me meanwhile might mine more moreover most mostly much must my
myself namely near need neither never nevertheless next no none nor not nothing now
nowadays of off often on once one only onto or other others otherwise ought our ours
ourselves out over own particular particularly per perhaps please possible probably
quite rather really regarding said same say says second see seem seemed seeming seems
seen several shall she should shouldn't since so some somehow someone something
sometimes somewhat somewhere still such sure take taken than that the their theirs them
themselves then thence there therefore these they third this those though three through
throughout thus to together too toward towards two under unless until up upon us use
used using usually various very via was wasn't way we well were weren't what whatever
when whence whenever where whereas whereby wherein whether which while whither who whoever
whole whom whose why will with within without won't would wouldn't yet you your yours
yourself yourselves
""".split())

STOPWORDS: dict[str, frozenset[str]] = {
    "ru": RUSSIAN_STOPWORDS,
    "en": ENGLISH_STOPWORDS,
}


def is_stopword(word: str, lang: str) -> bool:
    """Проверяет, является ли слово стоп-словом для указанного языка."""
    return word in STOPWORDS.get(lang, frozenset())
