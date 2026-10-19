"""Tiny in-memory job runner for long setup actions (installs, whichllm runs)."""

import threading
import time
import uuid

_jobs = {}


def start(fn, *args, **kwargs):
    """Run fn(log, *args, **kwargs) on a thread. Returns the job id."""
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "running",
        "log": [],
        "result": None,
        "error": None,
        "started": time.time(),
    }
    _jobs[job_id] = job

    def log(line):
        job["log"].append(str(line))
        if len(job["log"]) > 500:
            del job["log"][:100]

    def run():
        try:
            job["result"] = fn(*args, log=log, **kwargs)
            job["status"] = "done"
        except Exception as e:
            job["error"] = str(e)
            job["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return job_id


def get(job_id):
    return _jobs.get(job_id)
