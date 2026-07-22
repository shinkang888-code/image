"""LIP — Lexi Image Factory. 로컬 ComfyUI + 8GB GPU 웹 이미지 데이터 공장."""
from .config import Config, load_config
from .factory import Factory
from .jobs import GenJob, JobStore, STATUS_LABELS
from .manifest import Manifest
from .nodes import ComputeNode, NodeRegistry, ensure_default_node
from .optimize import OutputSpec, cover_resize, optimize
from .prompts import Prompt, expand, load_prompts
from .scene import scene_to_prompt
from .workflow import GpuProfile, build_img2img_workflow, build_workflow

__all__ = [
    "Config", "load_config", "Factory", "Manifest",
    "GenJob", "JobStore", "STATUS_LABELS",
    "ComputeNode", "NodeRegistry", "ensure_default_node",
    "OutputSpec", "cover_resize", "optimize",
    "Prompt", "expand", "load_prompts", "scene_to_prompt",
    "GpuProfile", "build_workflow", "build_img2img_workflow",
]
__version__ = "0.2.0"
