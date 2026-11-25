#!/usr/bin/env python3
"""Validate repo.json, mappings/index.json, and mappings/*.ndjson for schema, dedup, and privacy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
REPO_JSON = ROOT / "repo.json"
MAPPINGS_DIR = ROOT / "mappings"
INDEX_JSON = MAPPINGS_DIR / "index.json"

ALLOWED_KINDS = {"bangumi_archive", "offline_sqlite", "tag_dictionary", "mapping_pack"}
ALLOWED_TARGETS = {"bangumi", "gallery_v1", "mangaalpha_meta_v1"}
PII_PATTERNS = [
    re.compile(r"(/home/|/Users/|[A-Za-z]:\\\\)", re.IGNORECASE),
    re.compile(r"\b(?:192\.168|10\.\d+|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b"),
    re.compile(r"\b(?:ghp_|gho_|github_pat_|fk115_)[A-Za-z0-9_]{8,}\b"),
    re.compile(r"https?://", re.IGNORECASE),
]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def validate_repo_json() -> None:
    if not REPO_JSON.is_file():
        fail("repo.json missing")
    data = json.loads(REPO_JSON.read_text(encoding="utf-8"))
    if data.get("schema") != "mangaalpha-repo-v1":
        fail(f"invalid repo.json schema: {data.get('schema')}")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("repo.json must declare a non-empty sources list")
    seen_ids: set[str] = set()
    for idx, src in enumerate(sources):
        if not isinstance(src, dict):
            fail(f"sources[{idx}] must be an object")
        sid = str(src.get("id") or "").strip()
        if not sid or sid in seen_ids:
            fail(f"duplicate or empty source id at sources[{idx}]: {sid!r}")
        seen_ids.add(sid)
        kind = src.get("kind")
        if kind not in ALLOWED_KINDS:
            fail(f"sources[{idx}] unsupported kind: {kind!r}")
        if not src.get("name"):
            fail(f"sources[{idx}] missing name")
        if not (src.get("downloadUrl") or src.get("manifestUrl")):
            fail(f"sources[{idx}] must specify downloadUrl or manifestUrl")
    print(f"OK: repo.json ({len(sources)} sources)")


def validate_ndjson_file(path: Path) -> tuple[int, str]:
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    seen_keys: set[tuple[str, str, str]] = set()
    count = 0
    for lineno, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rec = json.loads(stripped)
        except ValueError as exc:
            fail(f"{path.name}:{lineno} invalid JSON: {exc}")
        if not isinstance(rec, dict):
            fail(f"{path.name}:{lineno} record must be a JSON object")
        if rec.get("schema") != "mangaalpha_mapping_v1":
            fail(f"{path.name}:{lineno} invalid schema: {rec.get('schema')!r}")
        key = str(rec.get("key") or "").strip()
        raw_key = str(rec.get("rawKey") or "").strip()
        author = str(rec.get("author") or "").strip()
        target_src = str(rec.get("targetSource") or "").strip()
        target_id = str(rec.get("targetId") or "").strip()
        if not key or len(key) > 200:
            fail(f"{path.name}:{lineno} invalid key")
        if len(raw_key) > 200 or len(author) > 120:
            fail(f"{path.name}:{lineno} rawKey/author too long")
        if target_src not in ALLOWED_TARGETS:
            fail(f"{path.name}:{lineno} unsupported targetSource: {target_src!r}")
        if not target_id or len(target_id) > 64:
            fail(f"{path.name}:{lineno} invalid targetId")
        if target_src == "bangumi" and not target_id.isdigit():
            fail(f"{path.name}:{lineno} bangumi targetId must be numeric: {target_id!r}")
        for field_name, val in (("key", key), ("rawKey", raw_key), ("author", author), ("targetId", target_id)):
            for pat in PII_PATTERNS:
                if pat.search(val):
                    fail(f"{path.name}:{lineno} {field_name} matched forbidden privacy/URL pattern")
        dedup_key = (key.casefold(), author.casefold(), target_src)
        if dedup_key in seen_keys:
            fail(f"{path.name}:{lineno} duplicate mapping key: {dedup_key}")
        seen_keys.add(dedup_key)
        count += 1
    return count, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()

    validate_repo_json()
    ndjson_files = sorted(MAPPINGS_DIR.glob("*.ndjson"))
    if not ndjson_files:
        fail("no mappings/*.ndjson files found")

    packs = []
    for p in ndjson_files:
        count, digest = validate_ndjson_file(p)
        packs.append({
            "id": p.stem,
            "file": p.name,
            "downloadUrl": f"https://raw.githubusercontent.com/BlackMuseCode/mangaalpha-metadata-repo/main/mappings/{p.name}",
            "entryCount": count,
            "sha256": digest,
        })
        print(f"OK: {p.name} ({count} entries, sha256={digest[:12]}...)")

    if args.rebuild_index:
        index_obj = {
            "schema": "mangaalpha-mapping-index-v1",
            "version": datetime.now(timezone.utc).strftime("%Y.%m.%d.1"),
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "packs": packs,
        }
        INDEX_JSON.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {INDEX_JSON}")
        return 0

    if not INDEX_JSON.is_file():
        fail("mappings/index.json missing (run --rebuild-index)")
    idx_data = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    if idx_data.get("schema") != "mangaalpha-mapping-index-v1":
        fail("invalid mappings/index.json schema")
    idx_packs = {p.get("file"): p for p in idx_data.get("packs") or [] if isinstance(p, dict)}
    for p in packs:
        recorded = idx_packs.get(p["file"])
        if not recorded:
            fail(f"mappings/index.json missing entry for {p['file']}")
        if recorded.get("sha256") != p["sha256"] or recorded.get("entryCount") != p["entryCount"]:
            fail(f"mappings/index.json out of sync for {p['file']} (run python3 scripts/validate_mappings.py --rebuild-index)")
    print("OK: mappings/index.json verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
