import tempfile
import unittest
from pathlib import Path

from lip.comfy_client import MockComfyClient
from lip.config import Config
from lip.factory import Factory
from lip.manifest import Manifest
from lip.prompts import load_prompts


class TestFactoryPipeline(unittest.TestCase):
    def test_dry_run_pipeline_produces_files(self):
        prompts = load_prompts(tags=["interior"])[:5]
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(out_dir=Path(d), workers=3)
            mani = Manifest(Path(d) / "manifest.jsonl")
            engine = MockComfyClient((cfg.profile.width, cfg.profile.height))
            f = Factory(cfg, engine, mani, log=lambda *_: None)
            n = f.run(prompts, count=5)
            self.assertEqual(n, 5)
            for p in prompts:
                self.assertTrue((Path(d) / p.id / "image.webp").exists())
                self.assertTrue((Path(d) / p.id / "image.jpg").exists())

    def test_resume_skips_done(self):
        prompts = load_prompts(tags=["interior"])[:4]
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(out_dir=Path(d), workers=2)
            engine = MockComfyClient((cfg.profile.width, cfg.profile.height))
            m1 = Manifest(Path(d) / "manifest.jsonl")
            Factory(cfg, engine, m1, log=lambda *_: None).run(prompts, count=4)
            # 두 번째 실행: 매니페스트 재로드 → 전부 완료라 0장
            m2 = Manifest(Path(d) / "manifest.jsonl")
            self.assertEqual(len(m2), 4)
            n2 = Factory(cfg, engine, m2, log=lambda *_: None).run(prompts, count=4)
            self.assertEqual(n2, 0)


if __name__ == "__main__":
    unittest.main()
