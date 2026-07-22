"""ComfyUI API-format 워크플로우 빌더.

- sdxl: CheckpointLoaderSimple + SDXL-Lightning (공식 4/8step)
- gguf: UnetLoaderGGUF + CLIP(krea2) + VAE — sonsu/linkr 작가 파이프라인과 동일
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuProfile:
    """로컬 8GB GPU 프로파일. engine=sdxl|gguf."""
    engine: str = "sdxl"
    # SDXL
    checkpoint: str = "sdxl_lightning_4step.safetensors"
    # GGUF / Krea (D:\\ComfyUI_windows_portable 기본 설치본)
    unet: str = "krea2_turbo-Q3_K_M.gguf"
    clip: str = "qwen3vl_4b_fp8_scaled.safetensors"
    clip_type: str = "krea2"
    vae: str = "qwen_image_vae.safetensors"
    width: int = 1344
    height: int = 768
    steps: int = 6
    cfg: float = 2.0
    sampler: str = "euler"
    scheduler: str = "sgm_uniform"
    upscale_model: str = "4x-UltraSharp.pth"


def gguf_profile(**overrides) -> GpuProfile:
    """sonsu/linkr 전시·작가 배치와 맞춘 Krea GGUF 기본값."""
    base = dict(
        engine="gguf",
        width=1216,
        height=832,
        steps=8,
        cfg=1.0,
        sampler="er_sde",
        scheduler="simple",
    )
    base.update(overrides)
    return GpuProfile(**base)


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


def _attach_quality(wf: dict, decode_ref: list, profile: GpuProfile) -> list:
    wf["10"] = {"class_type": "UpscaleModelLoader",
                "inputs": {"model_name": profile.upscale_model}}
    wf["11"] = {"class_type": "ImageUpscaleWithModel",
                "inputs": {"upscale_model": ["10", 0], "image": decode_ref}}
    return ["11", 0]


def build_workflow_sdxl(positive: str, negative: str, seed: int, profile: GpuProfile,
                        quality: bool = False) -> dict:
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
        image_ref = _attach_quality(wf, ["8", 0], profile)
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "lip", "images": image_ref}}
    return wf


def build_workflow_gguf(positive: str, negative: str, seed: int, profile: GpuProfile,
                        quality: bool = False) -> dict:
    """Krea-2-Turbo GGUF txt2img — linkr/sonsu 작가 배치와 동일 그래프.

    negative 는 ConditioningZeroOut 으로 비움(Krea 권장). negative 인자는 호환용으로 무시.
    """
    _ = negative
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": profile.unet}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": profile.clip, "type": profile.clip_type}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": profile.vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyLatentImage",
              "inputs": {"width": profile.width, "height": profile.height, "batch_size": 1}},
        "7": _sampler_node(["1", 0], ["4", 0], ["5", 0], ["6", 0], seed, profile),
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
    }
    image_ref = ["8", 0]
    if quality:
        image_ref = _attach_quality(wf, ["8", 0], profile)
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "lip", "images": image_ref}}
    return wf


def build_workflow(positive: str, negative: str, seed: int, profile: GpuProfile,
                   quality: bool = False) -> dict:
    """txt2img. profile.engine 에 따라 SDXL 또는 GGUF 그래프 생성."""
    if profile.engine == "gguf":
        return build_workflow_gguf(positive, negative, seed, profile, quality=quality)
    return build_workflow_sdxl(positive, negative, seed, profile, quality=quality)


def build_img2img_workflow(image_name: str, positive: str, negative: str, seed: int,
                           profile: GpuProfile, denoise: float = 0.6,
                           quality: bool = False) -> dict:
    """img2img — SDXL 전용. GGUF 엔진이면 ValueError."""
    if profile.engine == "gguf":
        raise ValueError(
            "img2img 는 engine=sdxl 에서만 지원합니다. "
            "lip.toml [gpu] engine 을 sdxl 로 바꾸세요."
        )
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
        image_ref = _attach_quality(wf, ["8", 0], profile)
    wf["9"] = {"class_type": "SaveImage",
               "inputs": {"filename_prefix": "lip_render", "images": image_ref}}
    return wf
