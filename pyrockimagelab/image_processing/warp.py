"""Ortho-warp and HDR enhancement helpers."""
from __future__ import annotations

import cv2
import numpy as np


def _apply_hdr_enhancement(rgb_uint8, clip_limit=2.0, tile_size=8):
    lab = cv2.cvtColor(rgb_uint8, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

def ortho_warp_quad(img, quad_xy, interp=cv2.INTER_LANCZOS4):
    src = np.array(quad_xy, dtype=np.float32)
    if src.shape != (4, 2):
        raise ValueError(f"Quad must be 4 (x,y); got shape {src.shape}")
    w1 = np.linalg.norm(src[1] - src[0])
    w2 = np.linalg.norm(src[2] - src[3])
    h1 = np.linalg.norm(src[3] - src[0])
    h2 = np.linalg.norm(src[2] - src[1])
    out_w = max(2, int(round((w1 + w2) / 2)))
    out_h = max(2, int(round((h1 + h2) / 2)))
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (out_w, out_h), flags=interp)


def clamp_quad_to_image(quad_xy, img):
    """Clip quad corners to the image bounds (avoids empty/black margins when a
    saved quad extends past a re-stitched mosaic)."""
    h, w = img.shape[:2]
    q = np.array(quad_xy, dtype=np.float64)
    q[:, 0] = np.clip(q[:, 0], 0, w - 1)
    q[:, 1] = np.clip(q[:, 1], 0, h - 1)
    return q.tolist()


def trim_empty_rows(img, thresh=8, min_frac=0.5):
    """Drop top/bottom rows that are mostly empty (near-black) after warping."""
    filled = (img.max(axis=2) > thresh).mean(axis=1) >= min_frac
    if not filled.any():
        return img
    r0, r1 = np.where(filled)[0][[0, -1]]
    return img[r0 : r1 + 1]
