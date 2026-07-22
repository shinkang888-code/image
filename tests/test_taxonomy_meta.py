import unittest

from lip.meta import build_meta, iplant_line
from lip.taxonomy import DEFAULT_WEIGHTS, alloc, ai_recommend_weights


class TestTaxonomy(unittest.TestCase):
    def test_alloc_sums_to_total(self):
        qs = alloc(1000, DEFAULT_WEIGHTS)
        self.assertEqual(sum(q.count for q in qs), 1000)
        cats = {q.category for q in qs}
        self.assertEqual(cats, {"websource", "commerce", "aimodel"})

    def test_alloc_small(self):
        qs = alloc(10)
        self.assertEqual(sum(q.count for q in qs), 10)

    def test_recommend(self):
        w = ai_recommend_weights("aimodel")
        self.assertGreater(w["aimodel"], w["websource"])


class TestMeta(unittest.TestCase):
    def test_line_tokens(self):
        line = iplant_line(category="commerce", subcategory="pdp",
                           prompt_id="abc", seed=1, use="pdp")
        self.assertIn("IPLANT;v1", line)
        self.assertIn("cat=commerce.pdp", line)
        self.assertIn("by=lexi_ai/ipplant", line)
        self.assertIn("c=steven8kay", line)

    def test_schema(self):
        m = build_meta(
            category="websource", subcategory="hero", prompt_id="x",
            positive="a banner", negative="blur", seed=2, local_path="C:/x",
        )
        self.assertEqual(m["@type"], "ImageObject")
        self.assertEqual(m["copyrightHolder"]["name"], "steven8kay")
        self.assertIn("lexi_ai", m["creditText"])


if __name__ == "__main__":
    unittest.main()
