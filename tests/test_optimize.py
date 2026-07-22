import io
import unittest

from PIL import Image

from lip.optimize import FHD, OutputSpec, cover_resize, optimize


def _img(w, h, color=(120, 80, 200)):
    return Image.new("RGB", (w, h), color)


class TestOptimize(unittest.TestCase):
    def test_cover_resize_exact_fhd(self):
        for w, h in [(1344, 768), (1000, 1000), (3000, 1000), (800, 1600)]:
            out = cover_resize(_img(w, h))
            self.assertEqual(out.size, FHD, f"{w}x{h}")

    def test_cover_no_distortion_from_square(self):
        # 정사각 입력 → cover-crop 이므로 세로가 잘려 나가야 (왜곡 없이 꽉 채움)
        out = cover_resize(_img(1000, 1000))
        self.assertEqual(out.size, (1920, 1080))

    def test_optimize_emits_webp_and_jpg(self):
        raw = _img(1344, 768)
        encoded = optimize(raw, formats=("webp", "jpg"))
        fmts = {e.fmt for e in encoded}
        self.assertEqual(fmts, {"webp", "jpg"})
        for e in encoded:
            self.assertEqual(e.size, FHD)
            self.assertGreater(e.bytes_len, 0)

    def test_optimize_from_bytes(self):
        buf = io.BytesIO()
        _img(1344, 768).save(buf, format="PNG")
        encoded = optimize(buf.getvalue())
        self.assertEqual(len(encoded), 2)

    def test_webp_smaller_than_jpg_on_photo(self):
        # 그라디언트(사진 유사)에서 WebP 가 JPG 보다 작아야 (요구: 가장 작은 웹포맷)
        img = Image.new("RGB", (1344, 768))
        px = img.load()
        for y in range(768):
            for x in range(0, 1344, 1):
                px[x, y] = ((x + y) % 256, (x * 2) % 256, (y * 3) % 256)
        spec = OutputSpec(webp_quality=80, jpg_quality=82)
        enc = {e.fmt: e.bytes_len for e in optimize(img, spec)}
        self.assertLess(enc["webp"], enc["jpg"])


if __name__ == "__main__":
    unittest.main()
