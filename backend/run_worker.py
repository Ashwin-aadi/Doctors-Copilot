"""Document-processing worker entrypoint.

`rq worker` forks a child process per job, which POSIX gives it for free and
Windows does not have at all -- there, the worker starts and then dies on the
first job with "Fork not available". `SimpleWorker` runs the job in the worker
process itself, which is what makes the queue work identically on both, at the
cost of no per-job process isolation (acceptable: these jobs are OCR, not
untrusted code).

Without this running, every upload sits at status="queued" forever: nothing
OCRs the file, no LabResult rows are written, and the copilot brief has no
patient evidence to reason about.

Usage: python run_worker.py [--burst]
"""

import argparse
import sys

from redis import Redis
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.core.config import get_settings
from app.workers.queue import QUEUE_NAME

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--burst",
        action="store_true",
        help="drain the queue and exit, instead of waiting for more work",
    )
    args = parser.parse_args()

    connection = Redis.from_url(get_settings().redis_url)
    worker = SimpleWorker([Queue(QUEUE_NAME, connection=connection)], connection=connection)
    if sys.platform == "win32":
        # rq enforces the per-job timeout with SIGALRM, which exists only on
        # POSIX -- on Windows every job dies with AttributeError before it
        # runs. The timer-thread implementation is rq's own replacement.
        worker.death_penalty_class = TimerDeathPenalty
    print(f"worker listening on '{QUEUE_NAME}' ({sys.platform})", flush=True)
    worker.work(burst=args.burst)
