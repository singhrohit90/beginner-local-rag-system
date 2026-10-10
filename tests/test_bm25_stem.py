import numpy as np

from rag.common.bm25 import BM25Index, tokenize
from rag.common.chunk_store import MemoryChunkStore, Scope
from rag.common.stem import stem
from rag.common.types import Chunk


def test_stem_known_porter_pairs():
    assert stem("indexes") == stem("indexing") == stem("index") == "index"
    assert stem("replicated") == stem("replication") == "replic"
    assert stem("caresses") == "caress" and stem("ponies") == "poni" and stem("agreed") == "agre"
    assert stem("is") == "is" and stem("b2b") == "b2b"  # short words and non-alphabetic tokens untouched


def test_tokenize_default_does_not_stem():
    assert tokenize("The indexes of partitioned logs") == ["indexes", "partitioned", "logs"]
    assert tokenize("The indexes of partitioned logs", stem=True) == ["index", "partit", "log"]


# Examples from Porter's 1980 paper (the original algorithm), so a slip in any rule shows up here.
PORTER_PAIRS = """caresses caress ponies poni ties ti caress caress cats cat feed feed agreed agre plastered plaster
bled bled motoring motor sing sing conflated conflat troubled troubl sized size hopping hop tanned tan
falling fall hissing hiss fizzed fizz failing fail filing file happy happi sky sky relational relat
conditional condit rational ration digitizer digit operator oper feudalism feudal decisiveness decis
hopefulness hope callousness callous formaliti formal sensitiviti sensit sensibiliti sensibl
triplicate triplic formative form formalize formal electriciti electr electrical electr hopeful hope
goodness good revival reviv allowance allow inference infer airliner airlin gyroscopic gyroscop
adjustable adjust defensible defens irritant irrit replacement replac adjustment adjust dependent depend
adoption adopt homologou homolog communism commun activate activ angulariti angular homologous homolog
effective effect bowdlerize bowdler probate probat rate rate cease ceas controll control roll roll""".split()


def test_stemmer_matches_porters_published_examples():
    words = PORTER_PAIRS[::2]
    wanted = PORTER_PAIRS[1::2]
    assert [stem(w) for w in words] == wanted


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
    assert MemoryChunkStore().stem is False


def _store(stem):
    store = MemoryChunkStore(stem=stem)
    chunks = [Chunk("a", "the secondary indexes are rebuilt", 1, 1, "t"), Chunk("b", "clocks drift", 1, 1, "t")]
    store.upsert("d", "u", chunks, np.eye(2, 4, dtype=np.float32), "emb")
    return store


def test_stores_in_one_process_do_not_share_the_stem_setting():
    on, off = _store(True), _store(False)
    scope = Scope("u")
    assert [c.chunk_id for c, _ in on.search_keyword("indexing", 2, scope)] == ["a"]
    assert off.search_keyword("indexing", 2, scope) == []
    assert _store(False).search_keyword("indexing", 2, scope) == []  # built after the stemming store: unaffected


def test_copy_keeps_the_stem_setting():
    assert _store(True).copy().stem is True and _store(False).copy().stem is False
