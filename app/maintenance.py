from __future__ import annotations

import argparse
import json

from .database import SessionLocal
from .services.job_recovery import recover_stale_analysis_jobs
from .services.retention import cleanup_expired_security_records


def main() -> None:
    parser = argparse.ArgumentParser(description="MindMate maintenance tasks")
    parser.add_argument("task", choices=("recover-analysis", "cleanup-security"))
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = recover_stale_analysis_jobs(db) if args.task == "recover-analysis" else cleanup_expired_security_records(db)
        print(json.dumps(result, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
