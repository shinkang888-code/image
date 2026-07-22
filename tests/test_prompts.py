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
        self.assertEqual(both, {"interior", "web"})
        only = {p.tag for p in load_prompts(tags=["web"])}
        self.assertEqual(only, {"web"})


if __name__ == "__main__":
    unittest.main()
