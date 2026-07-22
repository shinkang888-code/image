"""오케스트레이터 — GPU 직렬 생성 ∥ CPU 워커풀 후처리, + 작업제어·멀티노드·재시도·takes.

'천재병렬작업': 단일 GPU 는 diffusion 을 병렬화 못 하므로 GPU 는 생성만 직렬로,
FHD 업스케일 + WebP/JPG 인코딩은 CPU 워커 N개가 동시에.

이식 통합:
- LinkNode  : JobStore 로 작업 상태·이벤트·제어(pause/stop/cancel)
- lasset    : 여러 Compute Node 에 라운드로빈 분산 생성
- voicebox  : 실패 재시도, takes(시드 변주), 재개(manifest)
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .jobs import GenJob, JobStore
from .manifest import Manifest
from .optimize import optimize
from .prompts import Prompt
from .workflow import build_workflow


@dataclass
class _Task:
    job: GenJob
    raw: bytes
    dest: Path


class Factory:
    def __init__(self, cfg: Config, engine, manifest: Manifest,
                 store: JobStore | None = None,
                 engines: list[tuple[str, object]] | None = None,
                 log: Callable[[str], None] = print):
        self.cfg = cfg
        self.engine = engine                     # 단일 클라이언트 (dry-run/기본)
        self.engines = engines                   # [(node_name, client)] 멀티노드 (있으면 라운드로빈)
        self.manifest = manifest
        self.store = store or JobStore()
        self.log = log
        self.out_dir = Path(cfg.out_dir)
        self._q: "queue.Queue[_Task | None]" = queue.Queue(maxsize=cfg.workers * 2)
        self._lock = threading.Lock()
        self.done = 0
        self._rr = 0                             # 라운드로빈 커서

    def _pick_engine(self) -> tuple[str, object]:
        if self.engines:
            name, client = self.engines[self._rr % len(self.engines)]
            self._rr += 1
            return name, client
        return "", self.engine

    def _worker(self) -> None:
        while True:
            task = self._q.get()
            try:
                if task is None:
                    return
                job = task.job
                self.store.mark(job.id, "optimizing")
                encoded = optimize(task.raw, self.cfg.output, self.cfg.formats)
                task.dest.mkdir(parents=True, exist_ok=True)
                files: list[str] = []
                total = 0
                for e in encoded:
                    fp = task.dest / f"image.{e.fmt}"
                    fp.write_bytes(e.data)
                    files.append(str(fp))
                    total += e.bytes_len
                self.manifest.record(job.prompt_id, job.seed, job.tag, files)
                self.store.mark(job.id, "done", files=files, bytes_total=total)
                with self._lock:
                    self.done += 1
                    sizes = ", ".join(f"{e.fmt} {e.bytes_len // 1024}KB" for e in encoded)
                    self.log(f"  [{self.done}] {job.tag}/{job.prompt_id}"
                             f"{('@' + job.node) if job.node else ''}  ({sizes})")
            except Exception as ex:
                self.store.mark(task.job.id, "failed", error=str(ex))
                self.store.event("error", f"인코딩 실패 {task.job.prompt_id}: {ex}")
                self.log(f"  ! encode failed {task.job.prompt_id}: {ex}")
            finally:
                self._q.task_done()

    def _generate_with_retry(self, job: GenJob, wf: dict, client) -> bytes | None:
        for attempt in range(1, self.cfg.retries + 2):
            try:
                return client.generate(wf)
            except Exception as ex:
                self.store.event("warning", f"생성 실패(시도 {attempt}) {job.prompt_id}: {ex}")
                if attempt >= self.cfg.retries + 1:
                    self.store.mark(job.id, "failed", error=str(ex), attempt=attempt)
                    return None
        return None

    def run(self, prompts: list[Prompt], count: int | None = None) -> int:
        workers = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self.cfg.workers)]
        for w in workers:
            w.start()
        self.store.event("info", f"공장 시작 — 목표 {count or '전체'}장, 워커 {self.cfg.workers}")

        produced = 0
        try:
            for i, p in enumerate(prompts):
                if count is not None and produced >= count:
                    break
                if self.store.should_stop:
                    self.store.event("warning", "중지 요청으로 종료")
                    break
                # 일시정지 대기
                while self.store.is_paused and not self.store.should_stop:
                    threading.Event().wait(0.2)
                if self.store.is_cancelled(p.id):
                    continue
                for take in range(self.cfg.takes):
                    if count is not None and produced >= count:
                        break
                    seed = self.cfg.base_seed + i + take * 100003
                    if self.manifest.has(p.id, seed):
                        continue
                    node_name, client = self._pick_engine()
                    dest = self.out_dir / p.id if take == 0 else self.out_dir / p.id / f"take{take}"
                    job = self.store.create(GenJob(
                        id=f"J-{p.id}-{seed}", prompt_id=p.id, tag=p.tag, seed=seed,
                        positive=p.positive, node=node_name, take=take))
                    self.store.mark(job.id, "generating")
                    wf = build_workflow(p.positive, p.negative, seed, self.cfg.profile,
                                        quality=self.cfg.quality)
                    raw = self._generate_with_retry(job, wf, client)
                    if raw is None:
                        continue
                    self._q.put(_Task(job=job, raw=raw, dest=dest))
                    produced += 1
                    if count is not None and produced >= count:
                        break
        finally:
            for _ in workers:
                self._q.put(None)
            for w in workers:
                w.join()
        self.store.event("success", f"공장 완료 — {self.done}장 생성")
        return self.done
