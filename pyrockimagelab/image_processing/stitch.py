"""SIFT+RANSAC chain stitching helpers."""
from __future__ import annotations

import cv2
import numpy as np

# Stitching defaults (notebook Step 4)
NFEATURES = 25000
MATCH_RATIO = 0.75
RANSAC_REPROJ = 3.0
WORK_MEGAPIX = 4
MAX_PERSPECT_DISTORT = 0.005
MAX_CANVAS_PIXELS = 1000_000_000

FLANN_INDEX_KDTREE = 1
_FLANN_INDEX_PARAMS = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
_FLANN_SEARCH_PARAMS = dict(checks=50)

def _resize_for_work(img, megapix=WORK_MEGAPIX):
    if megapix <= 0:
        return img, 1.0
    h, w = img.shape[:2]
    s = (megapix * 1e6 / max(1, h * w)) ** 0.5
    if s >= 1.0:
        return img, 1.0
    return (
        cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA),
        s,
    )


def _blend_canvas(imgs, transforms_3x3):
    corners = []
    for img, H in zip(imgs, transforms_3x3):
        h, w = img.shape[:2]
        pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
        warped = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
        corners.append(warped)
    all_corners = np.vstack(corners)
    x_min, y_min = np.floor(all_corners.min(axis=0)).astype(int)
    x_max, y_max = np.ceil(all_corners.max(axis=0)).astype(int)
    cw, ch = x_max - x_min, y_max - y_min
    T = np.array([[1, 0, -x_min], [0, 1, -y_min], [0, 0, 1]], dtype=np.float64)

    if cw * ch > MAX_CANVAS_PIXELS:
        scale = (MAX_CANVAS_PIXELS / (cw * ch)) ** 0.5
        T = np.diag([scale, scale, 1.0]) @ T
        cw, ch = int(cw * scale), int(ch * scale)
        print(f"    [warn] Canvas too large; downscaled to {cw}x{ch}")

    accum = np.zeros((ch, cw, 3), dtype=np.float32)
    weight = np.zeros((ch, cw), dtype=np.float32)
    for img, H in zip(imgs, transforms_3x3):
        h, w = img.shape[:2]
        H_full = T @ H
        warped = cv2.warpPerspective(img, H_full, (cw, ch), flags=cv2.INTER_LINEAR)
        mask = np.full((h, w), 255, dtype=np.uint8)
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        mx = float(dist.max()) or 1.0
        dist = (dist / mx).astype(np.float32)
        w_warp = cv2.warpPerspective(dist, H_full, (cw, ch), flags=cv2.INTER_LINEAR)
        accum += warped.astype(np.float32) * w_warp[..., None]
        weight += w_warp

    out = np.zeros((ch, cw, 3), dtype=np.uint8)
    nz = weight > 1e-6
    out[nz] = np.clip(accum[nz] / weight[nz, None], 0, 255).astype(np.uint8)

    rows = np.any(weight > 1e-6, axis=1)
    cols = np.any(weight > 1e-6, axis=0)
    if rows.any() and cols.any():
        r0, r1 = np.where(rows)[0][[0, -1]]
        c0, c1 = np.where(cols)[0][[0, -1]]
        out = out[r0 : r1 + 1, c0 : c1 + 1]
    return out


def _try_match_pair(img1, img2, verbose=True, params=None):
    p = params or {}
    nfeatures = int(p.get("NFEATURES", NFEATURES))
    match_ratio = float(p.get("MATCH_RATIO", MATCH_RATIO))
    ransac_reproj = float(p.get("RANSAC_REPROJ", RANSAC_REPROJ))
    work_megapix = float(p.get("WORK_MEGAPIX", WORK_MEGAPIX))

    sift = cv2.SIFT_create(nfeatures=nfeatures)
    work1, s1 = _resize_for_work(img1, work_megapix)
    work2, s2 = _resize_for_work(img2, work_megapix)
    kp1, d1 = sift.detectAndCompute(cv2.cvtColor(work1, cv2.COLOR_RGB2GRAY), None)
    kp2, d2 = sift.detectAndCompute(cv2.cvtColor(work2, cv2.COLOR_RGB2GRAY), None)

    H = None
    n_in = 0
    n1 = 0 if d1 is None else d1.shape[0]
    n2 = 0 if d2 is None else d2.shape[0]

    if n1 >= 4 and n2 >= 4:
        try:
            d1f = np.ascontiguousarray(d1, dtype=np.float32)
            d2f = np.ascontiguousarray(d2, dtype=np.float32)
            flann = cv2.FlannBasedMatcher(_FLANN_INDEX_PARAMS, _FLANN_SEARCH_PARAMS)
            raw = flann.knnMatch(d1f, d2f, k=2)
            good = [m for m, n in raw if m.distance < match_ratio * n.distance]
            if verbose:
                print(f"    {n1}+{n2} desc, {len(raw)} raw, {len(good)} good")
            if len(good) >= 4:
                p1 = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2) / s1
                p2 = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2) / s2
                H_cand, mask = cv2.findHomography(p2, p1, cv2.RANSAC, ransac_reproj)
                if H_cand is not None:
                    n_in = int(mask.sum()) if mask is not None else 0
                    persp = max(abs(H_cand[2, 0]), abs(H_cand[2, 1]))
                    if verbose:
                        print(f"      RANSAC: {n_in}/{len(good)} inliers, persp={persp:.2e}")
                    if persp > MAX_PERSPECT_DISTORT:
                        if verbose:
                            print(
                                f"      perspective too strong ({persp:.2e} > {MAX_PERSPECT_DISTORT}), "
                                "clamping to affine"
                            )
                        H_cand[2, 0] = 0.0
                        H_cand[2, 1] = 0.0
                        H_cand[2, 2] = 1.0
                    H = H_cand
        except cv2.error as e:
            if verbose:
                print(f"    [warn] matching failed ({e}); using translation fallback")
    elif verbose:
        print(f"    {n1}+{n2} desc — too few for matching")

    if H is None:
        h1, w1 = img1.shape[:2]
        H = np.array([[1, 0, w1 * 0.5], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        if verbose:
            print("    -> fallback: horizontal translation (50% overlap)")
    elif verbose:
        print(f"    -> accepted ({n_in} inliers)")
    return n_in, H


def stitch_chain(seg_num, imgs, picks_dict=None, params=None):
    """Sequentially stitch RGB images. Always produces output."""
    if len(imgs) == 1:
        return imgs[0]

    cumulative_H = [np.eye(3, dtype=np.float64)]
    for i in range(1, len(imgs)):
        print(f"  pair {i - 1}->{i}:")
        _, H = _try_match_pair(imgs[i - 1], imgs[i], params=params)
        cumulative_H.append(cumulative_H[-1] @ H)

    print(f"  Blending {len(imgs)} images...")
    return _blend_canvas(imgs, cumulative_H)
