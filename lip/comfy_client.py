"""ComfyUI HTTP 클라이언트 — stdlib urllib 만 사용 (무의존, CLAUDE.md 규칙4).

/prompt 로 워크플로우 큐잉 → /history/{id} 폴링 → /view 로 이미지 bytes 회수.
GPU/ComfyUI 없이도 파이프라인을 검증할 수 있도록 MockComfyClient(그라디언트) 제공.
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, host: str = "127.0.0.1:8188", timeout: float = 5.0,
                 base_url: str | None = None):
        # base_url 우선(멀티 노드: ComputeNode.base_url 를 그대로 전달)
        self.base = (base_url or f"http://{host}").rstrip("/")
        self.timeout = timeout

    # --- low level ---
    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get_bytes(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return r.read()

    # --- public ---
    def ping(self) -> bool:
        try:
            self._get_json("/system_stats")
            return True
        except (urllib.error.URLError, OSError, ComfyError):
            return False

    def queue(self, workflow: dict) -> str:
        data = self._post("/prompt", {"prompt": workflow})
        pid = data.get("prompt_id")
        if not pid:
            raise ComfyError(f"no prompt_id in response: {data}")
        return pid

    def wait(self, prompt_id: str, poll: float = 1.0, max_wait: float = 300.0) -> dict:
        """history 에 결과가 나타날 때까지 폴링. 완료된 노드 출력 dict 반환."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            hist = self._get_json(f"/history/{prompt_id}")
            if prompt_id in hist:
                return hist[prompt_id].get("outputs", {})
            time.sleep(poll)
        raise ComfyError(f"timeout waiting for {prompt_id}")

    def fetch_image(self, outputs: dict) -> bytes:
        """SaveImage 노드 출력에서 첫 이미지 bytes 를 /view 로 가져온다."""
        for node in outputs.values():
            for img in node.get("images", []):
                q = urllib.parse.urlencode(
                    {"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}
                )
                return self._get_bytes(f"/view?{q}")
        raise ComfyError("no image in outputs")

    def upload_image(self, path: str) -> str:
        """이미지를 ComfyUI 에 업로드(/upload/image) 후 LoadImage 용 파일명 반환."""
        with open(path, "rb") as f:
            content = f.read()
        boundary = uuid.uuid4().hex
        name = os.path.basename(path)
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content, b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            self.base + "/upload/image", data=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("name", name)

    def generate(self, workflow: dict) -> bytes:
        pid = self.queue(workflow)
        outputs = self.wait(pid)
        return self.fetch_image(outputs)


class MockComfyClient:
    """GPU/ComfyUI 없이 파이프라인을 검증하는 dry-run 엔진.

    프롬프트 시드에 따라 결정적 그라디언트 PNG 를 생성한다 (SDXL 네이티브 크기).
    """
    def __init__(self, size: tuple[int, int] = (1344, 768)):
        self.size = size

    def ping(self) -> bool:
        return True

    def upload_image(self, path: str) -> str:
        return os.path.basename(path)

    def generate(self, workflow: dict) -> bytes:
        from PIL import Image

        seed = 0
        for node in workflow.values():
            if node.get("class_type") == "KSampler":
                seed = int(node["inputs"].get("seed", 0))
        w, h = self.size
        r = (seed * 37) % 256
        g = (seed * 91) % 256
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):
            b = int(255 * y / h)
            for x in range(w):
                rr = int(r * (1 - x / w) + g * (x / w))
                px[x, y] = (rr, (g + y) % 256, b)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
