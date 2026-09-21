"""Shared scoring/labelling helpers for the gold-standard V/O eval, split out
of run_eval.py so a CPU-only candidate (tools/gold_eval/cpu_reference.py,
F-1) can be scored without importing render_pass.py's OpenGL/EGL
dependencies. No GPU/shader-compile code belongs in this file.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from generate_shapes import BG, FG

LUMA = lambda rgb: 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
THRESHOLD = (LUMA(np.array([[BG]])) + LUMA(np.array([[FG]]))).item() / 2.0


def nearest_neighbour(img: Image.Image, scale: int) -> np.ndarray:
    return np.array(img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST).convert("RGB"))


def score(reconstructed_rgb: np.ndarray, ground_truth_rgb: np.ndarray) -> tuple:
    recon_fg = LUMA(reconstructed_rgb.astype(np.float64)) > THRESHOLD
    gt_fg = LUMA(ground_truth_rgb.astype(np.float64)) > THRESHOLD
    intersection = np.logical_and(recon_fg, gt_fg).sum()
    union = np.logical_or(recon_fg, gt_fg).sum()
    iou = intersection / union if union > 0 else 1.0
    accuracy = (recon_fg == gt_fg).mean()
    return iou, accuracy


def label(img: Image.Image, text: str) -> Image.Image:
    bar_h = 28
    out = Image.new("RGB", (img.width, img.height + bar_h), (10, 10, 10))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((4, img.height + 6), text, fill=(255, 255, 255), font=ImageFont.load_default())
    return out


def contact_sheet(cells: list) -> Image.Image:
    w = sum(c.width for c in cells) + 8 * (len(cells) - 1)
    h = max(c.height for c in cells)
    sheet = Image.new("RGB", (w, h), (10, 10, 10))
    x = 0
    for c in cells:
        sheet.paste(c, (x, 0))
        x += c.width + 8
    return sheet
