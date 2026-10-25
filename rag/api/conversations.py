"""Server-side conversations: the turns of one owner within one declared document scope.

A conversation is the list of question-and-answer turns a caller has asked inside one scope. The
service is the only caller of this module, and it supplies the owner from `current_owner`; nothing
here reads a request, and the caller never sends history (the store is the only source of turns).

Where a conversation lives depends on the scope it was declared with (decision D-01):

- exactly one document: `{root}/{doc_id}/chat/conversations/{id}.json`, inside that document's
  folder, so deleting the folder deletes the conversation with it;
- several documents or all documents: `{root}/_conversations/{owner_key}/{id}.json`, removed by
  `purge_document` when any document its scope touched is deleted (decision D-02).

The owner never appears in a path or a file: it is hashed into `owner_key`. Each file is
`{"header": {"id", "owner_key", "scope_key", "doc_ids", "created_at", "version": 1}, "turns": [...]}`
(decision D-07), written through a temporary file and an atomic replace. A stored turn may also carry
the optional `kind` ("clarify" when the turn was a clarifying question) and `topic_start` (true when
the turn started a new topic, so earlier turns are left out of later prompts).

Turns are read after the lease is taken and appended under the store lock to the list re-read
there, so a turn written between `open` and `lease` is neither hidden nor overwritten. Stored text
is untrusted when it comes back: `rag.query.history.render_block` neutralizes it before it reaches a
prompt.
"""
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from rag.query.guard import scan_text
from rag.query.history import CONVERSATION_MAX_STORED_WORDS, CONVERSATION_MAX_TURNS, HistoryTurn

logger = logging.getLogger("rag.conversations")
CONVERSATION_ID = re.compile(r"[0-9a-f]{32}")  # always used with fullmatch, so a trailing newline fails
DOCUMENT_ID = re.compile(r"[0-9a-f]{12}")  # the same shape as the service's document ids
CONVERSATIONS_DIR = "_conversations"  # never matches a document id, so the service's folder scans skip it
FORMAT_VERSION = 1
# A clarification is stored as a turn so the next turn knows not to clarify again (decision D-13).
TURN_KINDS = ("answer", "clarify")


class NoSuchConversation(Exception):
    """Unknown, malformed, another owner's or another scope's id: one exception, so every miss looks the same."""


class ConversationFull(Exception):
    """The turn cap, the stored-word cap or the prompt budget is reached; start a new conversation."""


class ConversationBusy(Exception):
    """Another request on the same conversation is still being answered."""


def owner_key(owner: str) -> str:
    """The owner as it appears on disk: a short hash, so the owner string is never written."""
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16]


def scope_of(doc_ids: Optional[Sequence[str]]) -> Tuple[str, Tuple[str, ...]]:
    """The scope key and the declared ids, de-duplicated and sorted, so order and repeats do not matter."""
    if doc_ids is None:
        return "all", ()
    ids = tuple(sorted(dict.fromkeys(doc_ids)))
    if not ids:
        raise ValueError(f"empty document scope {doc_ids!r}")
    for doc_id in ids:
        if not isinstance(doc_id, str) or not DOCUMENT_ID.fullmatch(doc_id):
            raise ValueError(f"bad document id {doc_id!r}")
    if len(ids) == 1:
        return ids[0], ids
    return ",".join(ids), ids


def new_turn(question: str, answer: str, doc_ids: Sequence[str], query_id: str,
             rewritten: Optional[str] = None, kind: str = "answer", topic_start: bool = False) -> Dict[str, Any]:
    """One stored turn (decision D-09), with the scanner rule names found in the question and the answer.

    `kind` and `topic_start` are written only when they differ from the default, so files and tests
    from Phase 2 keep their exact shape; readers use `turn.get("kind", "answer")` and
    `turn.get("topic_start", False)`.
    """
    if kind not in TURN_KINDS:
        raise ValueError(f"unknown turn kind {kind!r}")
    turn: Dict[str, Any] = {
        "question": question,
        "rewritten": rewritten,
        "answer": answer,
        "doc_ids": list(doc_ids),
        "asked_at": datetime.now(timezone.utc).isoformat(),
        "query_id": query_id,
        "scan": sorted(set(scan_text(question).rules) | set(scan_text(answer).rules)),
    }
    if kind != "answer":
        turn["kind"] = kind
    if topic_start:
        turn["topic_start"] = True
    return turn


