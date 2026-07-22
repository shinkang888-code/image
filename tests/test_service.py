import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from lip.comfy_client import MockComfyClient
from lip.config import Config
from lip.service import GenerationService, request_id, serve_service


def _cfg(tmp: str) -> Config:
    cfg = Config()
    cfg.out_dir = Path(tmp)
    cfg.formats = ("webp", "jpg")
    cfg.output = type(cfg.output)(target=(320, 180))   # 테스트는 작게
    return cfg


class TestGenerationService(unittest.TestCase):
    def test_request_id_is_stable_and_seed_sensitive(self):
        self.assertEqual(request_id("a serum bottle", 7), request_id("a serum bottle", 7))
        self.assertNotEqual(request_id("a serum bottle", 7), request_id("a serum bottle", 8))

    def test_request_id_separates_mock_from_live(self):
        """목업 산출물이 LIVE 캐시 히트로 '실사' 행세를 하면 안 된다."""
        self.assertNotEqual(
            request_id("a serum bottle", 7, mock=True),
            request_id("a serum bottle", 7, mock=False),
        )

    def test_mock_artifact_is_not_served_as_live(self):
        """같은 (프롬프트,시드)라도 모드가 다르면 캐시를 재사용하지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            mock_svc = GenerationService(cfg, mock=True)
            first = mock_svc.generate("a serum bottle", seed=7)

            live_svc = GenerationService(_cfg(tmp), client=MockComfyClient((64, 64)), mock=False)
            second = live_svc.generate("a serum bottle", seed=7)

            self.assertNotEqual(first["id"], second["id"])
            self.assertFalse(second["cached"])   # 목업 폴더를 히트하지 않음
            self.assertTrue(first["mock"])
            self.assertFalse(second["mock"])

    def test_generate_writes_both_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = GenerationService(_cfg(tmp), mock=True)
            r = svc.generate("product photo of a serum bottle", seed=3, tag="product")
            self.assertEqual(r["tag"], "product")
            self.assertTrue(r["mock"])
            self.assertFalse(r["cached"])
            self.assertEqual(r["image_path"], f"/img/{r['id']}/image.webp")
            for f in r["files"]:
                self.assertTrue(Path(f).is_file())
            self.assertTrue((Path(tmp) / r["id"] / "image.webp").is_file())
            self.assertTrue((Path(tmp) / r["id"] / "image.jpg").is_file())

    def test_second_call_hits_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = GenerationService(_cfg(tmp), mock=True)
            first = svc.generate("a knit cardigan", seed=1)
            second = svc.generate("a knit cardigan", seed=1)
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(second["cached"])

    def test_empty_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = GenerationService(_cfg(tmp), mock=True)
            with self.assertRaises(ValueError):
                svc.generate("   ")

    def test_manifest_records_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = GenerationService(_cfg(tmp), mock=True)
            r = svc.generate("a leather bag", seed=5, tag="product")
            lines = (Path(tmp) / "manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(json.loads(lines[-1])["id"], r["id"])


class TestServiceHttp(unittest.TestCase):
    """실제 소켓으로 라운드트립 — 프로바이더가 보게 될 계약 그대로."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = GenerationService(_cfg(self.tmp.name), mock=True)
        self.httpd = serve_service(self.svc, port=0, block=False)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def _post(self, payload: dict):
        req = urllib.request.Request(
            self.base + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_health(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertTrue(data["mock"])

    def test_generate_then_fetch_image(self):
        data = self._post({"prompt": "product photo of a lip tint", "seed": 2})
        with urllib.request.urlopen(self.base + data["image_path"], timeout=10) as r:
            body = r.read()
            self.assertEqual(r.headers["content-type"], "image/webp")
        self.assertTrue(body.startswith(b"RIFF"))     # WebP 매직

    def test_missing_prompt_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post({"seed": 1})
        self.assertEqual(cm.exception.code, 400)

    def test_path_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.base + "/img/../../lip.toml", timeout=10)
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
