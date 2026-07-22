import unittest

from lip.scene import scene_to_prompt
from lip.workflow import GpuProfile, build_img2img_workflow, build_workflow


class TestQualityMode(unittest.TestCase):
    def test_quality_adds_upscale_nodes(self):
        base = build_workflow("p", "n", 1, GpuProfile(), quality=False)
        self.assertNotIn("11", base)
        self.assertEqual(base["9"]["inputs"]["images"], ["8", 0])  # VAEDecode 직결

        q = build_workflow("p", "n", 1, GpuProfile(), quality=True)
        self.assertIn("10", q)  # UpscaleModelLoader
        self.assertEqual(q["10"]["class_type"], "UpscaleModelLoader")
        self.assertEqual(q["11"]["class_type"], "ImageUpscaleWithModel")
        self.assertEqual(q["9"]["inputs"]["images"], ["11", 0])  # 업스케일 경유


class TestImg2Img(unittest.TestCase):
    def test_img2img_graph(self):
        wf = build_img2img_workflow("snap.png", "living room", "blurry", 7,
                                    GpuProfile(), denoise=0.55)
        self.assertEqual(wf["12"]["class_type"], "LoadImage")
        self.assertEqual(wf["12"]["inputs"]["image"], "snap.png")
        self.assertEqual(wf["13"]["class_type"], "VAEEncode")
        self.assertEqual(wf["3"]["inputs"]["denoise"], 0.55)
        self.assertEqual(wf["3"]["inputs"]["latent_image"], ["13", 0])  # 인코딩된 이미지 사용

    def test_img2img_quality(self):
        wf = build_img2img_workflow("s.png", "p", "n", 1, GpuProfile(), quality=True)
        self.assertEqual(wf["9"]["inputs"]["images"], ["11", 0])


class TestSceneToPrompt(unittest.TestCase):
    def test_prompt_from_scene(self):
        scene = {
            "walls": [{}, {}, {}, {}],
            "items": [{"catalogId": "sofa"}, {"catalogId": "coffee_table"}, {"catalogId": "sofa"}],
            "roomMeta": [{"id": "r1"}],
        }
        p = scene_to_prompt(scene, style="scandinavian")
        self.assertIn("scandinavian", p)
        self.assertIn("sofa", p)
        self.assertIn("photorealistic", p)
        # 중복 catalogId 는 한 번만
        self.assertEqual(p.count("a sofa"), 1)

    def test_empty_scene(self):
        p = scene_to_prompt({})
        self.assertIn("interior", p)


if __name__ == "__main__":
    unittest.main()
