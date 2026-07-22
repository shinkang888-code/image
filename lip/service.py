"""생성 서비스 — 외부 앱이 이미지 1장을 요청하는 HTTP 엔드포인트 (무의존 stdlib).

대시보드(dashboard.py)가 "관제"라면 이쪽은 "주문 창구"다. LEXI Studio 의
ImageProvider(`src/lib/images/providers/lip.ts`)가 여기에 프롬프트를 보내고,
받은 image_url 을 optimizeAndStore 가 내려받아 자기 파이프라인에 태운다.

라우트:
  GET  /api/health      → 엔진·노드 상태 (프로바이더 선택 판단용)
  POST /api/generate    → {prompt, negative?, seed?, tag?} → 이미지 1장 생성
  GET  /img/<id>/<file> → 생성물 (image.webp / image.jpg)

GPU 는 병렬화되지 않으므로 생성 구간은 프로세스 전역 락으로 직렬화한다
(factory.py 의 "GPU 직렬 ∥ CPU 병렬" 원칙과 동일). 인코딩은 요청 스레드에서 수행.
"""
from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .comfy_client import ComfyClient, MockComfyClient
from .config import Config
from .jobs import GenJob, JobStore
from .manifest import Manifest
from .optimize import optimize
from .workflow import build_workflow

# GPU 는 한 번에 하나. 요청이 몰려도 생성은 줄을 선다.
_GPU_LOCK = threading.Lock()

MAX_PROMPT_CHARS = 2000

DEFAULT_NEGATIVE = (
    "lowres, blurry, jpeg artifacts, watermark, text, signature, logo, "
    "brand name, deformed, cartoon, cgi, plastic looking"
)


def request_id(prompt: str, seed: int, mock: bool = False) -> str:
    """프롬프트+시드+엔진출처 기반 안정적 id — 같은 주문은 같은 폴더에 떨어진다.

    mock 을 키에 포함하는 이유: 목업 그라디언트와 실사가 같은 칸을 쓰면,
    나중에 LIVE 로 띄웠을 때 캐시 히트가 목업을 '실사'로 되돌려준다.
    출처가 다르면 산출물도 다른 칸에 둔다.
    """
    provenance = "mock" if mock else "live"
    return hashlib.sha1(f"{prompt}|{seed}|{provenance}".encode("utf-8")).hexdigest()[:12]


class GenerationService:
    """생성 요청 처리기 — 엔진 선택·직렬 생성·인코딩·저장."""

    def __init__(self, cfg: Config, client=None, mock: bool = False,
                 store: JobStore | None = None):
        self.cfg = cfg
        self.out_dir = Path(cfg.out_dir)
        self.store = store or JobStore()
        self.manifest = Manifest(self.out_dir / "manifest.jsonl")
        self.mock = mock
        self.client = client or (
            MockComfyClient((cfg.profile.width, cfg.profile.height)) if mock
            else ComfyClient(host=cfg.comfy_host)
        )

    def health(self) -> dict:
        online = bool(self.mock) or self.client.ping()
        p = self.cfg.profile
        return {
            "ok": online,
            "mock": self.mock,
            "engine": p.engine,
            "model": p.unet if p.engine == "gguf" else p.checkpoint,
            "size": [p.width, p.height],
            "comfy": self.cfg.comfy_host,
        }

    def generate(self, prompt: str, negative: str | None = None,
                 seed: int | None = None, tag: str = "api") -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"prompt too long (>{MAX_PROMPT_CHARS} chars)")
        seed = int(seed if seed is not None else self.cfg.base_seed)
        negative = negative or DEFAULT_NEGATIVE
        rid = request_id(prompt, seed, self.mock)
        dest = self.out_dir / rid

        # 캐시 히트 — 같은 (프롬프트, 시드)는 다시 굽지 않는다.
        cached = self._existing(dest)
        if cached:
            return self._payload(rid, seed, tag, cached, cached_hit=True)

        job = self.store.create(GenJob(id=f"S-{rid}-{seed}", prompt_id=rid, tag=tag,
                                       seed=seed, positive=prompt))
        try:
            wf = build_workflow(prompt, negative, seed, self.cfg.profile,
                                quality=self.cfg.quality)
            self.store.mark(job.id, "generating")
            with _GPU_LOCK:
                raw = self.client.generate(wf)

            self.store.mark(job.id, "optimizing")
            encoded = optimize(raw, self.cfg.output, self.cfg.formats)
            dest.mkdir(parents=True, exist_ok=True)
            files: list[str] = []
            total = 0
            for e in encoded:
                fp = dest / f"image.{e.fmt}"
                fp.write_bytes(e.data)
                files.append(str(fp))
                total += e.bytes_len
            self.manifest.record(rid, seed, tag, files)
            self.store.mark(job.id, "done", files=files, bytes_total=total)
            self.store.event("success", f"API 생성 완료 {rid} ({total // 1024}KB)")
            return self._payload(rid, seed, tag, files)
        except Exception as ex:
            self.store.mark(job.id, "failed", error=str(ex))
            self.store.event("error", f"API 생성 실패 {rid}: {ex}")
            raise

    def _existing(self, dest: Path) -> list[str]:
        if not dest.is_dir():
            return []
        found = [str(dest / f"image.{fmt}") for fmt in self.cfg.formats
                 if (dest / f"image.{fmt}").is_file()]
        return found if len(found) == len(self.cfg.formats) else []

    def _payload(self, rid: str, seed: int, tag: str, files: list[str],
                 cached_hit: bool = False) -> dict:
        p = self.cfg.profile
        return {
            "id": rid,
            "seed": seed,
            "tag": tag,
            "files": files,
            # 상대 경로 — 호출부가 자기 origin 을 붙여 절대 URL 로 만든다.
            "image_path": f"/img/{rid}/image.webp",
            "engine": p.engine,
            "model": p.unet if p.engine == "gguf" else p.checkpoint,
            "mock": self.mock,
            "cached": cached_hit,
        }


class _Handler(BaseHTTPRequestHandler):
    service: GenerationService = None    # 인스턴스 주입 (set on class)

    def log_message(self, *a):           # 조용히
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/api/health"):
            self._json(self.service.health())
        elif p.startswith("/img/"):
            self._serve_image(p[len("/img/"):])
        else:
            self._json({"error": "not found"}, 404)

    def _serve_image(self, rel: str):
        out = self.service.out_dir.resolve()
        target = (self.service.out_dir / rel).resolve()
        # out_dir 밖으로 못 나가게 (경로 탈출 차단)
        if out not in target.parents or not target.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = "image/webp" if target.suffix == ".webp" else "image/jpeg"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/generate":
            self._json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("content-length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid json"}, 400)
            return
        try:
            result = self.service.generate(
                prompt=payload.get("prompt", ""),
                negative=payload.get("negative"),
                seed=payload.get("seed"),
                tag=payload.get("tag", "api"),
            )
        except ValueError as ex:
            self._json({"error": str(ex)}, 400)
            return
        except Exception as ex:
            self._json({"error": f"generation failed: {ex}"}, 502)
            return
        self._json(result)


def serve_service(service: GenerationService, port: int, block: bool = True):
    """생성 서비스 시작. block=False 면 백그라운드 스레드로 실행하고 서버 반환."""
    handler = type("_H", (_Handler,), {"service": service})
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    if block:
        httpd.serve_forever()
        return httpd
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
