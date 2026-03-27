"""Asset generation — illustrations and video loops via local models.

Wraps ComfyUI (preferred) and HuggingFace diffusers as fallback for
generating on-brand visual assets.  All outputs are queued for human
approval (values_decision) before deployment.

Usage::

    from mandarin.ai.asset_generator import generate_illustration

    path = generate_illustration(
        "A quiet courtyard with bougainvillea and morning light",
        size=(1200, 630),
    )
    # path is None when no generation backend is available
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

CIVIC_SANCTUARY_STYLE = (
    "watercolor, warm Mediterranean tones, linen texture, "
    "muted bougainvillea rose (#946070) and cypress olive (#6A7A5A) accents, "
    "editorial illustration style, no cartoon, no gradient, "
    "hand-crafted feel, Civic Sanctuary aesthetic"
)

NEGATIVE_PROMPT = (
    "cartoon, anime, 3d render, gradient, neon, saturated, "
    "glossy, plastic, photorealistic face, text, watermark, logo"
)

from ..settings import COMFYUI_URL

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "web" / "static" / "generated"

# Supported named styles — extendable later
_STYLE_MAP: dict[str, str] = {
    "civic_sanctuary": CIVIC_SANCTUARY_STYLE,
}


# ── Availability checks ─────────────────────────────────────

def is_image_generation_available() -> bool:
    """Check if a local image generation model is available.

    Tries ComfyUI first, then checks for ``diffusers`` in the Python env.
    """
    if _is_comfyui_available():
        return True
    if _is_diffusers_available():
        return True
    return False


def _is_comfyui_available() -> bool:
    try:
        resp = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _is_diffusers_available() -> bool:
    try:
        import diffusers  # noqa: F401
        return True
    except ImportError:
        return False


# ── Public API ───────────────────────────────────────────────

def generate_illustration(
    prompt: str,
    size: tuple[int, int] = (600, 400),
    style: str = "civic_sanctuary",
    output_path: str | Path | None = None,
) -> Path | None:
    """Generate an illustration using a local Stable Diffusion backend.

    Tries ComfyUI API first, falls back to ``diffusers`` if available.
    Returns the path to the generated image, or ``None`` when no backend
    is reachable.

    All generated images are ``values_decision`` — they must be reviewed
    by a human before being deployed to production.

    Parameters
    ----------
    prompt:
        Natural-language description of the desired illustration.
    size:
        ``(width, height)`` in pixels.  Common presets:
        - ``(1200, 630)`` hero / OG images
        - ``(600, 400)``  empty-state illustrations
        - ``(600, ...)``  email headers (600 px wide)
    style:
        Named style key from ``_STYLE_MAP``.  Defaults to
        ``"civic_sanctuary"``.
    output_path:
        Where to write the result.  When *None* a timestamped filename
        inside ``web/static/generated/`` is chosen automatically.
    """
    style_suffix = _STYLE_MAP.get(style, CIVIC_SANCTUARY_STYLE)
    full_prompt = f"{prompt}, {style_suffix}"
    width, height = size

    dest = _resolve_output_path(output_path, prefix="illust", ext=".webp")

    logger.info(
        "generate_illustration  prompt=%r  size=%sx%s  dest=%s",
        prompt[:80], width, height, dest,
    )

    # 1. ComfyUI
    if _is_comfyui_available():
        ok = _generate_via_comfyui(full_prompt, width, height, dest)
        if ok:
            return dest

    # 2. diffusers
    if _is_diffusers_available():
        ok = _generate_via_diffusers(full_prompt, width, height, dest)
        if ok:
            return dest

    logger.warning("No image generation backend available — returning None")
    return None


def generate_video_loop(
    prompt: str,
    duration_s: float = 4,
    size: tuple[int, int] = (1280, 720),
    output_path: str | Path | None = None,
) -> Path | None:
    """Generate a short looping video background.

    Returns the path to the generated video, or ``None`` when no backend
    is available.

    All generated videos are ``values_decision`` — they must be reviewed
    by a human before being deployed to production.

    Parameters
    ----------
    prompt:
        Natural-language description of the desired scene.
    duration_s:
        Target duration in seconds (backend may round).
    size:
        ``(width, height)`` in pixels.
    output_path:
        Where to write the result.  When *None* a timestamped filename
        inside ``web/static/generated/`` is chosen automatically.
    """
    style_suffix = _STYLE_MAP.get("civic_sanctuary", CIVIC_SANCTUARY_STYLE)
    full_prompt = f"{prompt}, {style_suffix}"
    width, height = size

    dest = _resolve_output_path(output_path, prefix="video", ext=".mp4")

    logger.info(
        "generate_video_loop  prompt=%r  duration=%ss  size=%sx%s  dest=%s",
        prompt[:80], duration_s, width, height, dest,
    )

    # ComfyUI with AnimateDiff or SVD workflow
    if _is_comfyui_available():
        ok = _generate_video_via_comfyui(
            full_prompt, duration_s, width, height, dest,
        )
        if ok:
            return dest

    logger.warning("No video generation backend available — returning None")
    return None


# ── ComfyUI backend ─────────────────────────────────────────

def _generate_via_comfyui(
    prompt: str, width: int, height: int, dest: Path,
) -> bool:
    """Submit a txt2img workflow to ComfyUI and download the result."""
    workflow = _build_comfyui_txt2img_workflow(prompt, width, height)
    try:
        resp = httpx.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=120.0,
        )
        if resp.status_code != 200:
            logger.error("ComfyUI prompt rejected: %s", resp.text[:200])
            return False

        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            logger.error("ComfyUI returned no prompt_id")
            return False

        return _poll_comfyui_result(prompt_id, dest)

    except Exception:
        logger.exception("ComfyUI generation failed")
        return False


def _generate_video_via_comfyui(
    prompt: str, duration_s: float, width: int, height: int, dest: Path,
) -> bool:
    """Submit an AnimateDiff / SVD workflow to ComfyUI."""
    # Estimate frame count — 8 fps is typical for AnimateDiff
    fps = 8
    frames = max(8, int(duration_s * fps))

    workflow = _build_comfyui_video_workflow(prompt, width, height, frames)
    try:
        resp = httpx.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=300.0,
        )
        if resp.status_code != 200:
            logger.error("ComfyUI video prompt rejected: %s", resp.text[:200])
            return False

        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            logger.error("ComfyUI returned no prompt_id for video")
            return False

        return _poll_comfyui_result(prompt_id, dest)

    except Exception:
        logger.exception("ComfyUI video generation failed")
        return False


def _build_comfyui_txt2img_workflow(
    prompt: str, width: int, height: int,
) -> dict:
    """Minimal SDXL txt2img workflow for ComfyUI API."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int.from_bytes(os.urandom(4), "big"),
                "steps": 30,
                "cfg": 7.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE_PROMPT, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "aelu_gen", "images": ["8", 0]},
        },
    }


