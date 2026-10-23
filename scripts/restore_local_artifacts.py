"""Restore only fingerprinted local artifacts from a trusted original project."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def restore(source: Path) -> dict[str, str]:
    source = source.resolve(strict=True)
    entries = json.loads((ROOT / "configs/artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    prepared = []
    for entry in entries:
        relative = Path(entry["path"])
        origin, destination = (source / relative).resolve(), (ROOT / relative).resolve()
        if not origin.is_relative_to(source) or not destination.is_relative_to(ROOT / "models"):
            raise ValueError("Artifact path must stay within the source and local model directories")
        payload = origin.read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source fingerprint mismatch: {relative}")
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != entry["sha256"]:
            raise FileExistsError(f"Refusing to replace a different local artifact: {relative}")
        prepared.append((relative, destination, payload))
    result = {}
    for relative, destination, payload in prepared:
        if destination.exists():
            result[relative.as_posix()] = "verified_existing"
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also rejects files appearing after validation.
        with destination.open("xb") as handle:
            handle.write(payload)
        result[relative.as_posix()] = "restored"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Trusted original project root")
    args = parser.parse_args()
    print(json.dumps(restore(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
