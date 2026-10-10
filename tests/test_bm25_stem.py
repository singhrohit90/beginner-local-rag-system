from rag.common.bm25 import BM25Index, tokenize
from rag.common.stem import stem


def test_stem_known_porter_pairs():
    assert stem("indexes") == stem("indexing") == stem("index") == "index"
    assert stem("replicated") == stem("replication") == "replic"
    assert stem("caresses") == "caress" and stem("ponies") == "poni" and stem("agreed") == "agre"
    assert stem("is") == "is" and stem("b2b") == "b2b"  # short words and non-alphabetic tokens untouched


def test_tokenize_default_does_not_stem():
    assert tokenize("The indexes of partitioned logs") == ["indexes", "partitioned", "logs"]
    assert tokenize("The indexes of partitioned logs", stem=True) == ["index", "partit", "log"]



class _C:
    def __init__(self, text):
        self.text = text


def test_stemming_matches_other_word_forms_only_when_on():
    docs = [_C("the secondary indexes are rebuilt"), _C("a totally unrelated passage about clocks")]
    off = BM25Index(docs, stem=False)
    on = BM25Index(docs, stem=True)
    assert off.search("indexing", 2) == []
    assert [row for row, _ in on.search("indexing", 2)] == [0]


def test_default_is_off():
    assert BM25Index([_C("indexes")]).stem is False