def _build_comfyui_video_workflow(
    prompt: str, width: int, height: int, frames: int,
) -> dict:
    """Minimal AnimateDiff video workflow for ComfyUI API."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int.from_bytes(os.urandom(4), "big"),
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["10", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width, "height": height, "batch_size": frames,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE_PROMPT, "clip": ["4", 1]},
        },
        "10": {
            "class_type": "ADE_AnimateDiffLoaderWithContext",
            "inputs": {
                "model": ["4", 0],
                "model_name": "v3_sd15_mm.ckpt",
                "context_options": ["11", 0],
            },
        },
        "11": {
            "class_type": "ADE_StandardStaticContextOptions",
            "inputs": {
                "context_length": 16,
                "context_stride": 1,
                "context_overlap": 4,
            },
        },
        "12": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["8", 0],
                "frame_rate": 8,
                "loop_count": 0,
                "filename_prefix": "aelu_video",
                "format": "video/h264-mp4",
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
    }


def _poll_comfyui_result(prompt_id: str, dest: Path) -> bool:
    """Poll ComfyUI history until the prompt completes, then save output."""
    max_wait = 300  # seconds
    poll_interval = 2.0
    elapsed = 0.0

    while elapsed < max_wait:
        try:
            resp = httpx.get(
                f"{COMFYUI_URL}/history/{prompt_id}", timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if prompt_id in data:
                    outputs = data[prompt_id].get("outputs", {})
                    return _download_comfyui_output(outputs, dest)
        except Exception:
            logger.debug("Poll attempt failed, retrying...")

        time.sleep(poll_interval)
        elapsed += poll_interval

    logger.error("ComfyUI generation timed out after %ss", max_wait)
    return False


def _download_comfyui_output(outputs: dict, dest: Path) -> bool:
    """Download the first image/video from ComfyUI output nodes."""
    for _node_id, node_output in outputs.items():
        images = node_output.get("images", []) + node_output.get("gifs", [])
        for img_info in images:
            filename = img_info.get("filename")
            subfolder = img_info.get("subfolder", "")
            if not filename:
                continue
            try:
                resp = httpx.get(
                    f"{COMFYUI_URL}/view",
                    params={
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": "output",
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(resp.content)
                    logger.info("Saved ComfyUI output → %s", dest)
                    return True
            except Exception:
                logger.exception("Failed to download ComfyUI output %s", filename)

    logger.error("No downloadable output found in ComfyUI response")
    return False


# ── diffusers backend ────────────────────────────────────────

def _generate_via_diffusers(
    prompt: str, width: int, height: int, dest: Path,
) -> bool:
    """Generate an image using HuggingFace diffusers (SDXL)."""
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError:
        logger.warning("diffusers or torch not available")
        return False

    try:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        if torch.cuda.is_available():
            device = "cuda"

        pipe = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0",
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            variant="fp16" if device == "cuda" else None,
        )
        pipe = pipe.to(device)

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            width=width,
            height=height,
            num_inference_steps=30,
            guidance_scale=7.0,
        ).images[0]

        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(dest), format="WEBP", quality=90)
        logger.info("Saved diffusers output → %s", dest)
        return True

    except Exception:
        logger.exception("diffusers generation failed")
        return False


# ── Helpers ──────────────────────────────────────────────────

def _resolve_output_path(
    user_path: str | Path | None,
    prefix: str,
    ext: str,
) -> Path:
    """Return a concrete output path, creating the parent dir if needed."""
    if user_path is not None:
        dest = Path(user_path)
    else:
        ts = time.strftime("%Y%m%d-%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        dest = _OUTPUT_DIR / f"{prefix}_{ts}_{short_id}{ext}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest
