"""Run all W3 tests and save the actual result and a readable log."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.w3_workflow import digest, dump_json, validate_output_targets


def main():
    report_dir = ROOT / "reports"
    result_path = report_dir / "w3_test_results.json"
    log_path = report_dir / "w3_test_results.log"
    validate_output_targets(report_dir, [result_path, log_path])
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_w3*.py")
    stream = io.StringIO()
    start = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    log = stream.getvalue()
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log, encoding="utf-8")
    source_files = [*sorted((ROOT / "tests").glob("test_w3*.py")), Path(__file__),
                    ROOT / "src/data/clean.py", ROOT / "src/data/preprocess.py",
                    ROOT / "src/data/w3_workflow.py", ROOT / "scripts/run_week3.py"]
    evidence = {
        "status": "passed" if result.wasSuccessful() and result.testsRun > 0 else "failed",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "command": "python scripts/test_week3.py",
        "test_pattern": "tests/test_w3*.py", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses),
        "duration_seconds": round(time.perf_counter() - start, 3),
        "log": "reports/w3_test_results.log", "log_sha256": digest(log_path),
        "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in source_files},
    }
    dump_json(result_path, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    if evidence["status"] != "passed":
        print(log)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
