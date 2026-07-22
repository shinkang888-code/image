"""D: 중복 파일 정리 — 천재병렬(해시 CPU 병렬, USB 읽기 동시성 제한).

같은 SHA256 해시끼리 묶고, CreationTime(없으면 mtime)이 가장 이른 파일만 남긴다.
기본은 dry-run. --apply 일 때만 삭제.

게임/시스템 폴더는 기본 제외(설치 깨짐 방지).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EXCLUDE_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "steamlibrary",
    "diablo iv",
    "world of warcraft",
    "warcraft iii",
    "starcraft ii",
    "hearthstone",
    "heroes of the storm",
}

DEFAULT_EXCLUDE_SUFFIXES = {
    ".dropbox.device",
}


@dataclass
class FileMeta:
    path: str
    size: int
    ctime: float
    mtime: float

    @property
    def keep_key(self) -> tuple[float, float, str]:
        # 먼저 생성된 것 우선; ctime 동일하면 mtime, 그다음 경로
        return (self.ctime, self.mtime, self.path.lower())


def _should_skip_dir(name: str, exclude: set[str]) -> bool:
    return name.lower() in exclude


def iter_files(roots: list[Path], exclude_dirs: set[str], min_bytes: int) -> list[FileMeta]:
    out: list[FileMeta] = []
    for root in roots:
        if not root.exists():
            print(f"! skip missing root: {root}", flush=True)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # prune excluded dirs in-place
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d, exclude_dirs)]
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    st = fp.stat()
                except OSError as ex:
                    print(f"! stat fail {fp}: {ex}", flush=True)
                    continue
                if st.st_size < min_bytes:
                    continue
                out.append(FileMeta(
                    path=str(fp),
                    size=st.st_size,
                    ctime=getattr(st, "st_ctime", st.st_mtime),
                    mtime=st.st_mtime,
                ))
    return out


def sha256_file_safe(path: str) -> tuple[str, str | None, str | None]:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(8 * 1024 * 1024)
                if not b:
                    break
                h.update(b)
        return path, h.hexdigest(), None
    except OSError as ex:
        return path, None, str(ex)


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D: duplicate cleaner (parallel hash)")
    ap.add_argument("--root", default="D:\\", help="scan root")
    ap.add_argument("--apply", action="store_true", help="actually delete duplicates")
    ap.add_argument("--workers", type=int, default=4, help="parallel hash workers (USB: 2~4)")
    ap.add_argument("--min-mb", type=float, default=1.0, help="ignore files smaller than this MB")
    ap.add_argument("--include-games", action="store_true", help="also scan game libraries (dangerous)")
    ap.add_argument("--report", default="out/dedupe_report.jsonl")
    ap.add_argument("--only", action="append", default=[], help="only scan these relative top folders")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"root missing: {root}", file=sys.stderr)
        return 2

    # quick gate: can we list and read?
    try:
        next(root.iterdir())
    except OSError as ex:
        print(f"D: unreadable — STOP: {ex}", file=sys.stderr)
        return 2

    exclude = set(DEFAULT_EXCLUDE_DIR_NAMES)
    if args.include_games:
        exclude -= {
            "steamlibrary", "diablo iv", "world of warcraft", "warcraft iii",
            "starcraft ii", "hearthstone", "heroes of the storm",
        }

    if args.only:
        roots = [root / p for p in args.only]
    else:
        roots = []
        for p in root.iterdir():
            if not p.is_dir():
                continue
            if _should_skip_dir(p.name, exclude):
                print(f"exclude top: {p.name}")
                continue
            roots.append(p)

    min_bytes = int(args.min_mb * 1024 * 1024)
    print(f"roots={len(roots)} workers={args.workers} min_mb={args.min_mb} apply={args.apply}")
    for r in roots:
        print(f"  scan {r}")

    t0 = time.monotonic()
    files = iter_files(roots, exclude, min_bytes)
    print(f"candidates={len(files)} enumerate={time.monotonic()-t0:.1f}s")

    # size pre-group: only hash sizes that appear more than once
    by_size: dict[int, list[FileMeta]] = {}
    for fm in files:
        by_size.setdefault(fm.size, []).append(fm)
    to_hash = [fm for sz, group in by_size.items() if len(group) > 1 for fm in group]
    unique_sizes = sum(1 for g in by_size.values() if len(g) == 1)
    print(f"size-unique={unique_sizes} need-hash={len(to_hash)} size-collision-groups="
          f"{sum(1 for g in by_size.values() if len(g) > 1)}")

    hashes: dict[str, str] = {}
    errors = 0
    t1 = time.monotonic()
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(sha256_file_safe, fm.path): fm for fm in to_hash}
        for fut in as_completed(futs):
            path, digest, err = fut.result()
            done += 1
            if done % 50 == 0 or done == len(futs):
                print(f"  hashed {done}/{len(futs)} errors={errors}", flush=True)
            if err or not digest:
                errors += 1
                print(f"! hash fail {path}: {err}", flush=True)
                if "Incorrect function" in (err or "") or "not ready" in (err or "").lower():
                    print("D: I/O unstable — STOP", file=sys.stderr)
                    return 3
                continue
            hashes[path] = digest
    print(f"hash done in {time.monotonic()-t1:.1f}s errors={errors}")

    by_hash: dict[str, list[FileMeta]] = {}
    for fm in to_hash:
        dig = hashes.get(fm.path)
        if not dig:
            continue
        by_hash.setdefault(dig, []).append(fm)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    delete_list: list[FileMeta] = []
    keep_list: list[tuple[str, FileMeta, int]] = []  # hash, keeper, dup_count
    bytes_free = 0

    with report_path.open("w", encoding="utf-8") as rep:
        for dig, group in by_hash.items():
            if len(group) < 2:
                continue
            group_sorted = sorted(group, key=lambda x: x.keep_key)
            keeper = group_sorted[0]
            dups = group_sorted[1:]
            keep_list.append((dig, keeper, len(dups)))
            rec = {
                "sha256": dig,
                "size": keeper.size,
                "keep": keeper.path,
                "keep_ctime": fmt_ts(keeper.ctime),
                "delete": [
                    {"path": d.path, "ctime": fmt_ts(d.ctime)} for d in dups
                ],
            }
            rep.write(json.dumps(rec, ensure_ascii=False) + "\n")
            delete_list.extend(dups)
            bytes_free += keeper.size * len(dups)

    print(f"duplicate_groups={len(keep_list)} files_to_delete={len(delete_list)} "
          f"reclaim_gb={bytes_free/1024/1024/1024:.2f}")
    print(f"report={report_path.resolve()}")

    if not args.apply:
        print("dry-run only. re-run with --apply to delete.")
        for dig, keeper, n in keep_list[:20]:
            print(f"  KEEP {keeper.path}")
            print(f"       (+{n} dups, {keeper.size/1024/1024:.1f} MB)")
        if len(keep_list) > 20:
            print(f"  ... +{len(keep_list)-20} more groups in report")
        return 0

    deleted = 0
    failed = 0
    for d in delete_list:
        try:
            os.remove(d.path)
            deleted += 1
            print(f"DEL {d.path}")
        except OSError as ex:
            failed += 1
            print(f"! DEL fail {d.path}: {ex}")
            if "Incorrect function" in str(ex) or "not ready" in str(ex).lower():
                print("D: I/O unstable — STOP", file=sys.stderr)
                return 3
    print(f"deleted={deleted} failed={failed} reclaim_gb~={bytes_free/1024/1024/1024:.2f}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raise SystemExit(main())
