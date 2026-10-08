"""The ingestion pipeline: PDF in, searchable index out. It only runs the steps in order.

    python -m rag.ingestion.pipeline data/raw/ddia.pdf --chunker semantic

    extract.py  ->  chunk.py  ->  index.py
    pages.jsonl     chunks/<strategy>.jsonl     data/processed/index/...

Each step is a module you can run and read alone. Every stage skips work whose output already
exists unless --force is given, because extraction and embedding are the slow parts.
"""

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rag.common.config import PROCESSED_DIR
from rag.common.embed import Embedder, get_embedder
from rag.common.log import setup_logging
from rag.common.store import VectorIndex
from rag.ingestion.chunk import STRATEGIES, make_chunker
from rag.ingestion.chunking.base import ChunkSet, load_chunkset
from rag.ingestion.chunking.document import Document
from rag.ingestion.extract import extract_pages, extract_toc, save_pages
from rag.ingestion.index import get_index

logger = logging.getLogger("rag.ingestion")


@dataclass
class IngestResult:
    chunkset: ChunkSet
    index: VectorIndex


def ingest(
    pdf: Path,
    chunker: str = "semantic",
    embedder_spec: str = "st:sentence-transformers/all-mpnet-base-v2",
    out_dir: Path = PROCESSED_DIR,
    force: bool = False,
    embedder: Optional[Embedder] = None,  # pass one in to reuse a loaded model (the API does)
) -> IngestResult:
    pages_path = out_dir / f"{pdf.stem}.pages.jsonl"
    toc_path = out_dir / f"{pdf.stem}.toc.json"
    embedder = embedder or get_embedder(embedder_spec)

    if force or not pages_path.exists():
        logger.info("step 1 extract: %s", pdf)
        save_pages(extract_pages(pdf), pages_path)
        toc_path.write_text(json.dumps(extract_toc(pdf), indent=1), encoding="utf-8")
    else:
        logger.info("step 1 extract: reusing %s", pages_path)

    chunks_dir = out_dir / "chunks"
    if force or not (chunks_dir / f"{chunker}.jsonl").exists():
        logger.info("step 2 chunk: %s", chunker)
        document = Document.from_files(pages_path, toc_path)
        chunkset = make_chunker(chunker, embedder=embedder).chunk(document)
        chunkset.save(chunks_dir)
    else:
        logger.info("step 2 chunk: reusing %s", chunks_dir / f"{chunker}.jsonl")
        chunkset = load_chunkset(chunks_dir, chunker)

    logger.info("step 3 index: %d chunks", len(chunkset.chunks))
    index = get_index(chunkset, embedder, "plain", rebuild=force, root=out_dir)
    return IngestResult(chunkset, index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--chunker", default="semantic", choices=STRATEGIES)
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--force", action="store_true", help="redo every step")
    args = parser.parse_args()
    setup_logging()
    result = ingest(args.pdf, args.chunker, args.embedder, force=args.force)
    print(f"{len(result.chunkset.chunks)} chunks indexed ({args.chunker})")


if __name__ == "__main__":
    main()
