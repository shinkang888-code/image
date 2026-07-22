"""산출물 라벨링 — naming / seo / watermark / library / sample."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lip import library, naming, sample, seo, watermark
from lip.prompts import load_catalog


class TestNaming(unittest.TestCase):
    def test_slug_word_boundary(self):
        s = naming.slugify("brick facade specialty coffee shop golden hour photography")
        self.assertTrue(s.startswith("brick-facade"))
        # 단어 중간 절단이면 facade → fac 로 끝남. 완전 단어면 facade.
        self.assertTrue(s.split("-")[1] == "facade")
        self.assertLessEqual(len(s), naming.MAX_SLUG)

    def test_filename(self):
        self.assertEqual(
            naming.filename("cafe-storefront", "web", "webp", index=1),
            "lex_cafe-storefront-01-web.webp",
        )


class TestSeo(unittest.TestCase):
    def test_packet_under_cap(self):
        m = seo.ImageMeta(
            category="websource", subcategory="storefront",
            prompt="specialty coffee shop brick facade golden hour street view",
            recipe="r1", engine="krea2t-q3km", seed=7,
            caption="Visit our store", license_url="https://lexi.ai/license",
        )
        pkt = seo.build_xmp(m)
        self.assertLessEqual(len(pkt), seo.MAX_PACKET_BYTES)
        self.assertIn(b"lexi:x=", pkt)
        self.assertIn(b"trainedAlgorithmicMedia", pkt)
        self.assertIn(b"steven8kay", pkt)

    def test_roundtrip_compact(self):
        m = seo.ImageMeta(
            category="websource", subcategory="interior",
            prompt="modern bakery counter soft daylight",
            recipe="r1", engine="krea2t-q3km", seed=3,
        )
        pkt = seo.build_xmp(m)
        line = seo.read_compact(pkt)
        self.assertIsNotNone(line)
        self.assertIn("websource/interior", line)
        self.assertIn("krea2t-q3km", line)


class TestWatermark(unittest.TestCase):
    def test_apply_preserves_size(self):
        img = Image.new("RGB", (640, 360), (220, 210, 200))
        out = watermark.apply(img)
        self.assertEqual(out.size, img.size)
        # 우하단 영역이 원본과 달라야 한다 (마크가 찍힘)
        corner = out.crop((560, 320, 640, 360))
        self.assertNotEqual(
            list(corner.getdata())[:16],
            [(220, 210, 200)] * 16,
        )


class TestLibrary(unittest.TestCase):
    def test_save_asset_writes_labeled_files(self):
        img = Image.new("RGB", (800, 450), (160, 120, 80))
        with tempfile.TemporaryDirectory() as tmp:
            rec = library.save_asset(
                img, root=tmp, category="websource", subcategory="storefront",
                prompt="specialty coffee shop brick facade", negative="text",
                prompt_id="t1", seed=1, engine="mock", index=1,
            )
            self.assertIn("avif", rec.files)
            self.assertIn("webp", rec.files)
            for p in rec.files.values():
                path = Path(p)
                self.assertTrue(path.exists())
                self.assertTrue(path.name.startswith("lex_"))
                data = path.read_bytes()
                self.assertIsNotNone(seo.read_compact(data))
            library.append_manifest(tmp, rec)
            report = library.report(tmp)
            self.assertEqual(report["websource"]["storefront"], 1)


class TestSample(unittest.TestCase):
    def test_plan_sums(self):
        cat = load_catalog(sample.CATALOG)
        quotas = sample.plan(100, cat)
        self.assertEqual(sum(quotas.values()), 100)
        self.assertGreater(quotas.get("storefront", 0), 0)

    def test_pick_prompts(self):
        cat = load_catalog(sample.CATALOG)
        ps = sample.pick_prompts(cat, "storefront", 5)
        self.assertEqual(len(ps), 5)
        self.assertTrue(all(p.tag == "storefront" for p in ps))


if __name__ == "__main__":
    unittest.main()
