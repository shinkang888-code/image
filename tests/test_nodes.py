import tempfile
import unittest
from pathlib import Path

from lip.nodes import NodeRegistry, ensure_default_node


class TestNodeRegistry(unittest.TestCase):
    def test_upsert_and_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nodes.json"
            reg = NodeRegistry(path)
            n = reg.upsert("local", "http://127.0.0.1:8188/")
            self.assertEqual(n.base_url, "http://127.0.0.1:8188")  # 슬래시 정규화
            self.assertTrue(n.active)  # 첫 노드는 active
            # 재로드 시 유지
            reg2 = NodeRegistry(path)
            self.assertEqual(len(reg2.list()), 1)

    def test_multi_node_active(self):
        with tempfile.TemporaryDirectory() as d:
            reg = NodeRegistry(Path(d) / "nodes.json")
            a = reg.upsert("a", "http://a:8188")
            reg.upsert("b", "http://b:8188", active=True)
            self.assertGreaterEqual(len(reg.active_nodes()), 1)
            reg.set_active(a.id, False)
            self.assertTrue(all(n.id != a.id for n in reg.active_nodes()))

    def test_update_status_and_remove(self):
        with tempfile.TemporaryDirectory() as d:
            reg = NodeRegistry(Path(d) / "nodes.json")
            n = reg.upsert("x", "http://x:8188")
            reg.update_status(n.id, "online", "ok")
            self.assertEqual(reg.list()[0].status, "online")
            self.assertIsNotNone(reg.list()[0].last_seen_at)
            self.assertTrue(reg.remove(n.id))
            self.assertEqual(reg.list(), [])

    def test_ensure_default(self):
        with tempfile.TemporaryDirectory() as d:
            reg = NodeRegistry(Path(d) / "nodes.json")
            ensure_default_node(reg, "127.0.0.1:8188")
            self.assertEqual(len(reg.list()), 1)
            ensure_default_node(reg, "127.0.0.1:8188")  # 재호출해도 1개
            self.assertEqual(len(reg.list()), 1)


if __name__ == "__main__":
    unittest.main()