def to_history_turns(turns: Sequence[Dict[str, Any]]) -> List[HistoryTurn]:
    return [
        HistoryTurn(
            question=turn["question"],
            answer=turn["answer"],
            asked_at=turn["asked_at"],
            rewritten=turn.get("rewritten"),
        )
        for turn in turns
    ]


@dataclass(frozen=True)
class Conversation:
    """A conversation as opened for one request; `doc_ids` is the declared scope (empty for all documents)."""

    id: str
    owner_key: str
    scope_key: str
    doc_ids: Tuple[str, ...]
    path: Path
    is_new: bool


class Lease:
    """The right to add one turn to a conversation. `release` is idempotent and may be called from any
    thread, up to three times per request, so the busy set never keeps a finished request."""

    def __init__(self, store: "ConversationStore", key: Tuple[str, str]):
        self._store = store
        self._key = key
        self._held = True

    def release(self) -> None:
        with self._store._mutex:
            if self._held:
                self._held = False
                self._store._busy.discard(self._key)


class ConversationStore:
    """Owner-scoped, deletable conversation storage under the uploads root.

    Two locks: `lock` (a re-entrant lock) serialises every file write, every purge, and the service's
    folder removal during a document delete; `_mutex` guards only the busy set of leased conversations.

    The service calls `purge_document` after removing the document folder and before it clears the
    document from its deleting set, inside `with store.lock:`, so a writer either finishes first and
    its file is removed, or starts later and is dropped by the liveness check.
    """

    def __init__(self, root: Path, max_turns: int = CONVERSATION_MAX_TURNS,
                 max_words: int = CONVERSATION_MAX_STORED_WORDS):
        self.root = Path(root)
        self.max_turns = max_turns
        self.max_words = max_words
        self.lock = threading.RLock()
        self._mutex = threading.Lock()
        self._busy: Set[Tuple[str, str]] = set()
        self.dropped_writes = 0

    # ---- paths and files ----------------------------------------------------------------

    def _folder(self, key: str, doc_ids: Tuple[str, ...]) -> Path:
        if len(doc_ids) == 1:
            return self.root / doc_ids[0] / "chat" / "conversations"
        return self.root / CONVERSATIONS_DIR / key

    @staticmethod
    def _retry(action, errors, seconds: float = 2.0):
        """Windows briefly refuses to open a file that another thread is replacing, so retry
        for a short while instead of failing the request."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                return action()
            except errors:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    def _read(self, path: Path) -> Dict[str, Any]:
        return self._retry(
            lambda: json.loads(path.read_text(encoding="utf-8")),
            (PermissionError, json.JSONDecodeError),
        )

    def _atomic_write(self, path: Path, text: str) -> None:
        """Write to a temporary file and swap it in, so a reader sees the old or new file, never half."""
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        self._retry(lambda: os.replace(temporary, path), PermissionError)

    # ---- lookup and lease ---------------------------------------------------------------

    def open(self, owner: str, doc_ids: Optional[Sequence[str]], conversation_id: Optional[str]) -> Conversation:
        """Start a new conversation (id None) or find an existing one of this owner and this exact scope.
        Writes nothing and takes no lease; every miss raises NoSuchConversation."""
        key = owner_key(owner)
        scope_key, declared = scope_of(doc_ids)
        if conversation_id is None:
            new_id = secrets.token_hex(16)
            path = self._folder(key, declared) / (new_id + ".json")
            return Conversation(new_id, key, scope_key, declared, path, True)
        if not isinstance(conversation_id, str) or not CONVERSATION_ID.fullmatch(conversation_id):
            logger.info("conversation lookup refused: malformed")
            raise NoSuchConversation()
        path = self._folder(key, declared) / (conversation_id + ".json")
        try:
            header = self._read(path)["header"]
            matches = (
                header["version"] == FORMAT_VERSION
                and header["id"] == conversation_id
                and header["owner_key"] == key
                and header["scope_key"] == scope_key
            )
        except FileNotFoundError:
            logger.info("conversation lookup refused: missing")
            raise NoSuchConversation() from None
        except (OSError, ValueError, KeyError, TypeError):
            logger.info("conversation lookup refused: unreadable")
            raise NoSuchConversation() from None
        if not matches:
            logger.info("conversation lookup refused: header mismatch")
            raise NoSuchConversation()
        return Conversation(conversation_id, key, scope_key, declared, path, False)

    def lease(self, conversation: Conversation) -> Lease:
        key = (conversation.owner_key, conversation.id)
        with self._mutex:
            if key in self._busy:
                raise ConversationBusy()
            self._busy.add(key)
        return Lease(self, key)

    def load_turns(self, conversation: Conversation) -> List[Dict[str, Any]]:
        """The stored turns, read fresh from the file (call after taking the lease)."""
        if conversation.is_new:
            return []
        try:
            return list(self._read(conversation.path)["turns"])
        except FileNotFoundError:
            raise NoSuchConversation() from None
        except (OSError, ValueError, KeyError, TypeError):
            raise NoSuchConversation() from None

    # ---- writing ------------------------------------------------------------------------

    def _drop(self) -> bool:
        self.dropped_writes += 1
        logger.warning("dropped %d conversation write(s)", self.dropped_writes)
        return False

    def _make_folders(self, conversation: Conversation) -> None:
        """Create only the folders the store owns, one level at a time and never with parents, so a
        document folder removed by a delete is never recreated (FileNotFoundError instead)."""
        if len(conversation.doc_ids) == 1:
            chat = self.root / conversation.doc_ids[0] / "chat"
            chat.mkdir(exist_ok=True)
            (chat / "conversations").mkdir(exist_ok=True)
        else:
            top = self.root / CONVERSATIONS_DIR
            top.mkdir(exist_ok=True)
            (top / conversation.owner_key).mkdir(exist_ok=True)

    def append_turn(self, conversation: Conversation, turn: Dict[str, Any],
                    alive: Callable[[Sequence[str]], bool]) -> bool:
        """Append one turn under the store lock. Returns False, and counts a dropped write, when the
        file is damaged, a delete removed the conversation or one of its documents, or a folder is gone."""
        with self.lock:
            existing: Optional[Dict[str, Any]] = None
            if conversation.path.exists():
                try:
                    existing = self._read(conversation.path)
                    header_ids = list(existing["header"]["doc_ids"])
                    list(existing["turns"])
                except (OSError, ValueError, KeyError, TypeError):
                    return self._drop()  # never overwrite a damaged file; a purge removes it
            else:
                header_ids = []
                if not conversation.is_new:
                    return self._drop()  # a delete purged it: never resurrect it
            union = sorted(set(conversation.doc_ids) | set(turn["doc_ids"]) | set(header_ids))
            if not alive(union):
                return self._drop()
            if existing is None:
                data: Dict[str, Any] = {
                    "header": {
                        "id": conversation.id,
                        "owner_key": conversation.owner_key,
                        "scope_key": conversation.scope_key,
                        "doc_ids": [],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "version": FORMAT_VERSION,
                    },
                    "turns": [],
                }
            else:
                data = existing
            data["header"]["doc_ids"] = union
            data["turns"].append(dict(turn))
            try:
                self._make_folders(conversation)
                self._atomic_write(conversation.path, json.dumps(data, indent=1))
            except FileNotFoundError:
                return self._drop()
            return True

    # ---- caps and the delete cascade ----------------------------------------------------

    def check_room(self, turns: Sequence[Dict[str, Any]]) -> None:
        """Refuse the next turn before retrieval and before any model call, so a conversation holds at
        most `max_turns` turns and stops growing once its stored words reach `max_words`."""
        if len(turns) >= self.max_turns:
            raise ConversationFull()
        words = sum(len(turn["question"].split()) + len(turn["answer"].split()) for turn in turns)
        if words >= self.max_words:
            raise ConversationFull()

    def _unlink(self, path: Path) -> None:
        self._retry(lambda: path.unlink(missing_ok=True), PermissionError)

    def purge_document(self, owner: str, doc_id: str) -> int:
        """Remove every cross-document conversation of this owner whose header or any turn names
        `doc_id`, every file that cannot be parsed and every temporary file. Returns the count."""
        with self.lock:
            folder = self.root / CONVERSATIONS_DIR / owner_key(owner)
            if not folder.is_dir():
                return 0
            removed = 0
            for temporary in folder.glob("*.json.tmp"):  # a crash mid-write can leave conversation text here
                self._unlink(temporary)
                removed += 1
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    touched = set(data["header"]["doc_ids"])
                    for turn in data["turns"]:
                        touched.update(turn["doc_ids"])
                    remove = doc_id in touched  # exact membership, never a substring test
                except FileNotFoundError:
                    continue
                except (OSError, ValueError, KeyError, TypeError):
                    remove = True  # cannot be proven unrelated to the deleted document
                if remove:
                    self._unlink(path)
                    removed += 1
            if removed:
                logger.info("removed %d conversation file(s) after a document delete", removed)
            return removed
