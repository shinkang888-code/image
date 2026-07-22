"""Lexi IPlant local agent — poll Neon jobs, run weighted factory, write ipplant + meta + API upsert."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .comfy_client import ComfyClient, MockComfyClient
from .config import load_config
from .factory import Factory
from .jobs import GenJob, JobStore
from .manifest import Manifest
from .meta import build_meta, write_sidecar
from .nodes import NodeRegistry, ensure_default_node
from .optimize import optimize
from .prompts import Prompt, load_prompts
from .taxonomy import Quota, alloc, catalog_tag_for
from .workflow import build_workflow


DEFAULT_IPLANT = Path(os.environ.get("IPLANT_ROOT", r"C:\cursor\ipplant"))


def _api_base() -> str:
    return os.environ.get("IPLANT_API", "http://127.0.0.1:3000").rstrip("/")


def _headers() -> dict:
    h = {"content-type": "application/json"}
    tok = os.environ.get("IPLANT_AGENT_TOKEN", "")
    if tok:
        h["authorization"] = f"Bearer {tok}"
    return h


def _http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _api_base() + path, data=data, headers=_headers(), method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"error": raw, "status": e.code}
    except Exception as ex:
        return {"error": str(ex)}


def heartbeat(comfy_ok: bool, root: Path) -> None:
    _http_json("POST", "/api/agents", {
        "id": os.environ.get("IPLANT_AGENT_ID", "local-8gb"),
        "name": "local-8gb",
        "comfy_ok": comfy_ok,
        "ipplant_path": str(root),
    })


def upsert_asset(payload: dict) -> None:
    _http_json("POST", "/api/assets", payload)


def write_inventory(root: Path) -> dict:
    lib = root / "library"
    stats: dict[str, dict[str, int]] = {}
    if lib.exists():
        for cat_dir in sorted(lib.glob("*")):
            if not cat_dir.is_dir():
                continue
            for sub in sorted(cat_dir.glob("*")):
                if not sub.is_dir():
                    continue
                n = sum(1 for _ in sub.rglob("image.webp"))
                stats.setdefault(cat_dir.name, {})[sub.name] = n
    report = {"updated_at": time.time(), "stats": stats, "root": str(root)}
    out = root / "reports" / "inventory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _pick_prompts_for_quota(quota: Quota, all_by_tag: dict[str, list[Prompt]],
                            used: set[str]) -> list[tuple[Quota, Prompt]]:
    tag = catalog_tag_for(quota.subcategory)
    pool = list(all_by_tag.get(tag) or all_by_tag.get("web") or [])
    if not pool:
        pool = [p for ps in all_by_tag.values() for p in ps]
    chosen: list[tuple[Quota, Prompt]] = []
    i = 0
    guard = max(quota.count * max(len(pool), 1) * 2, quota.count + 10)
    while len(chosen) < quota.count and pool and i < guard:
        p = pool[i % len(pool)]
        i += 1
        key = f"{quota.key}:{p.id}:{len(chosen)}"
        if key in used:
            continue
        used.add(key)
        tagged = Prompt(
            id=p.id,
            tag=f"{quota.category}.{quota.subcategory}",
            positive=p.positive,
            negative=p.negative,
        )
        chosen.append((quota, tagged))
    return chosen


@dataclass
class _CatTask:
    job: GenJob
    raw: bytes
    dest: Path
    quota: Quota
    positive: str
    negative: str
    engine: str


class CategoryFactory(Factory):
    """Writes into ipplant/library/<cat>/<sub>/<id>/ + IPLANT sidecar + Neon upsert."""

    def __init__(self, *args, ipplant_root: Path, engine_name: str = "gguf", **kwargs):
        super().__init__(*args, **kwargs)
        self.ipplant_root = ipplant_root
        self.engine_name = engine_name
        self._q = queue.Queue(maxsize=self.cfg.workers * 2)

    def _cat_worker(self) -> None:
        while True:
            task = self._q.get()
            try:
                if task is None:
                    return
                assert isinstance(task, _CatTask)
                job = task.job
                self.store.mark(job.id, "optimizing")
                encoded = optimize(task.raw, self.cfg.output, self.cfg.formats)
                task.dest.mkdir(parents=True, exist_ok=True)
                files: list[str] = []
                webp_bytes = 0
                for e in encoded:
                    fp = task.dest / f"image.{e.fmt}"
                    fp.write_bytes(e.data)
                    files.append(str(fp))
                    if e.fmt == "webp":
                        webp_bytes = e.bytes_len
                meta = build_meta(
                    category=task.quota.category,
                    subcategory=task.quota.subcategory,
                    prompt_id=job.prompt_id,
                    positive=task.positive,
                    negative=task.negative,
                    seed=job.seed,
                    local_path=str(task.dest),
                    engine=task.engine,
                    width=int(self.cfg.output.target[0]),
                    height=int(self.cfg.output.target[1]),
                )
                write_sidecar(task.dest, meta)
                self.manifest.record(job.prompt_id, job.seed, job.tag, files)
                total = sum(Path(f).stat().st_size for f in files if Path(f).exists())
                self.store.mark(job.id, "done", files=files, bytes_total=total)
                sha = None
                webp = task.dest / "image.webp"
                if webp.exists():
                    sha = hashlib.sha256(webp.read_bytes()).hexdigest()
                upsert_asset({
                    "id": f"{job.prompt_id}-{job.seed}",
                    "prompt_id": job.prompt_id,
                    "category": task.quota.category,
                    "subcategory": task.quota.subcategory,
                    "tag": job.tag,
                    "seed": job.seed,
                    "width": int(self.cfg.output.target[0]),
                    "height": int(self.cfg.output.target[1]),
                    "bytes_webp": webp_bytes,
                    "local_path": str(task.dest),
                    "sha256": sha,
                    "prompt_full": task.positive,
                    "negative": task.negative,
                    "iplant_line": meta["identifier"],
                    "copyright_holder": "steven8kay",
                    "schema_json": meta,
                })
                with self._lock:
                    self.done += 1
                    self.log(f"  [{self.done}] {task.quota.key}/{job.prompt_id}")
            except Exception as ex:
                if task is not None and isinstance(task, _CatTask):
                    self.store.mark(task.job.id, "failed", error=str(ex))
                self.log(f"  ! worker failed: {ex}")
            finally:
                self._q.task_done()

    def run_pairs(self, pairs: list[tuple[Quota, Prompt]], count: int | None = None) -> int:
        workers = [threading.Thread(target=self._cat_worker, daemon=True)
                   for _ in range(self.cfg.workers)]
        for w in workers:
            w.start()
        produced = 0
        try:
            for i, (quota, p) in enumerate(pairs):
                if count is not None and produced >= count:
                    break
                if self.store.should_stop:
                    break
                while self.store.is_paused and not self.store.should_stop:
                    threading.Event().wait(0.2)
                seed = self.cfg.base_seed + i
                dest = (self.ipplant_root / "library" / quota.category /
                        quota.subcategory / p.id)
                if self.manifest.has(p.id, seed):
                    continue
                node_name, client = self._pick_engine()
                job = self.store.create(GenJob(
                    id=f"J-{p.id}-{seed}", prompt_id=p.id, tag=p.tag, seed=seed,
                    positive=p.positive, node=node_name, take=0))
                self.store.mark(job.id, "generating")
                wf = build_workflow(p.positive, p.negative, seed, self.cfg.profile,
                                    quality=self.cfg.quality)
                raw = self._generate_with_retry(job, wf, client)
                if raw is None:
                    continue
                self._q.put(_CatTask(
                    job=job, raw=raw, dest=dest, quota=quota,
                    positive=p.positive, negative=p.negative, engine=self.engine_name,
                ))
                produced += 1
        finally:
            for _ in workers:
                self._q.put(None)
            for w in workers:
                w.join()
        return self.done


def run_generate_job(payload: dict, dry_run: bool = False) -> int:
    cfg = load_config()
    root = Path(payload.get("out_root") or DEFAULT_IPLANT)
    root.mkdir(parents=True, exist_ok=True)
    total = int(payload.get("total") or 10)
    weights = payload.get("weights")
    quotas = alloc(total, weights)

    tags = {catalog_tag_for(q.subcategory) for q in quotas} | {
        "web", "product", "model", "detail", "lifestyle",
    }
    by_tag: dict[str, list[Prompt]] = {t: load_prompts(cfg.catalog, [t]) for t in tags}
    used: set[str] = set()
    bags = {q.key: _pick_prompts_for_quota(q, by_tag, used) for q in quotas}
    keys = list(bags.keys())
    idx = {k: 0 for k in keys}
    pairs: list[tuple[Quota, Prompt]] = []
    while len(pairs) < total:
        progressed = False
        for k in keys:
            bag = bags[k]
            i = idx[k]
            if i < len(bag):
                pairs.append(bag[i])
                idx[k] = i + 1
                progressed = True
                if len(pairs) >= total:
                    break
        if not progressed:
            break

    reg = NodeRegistry(cfg.nodes_file)
    ensure_default_node(reg, cfg.comfy_host)
    store = JobStore()
    if dry_run:
        engines = [("mock", MockComfyClient((cfg.profile.width, cfg.profile.height)))]
    else:
        engines = []
        for n in reg.active_nodes():
            c = ComfyClient(base_url=n.base_url)
            if c.ping():
                engines.append((n.name, c))
        if not engines:
            print("no online Comfy — falling back to dry-run mock")
            engines = [("mock", MockComfyClient((cfg.profile.width, cfg.profile.height)))]
            dry_run = True

    heartbeat(comfy_ok=not dry_run, root=root)
    manifest = Manifest(root / "manifest.jsonl")
    fac = CategoryFactory(
        cfg, engine=engines[0][1], manifest=manifest, store=store, engines=engines,
        ipplant_root=root, engine_name=cfg.profile.engine,
    )
    n = fac.run_pairs(pairs, count=total)
    write_inventory(root)
    return n


def agent_loop(poll_sec: float = 5.0, dry_run: bool = False) -> None:
    print(f"iplant agent → {_api_base()} root={DEFAULT_IPLANT}")
    while True:
        heartbeat(comfy_ok=True, root=DEFAULT_IPLANT)
        data = _http_json("POST", "/api/jobs", {
            "action": "claim",
            "agent_id": os.environ.get("IPLANT_AGENT_ID", "local-8gb"),
        })
        job = data.get("job")
        if not job:
            time.sleep(poll_sec)
            continue
        jid = job["id"]
        payload = job.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        print(f"claimed {jid} type={job.get('type')}")
        try:
            if job.get("type") == "generate":
                n = run_generate_job(payload, dry_run=dry_run)
                _http_json("POST", "/api/jobs", {
                    "action": "finish", "id": jid, "status": "done",
                })
                print(f"done {jid} produced={n}")
            else:
                _http_json("POST", "/api/jobs", {
                    "action": "finish", "id": jid, "status": "done",
                })
        except Exception as ex:
            _http_json("POST", "/api/jobs", {
                "action": "finish", "id": jid, "status": "failed", "error": str(ex),
            })
            print(f"failed {jid}: {ex}")
        write_inventory(DEFAULT_IPLANT)
