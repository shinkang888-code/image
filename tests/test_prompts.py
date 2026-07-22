import unittest

from lip.prompts import expand, load_catalog, load_prompts


class TestPrompts(unittest.TestCase):
    def test_catalog_loads(self):
        cat = load_catalog()
        self.assertIn("sets", cat)
        self.assertIn("interior", cat["sets"])

    def test_interior_combination_count(self):
        cat = load_catalog()
        ax = cat["sets"]["interior"]["axes"]
        expected = 1
        for v in ax.values():
            expected *= len(v)
        prompts = expand(cat, tags=["interior"])
        self.assertEqual(len(prompts), expected)

    def test_ids_are_stable_and_unique(self):
        a = load_prompts(tags=["interior"])
        b = load_prompts(tags=["interior"])
        self.assertEqual([p.id for p in a], [p.id for p in b])   # 안정적
        self.assertEqual(len({p.id for p in a}), len(a))          # 고유

    def test_quality_and_negative_applied(self):
        p = load_prompts(tags=["interior"])[0]
        self.assertIn("photorealistic", p.positive)
        self.assertTrue(p.negative)

    def test_tag_filter(self):
        both = {p.tag for p in load_prompts()}
        self.assertEqual(both, {"interior", "web", "product", "detail", "lifestyle", "model"})
        only = {p.tag for p in load_prompts(tags=["web"])}
        self.assertEqual(only, {"web"})

    def test_commerce_sets_present(self):
        """LEXI 커머스 공급용 세트 — PDP 히어로/디테일/연출/착용."""
        cat = load_catalog()
        for name in ("product", "detail", "lifestyle", "model"):
            self.assertIn(name, cat["sets"])

    def test_set_level_quality_and_negative_override(self):
        """set 이 자기 화질어·네거티브를 가지면 전역값 대신 그것을 쓴다."""
        p = load_prompts(tags=["product"])[0]
        self.assertIn("commercial e-commerce quality", p.positive)
        self.assertNotIn("natural materials", p.positive)   # interior 전역값이 새지 않음
        self.assertIn("logo", p.negative)                   # 상품컷 전용 네거티브

    def test_global_quality_still_applies_without_override(self):
        p = load_prompts(tags=["interior"])[0]
        self.assertIn("natural materials", p.positive)


if __name__ == "__main__":
    unittest.main()
