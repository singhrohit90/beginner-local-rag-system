"""Run PDF extraction in a child process with a time limit and a memory limit (API uploads only).

A hostile PDF under the upload size limit can still hold huge page streams that expand a lot.
Extraction runs in a separate process so that such a file can only hurt the child:

    - time:   the child is killed when it runs longer than `timeout` seconds (all platforms).
    - memory: a Job Object on Windows (ctypes) or RLIMIT_AS on Linux and macOS caps the child's
              address space. If the cap cannot be set, a warning is logged and only the other
              limits apply.
    - output: each page's text is cut at `max_page_chars` inside extraction.

The CLI and the experiments call extract_pages directly and never come through here.
"""

import json
import logging
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MEMORY_MB = 2048
DEFAULT_MAX_PAGE_CHARS = 200_000  # a dense printed page is about 5,000 characters


class ExtractionLimit(Exception):
    """Extraction was stopped or failed inside the sandbox. The message is safe to show the user
    (no paths)."""


def _extract_to_files(pdf: str, pages_path: str, toc_path: str, max_page_chars: int) -> None:
    """The real work, run in the child. Writes next to the final names and renames at the end,
    so a killed child never leaves a half-written pages file that a later run would reuse."""
    from rag.ingestion.extract import extract_pages, extract_toc, save_pages

    pdf_path, pages_out, toc_out = Path(pdf), Path(pages_path), Path(toc_path)
    pages_tmp = pages_out.with_name(pages_out.name + ".tmp")
    toc_tmp = toc_out.with_name(toc_out.name + ".tmp")
    save_pages(extract_pages(pdf_path, max_page_chars=max_page_chars), pages_tmp)
    toc_tmp.write_text(json.dumps(extract_toc(pdf_path), indent=1), encoding="utf-8")
    os.replace(toc_tmp, toc_out)
    os.replace(pages_tmp, pages_out)  # last, because the pipeline reuses the pages file when it exists


def _child(target: Callable, args: tuple, memory_mb: int) -> None:
    if sys.platform != "win32":  # on Windows the parent puts the child in a Job Object instead
        try:
            import resource

            limit = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ImportError, ValueError, OSError):
            logger.warning("could not set a memory limit on the extraction process")
    target(*args)


def _limit_memory_windows(pid: int, memory_mb: int) -> bool:
    """Put the process in a Job Object with a per-process memory cap. Returns False on failure."""
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("Basic", BasicLimits), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    process_memory_limit, kill_on_close = 0x100, 0x2000
    extended_limit_class = 9
    set_quota, terminate = 0x0100, 0x0001  # process access rights

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return False
    limits = ExtendedLimits()
    limits.Basic.LimitFlags = process_memory_limit | kill_on_close
    limits.ProcessMemoryLimit = memory_mb * 1024 * 1024
    handle = kernel32.OpenProcess(set_quota | terminate, False, pid)
    ok = bool(handle) and bool(kernel32.SetInformationJobObject(
        job, extended_limit_class, ctypes.byref(limits), ctypes.sizeof(limits))) \
        and bool(kernel32.AssignProcessToJobObject(job, handle))
    if handle:
        kernel32.CloseHandle(handle)
    # The job handle stays open on purpose: closing it would kill the child (kill_on_close). It
    # is released when this process exits, or below once the child is done.
    _JOBS[pid] = job if ok else None
    if not ok:
        kernel32.CloseHandle(job)
    return ok


_JOBS: dict = {}


def _release_job(pid: int) -> None:
    job = _JOBS.pop(pid, None)
    if job:
        import ctypes

        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(job))


def run_limited(target: Callable, args: tuple = (), timeout: float = DEFAULT_TIMEOUT_SECONDS,
                memory_mb: int = DEFAULT_MEMORY_MB) -> None:
    """Run target(*args) in a fresh process. Raise ExtractionLimit on timeout or failure."""
    context = multiprocessing.get_context("spawn")  # a clean interpreter: no copy of the API's models
    process = context.Process(target=_child, args=(target, args, memory_mb), daemon=True)
    process.start()
    try:
        if sys.platform == "win32" and not _limit_memory_windows(process.pid, memory_mb):
            logger.warning("could not set a memory limit on the extraction process")
        process.join(timeout)
        if process.is_alive():
            process.kill()
            process.join()
            raise ExtractionLimit(f"PDF extraction took longer than {int(timeout)} seconds and was stopped")
        if process.exitcode != 0:
            raise ExtractionLimit(
                f"PDF extraction failed (exit code {process.exitcode}); the file may be damaged or "
                f"need more than {memory_mb} MB of memory"
            )
    finally:
        if process.is_alive():
            process.kill()
        if sys.platform == "win32":
            _release_job(process.pid)


def extract_in_sandbox(pdf: Path, pages_path: Path, toc_path: Path,
                       timeout: float = DEFAULT_TIMEOUT_SECONDS, memory_mb: int = DEFAULT_MEMORY_MB,
                       max_page_chars: int = DEFAULT_MAX_PAGE_CHARS,
                       target: Optional[Callable] = None) -> None:
    """Extract pages and bookmarks of `pdf` into pages_path and toc_path inside a limited child.
    `target` replaces the worker, for tests."""
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    run_limited(target or _extract_to_files,
                (str(pdf), str(pages_path), str(toc_path), max_page_chars), timeout, memory_mb)
