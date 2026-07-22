import unittest

from lip.workflow import GpuProfile, build_workflow, build_workflow_gguf, gguf_profile


class TestWorkflow(unittest.TestCase):
    def test_graph_shape(self):
        wf = build_workflow("a room", "blurry", 42, GpuProfile())
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
        self.assertEqual(wf["3"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(wf["9"]["inputs"]["images"], ["8", 0])

    def test_gguf_graph(self):
        prof = gguf_profile()
        wf = build_workflow_gguf("artist portrait", "ignored", 99, prof)
        self.assertEqual(wf["1"]["class_type"], "UnetLoaderGGUF")
        self.assertEqual(wf["1"]["inputs"]["unet_name"], "krea2_turbo-Q3_K_M.gguf")
        self.assertEqual(wf["2"]["inputs"]["type"], "krea2")
        self.assertEqual(wf["4"]["inputs"]["text"], "artist portrait")
        self.assertEqual(wf["5"]["class_type"], "ConditioningZeroOut")
        self.assertEqual(wf["7"]["inputs"]["seed"], 99)
        self.assertEqual(wf["7"]["inputs"]["steps"], 8)
        self.assertEqual(wf["7"]["inputs"]["sampler_name"], "er_sde")
        self.assertEqual(wf["6"]["inputs"]["width"], 1216)
        # dispatch via build_workflow
        wf2 = build_workflow("p", "n", 1, prof)
        self.assertEqual(wf2["1"]["class_type"], "UnetLoaderGGUF")


if __name__ == "__main__":
    unittest.main()
