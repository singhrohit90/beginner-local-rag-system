"""A small dependency-free Porter stemmer (the 1980 algorithm), used by BM25Index when stemming is on.

OpenSearch's `english` analyzer uses a Porter-family stemmer, so this is the closest cheap match for
testing whether stemming explains the keyword-search gap. Words of two letters or fewer are left alone.
"""

from functools import lru_cache


def _is_cons(w: str, i: int) -> bool:
    c = w[i]
    if c in "aeiou":
        return False
    if c == "y":
        return i == 0 or not _is_cons(w, i - 1)
    return True


def _measure(stem: str) -> int:
    """Number of vowel-consonant sequences, written [C](VC){m}[V] in the paper."""
    m, prev_vowel = 0, False
    for i in range(len(stem)):
        cons = _is_cons(stem, i)
        if cons and prev_vowel:
            m += 1
        prev_vowel = not cons
    return m


def _has_vowel(stem: str) -> bool:
    return any(not _is_cons(stem, i) for i in range(len(stem)))


def _double_cons(w: str) -> bool:
    return len(w) >= 2 and w[-1] == w[-2] and _is_cons(w, len(w) - 1)


def _cvc(w: str) -> bool:
    n = len(w)
    return (n >= 3 and _is_cons(w, n - 1) and not _is_cons(w, n - 2) and _is_cons(w, n - 3)
            and w[-1] not in "wxy")


def _replace(w: str, rules, min_m: int) -> str:
    for suffix, repl in rules:
        if w.endswith(suffix):
            stem = w[: len(w) - len(suffix)]
            return stem + repl if _measure(stem) > min_m else w
    return w


_STEP2 = [("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"), ("izer", "ize"),
          ("abli", "able"), ("alli", "al"), ("entli", "ent"), ("eli", "e"), ("ousli", "ous"),
          ("ization", "ize"), ("ation", "ate"), ("ator", "ate"), ("alism", "al"), ("iveness", "ive"),
          ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble")]
_STEP3 = [("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"), ("ical", "ic"),
          ("ful", ""), ("ness", "")]
_STEP4 = ["al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment", "ent", "ion", "ou",
          "ism", "ate", "iti", "ous", "ive", "ize"]


@lru_cache(maxsize=100_000)
def stem(word: str) -> str:
    w = word
    if len(w) <= 2 or not w.isalpha():
        return w
    # step 1a
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-2]
    elif w.endswith("ss"):
        pass
    elif w.endswith("s"):
        w = w[:-1]
    # step 1b
    if w.endswith("eed"):
        if _measure(w[:-3]) > 0:
            w = w[:-1]
    else:
        for suffix in ("ed", "ing"):
            if w.endswith(suffix) and _has_vowel(w[: -len(suffix)]):
                w = w[: -len(suffix)]
                if w.endswith(("at", "bl", "iz")):
                    w += "e"
                elif _double_cons(w) and w[-1] not in "lsz":
                    w = w[:-1]
                elif _measure(w) == 1 and _cvc(w):
                    w += "e"
                break
    # step 1c
    if w.endswith("y") and _has_vowel(w[:-1]):
        w = w[:-1] + "i"
    # steps 2 and 3
    w = _replace(w, _STEP2, 0)
    w = _replace(w, _STEP3, 0)
    # step 4
    for suffix in sorted(_STEP4, key=len, reverse=True):
        if w.endswith(suffix):
            base = w[: -len(suffix)]
            if _measure(base) > 1 and (suffix != "ion" or base.endswith(("s", "t"))):
                w = base
            break
    # step 5
    if w.endswith("e"):
        base = w[:-1]
        m = _measure(base)
        if m > 1 or (m == 1 and not _cvc(base)):
            w = base
    if _measure(w) > 1 and _double_cons(w) and w.endswith("l"):
        w = w[:-1]
    return w
