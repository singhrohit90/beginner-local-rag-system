# Patterns kept from the original fork

The original fork was a Streamlit chatbot over OpenSearch. It was removed from this repo because nothing in `rag/` used it. These three ideas are worth copying later. The full files stay in git history on `main` (`git show main:src/opensearch.py`).

## 1. OpenSearch hybrid query (from `src/opensearch.py`)

Use when the numpy vector index is replaced by a real vector database. One request runs keyword and vector search and a search pipeline fuses the scores.

```python
query_body = {
    "_source": {"exclude": ["embedding"]},          # do not return the vectors
    "query": {"hybrid": {"queries": [
        {"match": {"text": {"query": query_text}}},                         # keyword
        {"knn": {"embedding": {"vector": query_embedding, "k": top_k}}},    # vector
    ]}},
    "size": top_k,
}
client.search(index=INDEX, body=query_body, search_pipeline="nlp-search-pipeline")
```

Why it matters: our own fusion lives in `rag/retrieval/fusion.py`. The database pipeline does the same job server side, so compare the two on the golden set before switching. The search pipeline must be created first (not shown in the fork's search code).

## 2. Index mapping (from `src/index_config.json`)

```json
{
  "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0, "knn": true}},
  "mappings": {"properties": {
    "text": {"type": "text"},
    "embedding": {"type": "knn_vector", "dimension": "<embedding dimension>",
                  "method": {"engine": "faiss", "space_type": "l2", "name": "hnsw", "parameters": {}}},
    "document_name": {"type": "keyword"}
  }}
}
```

Why it matters: our vectors are compared by cosine, so use `cosinesimil` (or normalise the vectors and keep `l2`). Add `source`, `page_start`, `page_end` and `element_kind` as keyword or integer fields, because the per-source cap and the eval both need them.

## 3. OCR fallback (from `src/ocr.py`)

Idea: read the text layer of every page first, and run OCR only on pages that have none. The fork used `PyPDF2` for text and `pytesseract` on the page's embedded images.

```python
page_text = page.extract_text()
if page_text:
    text += page_text
else:
    for image in page.images:                    # scanned page: OCR each embedded image
        text += pytesseract.image_to_string(Image.open(io.BytesIO(image.data)))
```

Why it matters: this is the starting point for scanned documents (Stage 4 of the reorganisation plan). Gaps in the fork's version to fix: no OCR confidence recorded, OCR output not checked by the injection scanner, errors swallowed per page, and page boundaries lost because text is appended without page numbers.
