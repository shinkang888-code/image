import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from lip.dashboard import serve_dashboard
from lip.jobs import GenJob, JobStore
from lip.nodes import NodeRegistry


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.read()


def _post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.status, json.loads(r.read())


class TestDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        cls.store = JobStore()
        j = cls.store.create(GenJob(id="J-1", prompt_id="abc", tag="interior", seed=0,
                                    positive="a room"))
        cls.store.mark(j.id, "done", bytes_total=2048)
        cls.reg = NodeRegistry(out / "nodes.json")
        cls.reg.upsert("local", "http://127.0.0.1:8188")
        # 실제 webp 파일 하나 배치 (썸네일 라우트 검증)
        (out / "abc").mkdir()
        from PIL import Image
        import io
        buf = io.BytesIO(); Image.new("RGB", (16, 9)).save(buf, "WEBP")
        (out / "abc" / "image.webp").write_bytes(buf.getvalue())
        cls.httpd = serve_dashboard(cls.store, cls.reg, out, port=8899, block=False)
        cls.base = "http://127.0.0.1:8899"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def test_index_html(self):
        code, body = _get(self.base + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"LIP", body)

    def test_summary(self):
        code, body = _get(self.base + "/api/summary")
        data = json.loads(body)
        self.assertEqual(data["totals"]["done"], 1)

    def test_jobs_and_nodes(self):
        _, jb = _get(self.base + "/api/jobs")
        self.assertEqual(json.loads(jb)[0]["prompt_id"], "abc")
        _, nb = _get(self.base + "/api/nodes")
        self.assertEqual(json.loads(nb)[0]["name"], "local")

    def test_image_route(self):
        code, body = _get(self.base + "/img/abc/image.webp")
        self.assertEqual(code, 200)
        self.assertTrue(body[:4] == b"RIFF")  # webp 컨테이너

    def test_control_pause_resume(self):
        _, r = _post(self.base + "/api/control", {"action": "pause"})
        self.assertTrue(r["ok"])
        self.assertTrue(self.store.is_paused)
        _post(self.base + "/api/control", {"action": "resume"})
        self.assertFalse(self.store.is_paused)


if __name__ == "__main__":
    unittest.main()
