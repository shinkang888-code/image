import unittest

from lip.workflow import GpuProfile, build_workflow


class TestWorkflow(unittest.TestCase):
    def test_graph_shape(self):
        wf = build_workflow("a room", "blurry", 42, GpuProfile())
        # 모든 노드가 class_type + inputs 를 가진다 (ComfyUI API-format)
        for node in wf.values():
            self.assertIn("class_type", node)
            self.assertIn("inputs", node)

    def test_params_injected(self):
        prof = GpuProfile(width=1344, height=768, steps=6, cfg=2.0)
        wf = build_workflow("pos text", "neg text", 123, prof)
        self.assertEqual(wf["3"]["inputs"]["seed"], 123)
        self.assertEqual(wf["3"]["inputs"]["steps"], 6)
        self.assertEqual(wf["5"]["inputs"]["width"], 1344)
        self.assertEqual(wf["6"]["inputs"]["text"], "pos text")
        self.assertEqual(wf["7"]["inputs"]["text"], "neg text")

    def test_wiring(self):
        wf = build_workflow("p", "n", 1, GpuProfile())
        # KSampler latent 는 EmptyLatentImage(5) 를 참조
        self.assertEqual(wf["3"]["inputs"]["latent_image"], ["5", 0])
        # SaveImage 는 VAEDecode(8) 를 참조
        self.assertEqual(wf["9"]["inputs"]["images"], ["8", 0])


if __name__ == "__main__":
    unittest.main()
