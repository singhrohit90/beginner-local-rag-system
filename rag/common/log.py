import logging


def setup_logging() -> None:
    """INFO for our own messages, but silence per-request chatter from the HTTP and model libraries."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx", "httpcore", "google_genai", "google.genai", "huggingface_hub",
                  "sentence_transformers", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
