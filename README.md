# Modular RAG learning project

A local RAG pipeline built step by step to learn how each stage works and how to measure it: chunking, hybrid search (keyword plus vector), fusion, reranking, generation, evaluation and security tests. The test corpus is one book (Designing Data-Intensive Applications), with a hand-written golden question set.

Started from the MIT-licensed JAMwithAI beginner RAG repo. None of its code remains; the few ideas worth keeping are in `docs/original_repo_patterns.md`.

## Where things are

| Path | What it holds |
|------|---------------|
| `rag/` | all pipeline code; start with `rag/README.md` |
| `tests/` | unit tests, no network or GPU needed |
| `data/golden/` | the golden question set and the guides for writing questions |
| `docs/` | notes that are not code |

## Setup

    pip install -r requirements-rag.txt
    python -m pytest tests -q

Copy `.env.example` to `.env` (gitignored) for model settings and keys. Never commit `.env`.
