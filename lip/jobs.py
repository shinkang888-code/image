"""작업제어 코어 — 생성 작업 큐 + 이벤트 + 제어 (LinkNode 명령큐 패턴 이식).

LinkNode `src/lib/commands/store.ts` 의 명령 생명주기(pending→queued→running→
completed/failed/cancelled)와 대시보드 집계(`dashboard/summary.ts`)를
이미지 공장 작업에 맞게 이식. 스레드 안전, 무의존(stdlib).

상태 매핑:  LinkNode                 →  LIP
           pending/queued/running   →  pending / generating / optimizing
           completed/failed/cancelled → done / failed / cancelled
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field

JobStatus = str  # pending | generating | optimizing | done | failed | cancelled

STATUS_LABELS = {
    "pending": "대기",
    "generating": "생성 중",
    "optimizing": "최적화 중",
    "done": "완료",
    "failed": "실패",
    "cancelled": "취소",
}


@dataclass
class GenJob:
    id: str
    prompt_id: str
    tag: str
    seed: int
    positive: str
    node: str = ""                 # 처리한 Compute Node 이름
    status: JobStatus = "pending"
    take: int = 0                  # 시드 변주 회차 (voicebox 'takes' 패턴)
    attempt: int = 1               # 재시도 횟수
    error: str | None = None
    files: list[str] = field(default_factory=list)
    bytes_total: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["status_label"] = STATUS_LABELS.get(self.status, self.status)
        return d


@dataclass
class Event:
    ts: float
    level: str      # info | success | warning | error
    message: str


class JobStore:
    """스레드 안전 작업 저장소 + 이벤트 로그 + 공장 제어 플래그."""

    def __init__(self, max_events: int = 300):
        self._lock = threading.Lock()
        self._jobs: dict[str, GenJob] = {}
        self._order: list[str] = []
        self._events: deque[Event] = deque(maxlen=max_events)
        self._paused = threading.Event()   # set = 일시정지
        self._stopped = threading.Event()  # set = 중지 요청
        self._cancel: set[str] = set()     # 취소된 prompt_id
        self.started_at = time.time()

    # --- 작업 생명주기 ---
    def create(self, job: GenJob) -> GenJob:
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        return job

    def mark(self, job_id: str, status: JobStatus, **fields) -> None:
        now = time.time()
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return
            j.status = status
            if status == "generating" and j.started_at is None:
                j.started_at = now
            if status in ("done", "failed", "cancelled"):
                j.completed_at = now
            for k, v in fields.items():
                setattr(j, k, v)

    def event(self, level: str, message: str) -> None:
        with self._lock:
            self._events.append(Event(ts=time.time(), level=level, message=message))

    # --- 제어 (LinkNode cancel/큐 제어 대응) ---
    def pause(self) -> None:
        self._paused.set()
        self.event("warning", "공장 일시정지")

    def resume(self) -> None:
        self._paused.clear()
        self.event("info", "공장 재개")

    def stop(self) -> None:
        self._stopped.set()
        self.event("warning", "공장 중지 요청")

    def cancel(self, prompt_id: str) -> None:
        with self._lock:
            self._cancel.add(prompt_id)
        self.event("warning", f"작업 취소: {prompt_id}")

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    @property
    def should_stop(self) -> bool:
        return self._stopped.is_set()

    def is_cancelled(self, prompt_id: str) -> bool:
        with self._lock:
            return prompt_id in self._cancel

    # --- 조회 ---
    def jobs(self, limit: int = 50) -> list[GenJob]:
        with self._lock:
            ids = self._order[-limit:][::-1]
            return [self._jobs[i] for i in ids]

    def events(self, limit: int = 50) -> list[Event]:
        with self._lock:
            return list(self._events)[-limit:][::-1]

    def summary(self) -> dict:
        """대시보드 집계 (LinkNode buildDashboardSummary 대응)."""
        with self._lock:
            jobs = list(self._jobs.values())
        counts: dict[str, int] = {k: 0 for k in STATUS_LABELS}
        by_tag: dict[str, int] = {}
        bytes_total = 0
        done_times: list[float] = []
        for j in jobs:
            counts[j.status] = counts.get(j.status, 0) + 1
            if j.status == "done":
                by_tag[j.tag] = by_tag.get(j.tag, 0) + 1
                bytes_total += j.bytes_total
                if j.completed_at:
                    done_times.append(j.completed_at)
        elapsed_min = max((time.time() - self.started_at) / 60.0, 1e-9)
        done = counts.get("done", 0)
        throughput = round(done / elapsed_min, 1)  # 분당 완료 장수
        return {
            "totals": {
                "total": len(jobs),
                "done": done,
                "failed": counts.get("failed", 0),
                "cancelled": counts.get("cancelled", 0),
                "running": counts.get("generating", 0) + counts.get("optimizing", 0),
                "pending": counts.get("pending", 0),
                "bytes_total": bytes_total,
                "throughput_per_min": throughput,
                "elapsed_sec": round(time.time() - self.started_at, 1),
            },
            "distribution": [{"tag": t, "value": v} for t, v in sorted(by_tag.items())],
            "paused": self.is_paused,
            "stopped": self.should_stop,
        }
