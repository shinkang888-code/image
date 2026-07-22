"""ComfyUI API-format 워크플로우 빌더 — SDXL-Lightning txt2img / img2img (8GB 튜닝).

정적 JSON 대신 프로그램으로 그래프를 생성해 파라미터(체크포인트/크기/스텝/시드/프롬프트)를
주입한다. 반환 dict 를 그대로 ComfyUI `/prompt` 에 POST 하면 된다.

- build_workflow: txt2img. quality=True 면 ESRGAN 업스케일 노드 추가(GPU 고화질 모드).
- build_img2img_workflow: 참조 이미지 기반 img2img — Lexi Draft 조감도 실사화(로컬 render.ts 대체).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuProfile:
    """8GB GPU + SDXL-Lightning 기본 프로파일."""
    checkpoint: str = "sdxl_lightning_6step.safetensors"
    width: int = 1344      # SDXL 16:9 네이티브 (~1MP, 8GB 안전)
    height: int = 768
    steps: int = 6         # Lightning: 4~8
    cfg: float = 2.0
    sampler: str = "euler"
    scheduler: str = "sgm_uniform"
    upscale_model: str = "4x-UltraSharp.pth"  # quality 모드용 ESRGAN 모델


def _sampler_node(model_ref, pos_ref, neg_ref, latent_ref, seed, profile, denoise=1.0):
    return {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": profile.steps,
            "cfg": profile.cfg,
            "sampler_name": profile.sampler,
            "scheduler": profile.scheduler,
            "denoise": denoise,
            "model": model_ref,
            "positive": pos_ref,
            "negative": neg_ref,
            "latent_image": latent_ref,
        },
    }


def build_workflow(positive: str, negative: str, seed: int, profile: GpuProfile,
                   quality: bool = False) -> dict:
    """txt2img 그래프. quality=True 면 VAEDecode 뒤에 ESRGAN 업스케일을 얹는다."""
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": profile.checkpoint}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": profile.width, "height": profile.height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": _sampler_node(["4", 0], ["6", 0], ["7", 0], ["5", 0], seed, profile),
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    }
    image_ref = ["8", 0]
    if quality:
        # ESRGAN 고화질 업스케일 (GPU). CPU Lanczos 대신 디테일 복원.
        wf["10"] = {"class_type": "UpscaleModelLoader",
                    "inputs": {"model_name": profile.upscale_model}}
        wf["11"] = {"class_type": "ImageUpscaleWithModel",
                    "inputs": {"upscale_model": ["10", 0], "image": ["8", 0]}}
        image_ref = ["11", 0]
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "lip", "images": image_ref}}
    return wf


def build_img2img_workflow(image_name: str, positive: str, negative: str, seed: int,
                           profile: GpuProfile, denoise: float = 0.6,
                           quality: bool = False) -> dict:
    """img2img 그래프 — 업로드된 참조 이미지(조감도 스냅샷)를 실사화.

    denoise 0.4~0.7 권장: 낮을수록 원본 구도 유지, 높을수록 실사 디테일 강화.
    Lexi Draft 3D 캔버스 스냅샷 → 실사 렌더 (클라우드 render.ts 로컬 대체).
    """
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": profile.checkpoint}},
        "12": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "13": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": _sampler_node(["4", 0], ["6", 0], ["7", 0], ["13", 0], seed, profile, denoise),
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    }
    image_ref = ["8", 0]
    if quality:
        wf["10"] = {"class_type": "UpscaleModelLoader",
                    "inputs": {"model_name": profile.upscale_model}}
        wf["11"] = {"class_type": "ImageUpscaleWithModel",
                    "inputs": {"upscale_model": ["10", 0], "image": ["8", 0]}}
        image_ref = ["11", 0]
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "lip_render", "images": image_ref}}
    return wf
