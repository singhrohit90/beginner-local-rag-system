"""Worker functions for tests/test_sandbox.py. They live here, with no heavy imports, because the
child process imports this module before it can run them, and that import itself counts against
the child's memory limit."""

import time


def sleep_forever(*args):
    time.sleep(120)


def use_a_gigabyte(*args):
    hog = bytearray(1024 * 1024 * 1024)  # more than the 512 MB the test allows
    hog[-1] = 1


def fail_quietly(*args):
    raise SystemExit(3)


def start_another_process(*args):
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", "pass"], check=True)  # refused: the job allows one process
