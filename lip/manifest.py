"""매니페스트 — 완료된 프롬프트 id 를 append-only JSONL 로 기록.

재개(resume): 이미 완료한 id 는 건너뛴다.
중복제거(dedup): 같은 (prompt id, seed) 조합은 한 번만.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class Manifest:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._done: set[str] = set()
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._done.add(json.loads(line)["key"])
                    except (json.JSONDecodeError, KeyError):
                        continue

    @staticmethod
    def key(prompt_id: str, seed: int) -> str:
        return f"{prompt_id}:{seed}"

    def has(self, prompt_id: str, seed: int) -> bool:
        return self.key(prompt_id, seed) in self._done

    def record(self, prompt_id: str, seed: int, tag: str, files: list[str]) -> None:
        k = self.key(prompt_id, seed)
        self._done.add(k)
        entry = {"key": k, "id": prompt_id, "seed": seed, "tag": tag, "files": files}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def __len__(self) -> int:
        return len(self._done)
