"""Depth-grounded floor geometry: fits a real 3D floor plane from a metric
depth map, measures the room and a rug-sizing quad against it, and corrects
the depth model's absolute scale drift using an object of known real-world
size (a bed, door, or chair) found in the photo.

Port of the Flask client-backend's `utils/rugs.py` floor-plane/reference-
object functions (`_backproject`, `_fit_floor_frame`, `_floor_quad_from_depth`,
`_room_dims_from_depth`, `_measure_reference_object`, `_instance_score`,
`reference_scale_factor`, `_mask_from_bbox`) — this replaced that repo's
earlier GPT-4.1-vision room-size guess (the same technique our own
_estimate_room_dimensions still uses) because guessing absolute size from
pixels alone is unreliable; grounding it in a real object's known size is
not. Debug-overlay-only drawing helpers (`_measurement_geometry`,
`_plane_to_pixel`) are intentionally not ported — nothing here renders a
debug image.

Everything here is pure numpy/cv2 — no torch dependency of its own. The
metric depth map and reference-object detections it consumes come from
imaging/depth.py.
"""

from __future__ import annotations

import cv2
import numpy as np

M_TO_FT = 3.280839895

# known_ft : the object's real-world size, in feet.
# axis     : which side of the object's FLOOR FOOTPRINT known_ft refers to.
#            'short' -> the narrow side (a bed's width, a chair's width).
#            'long'  -> the long side. Used for flat vertical objects: a door
#                       has essentially no footprint, so its floor projection
#                       collapses to a sliver whose LENGTH is the door's width.
# aspect   : plausible range for footprint_short / footprint_long. Not a hard
#            reject — it feeds the instance score, so a segment that does not
#            look like its class loses to one that does. A door's footprint is
#            a sliver (~0), a bed's is a broad rectangle, a chair's is squarish.
REFERENCE_OBJECTS = {
    "door": {"known_ft": 3.0, "axis": "long", "aspect": (0.00, 0.40)},
    "chair": {"known_ft": 2.5, "axis": "short", "aspect": (0.55, 1.10)},
    "bed": {"known_ft": 6.0, "axis": "short", "aspect": (0.45, 1.10)},
}

# Priority order. The FIRST class here with a usable instance sets the scale on
# its own — there is no averaging across classes. A class is only passed over
# when EVERY instance of it fails to measure (clipped, too few depth pixels,
# degenerate footprint, or an implausible result).
REFERENCE_PRIORITY = ("bed", "door", "chair")

# Final backstop on the returned factor.
SCALE_MIN, SCALE_MAX = 0.5, 2.0

# Per-instance gate. Failing it makes the instance fall through to the next
# instance, then the next class. This MUST stay inside [SCALE_MIN, SCALE_MAX]:
# a gate wider than the clamp lets a bad instance be "accepted" and then quietly
# clamped, which is how an 8.3 ft door (3.0/8.3 = x0.36 -> clamped x0.50) ends
# up sizing a room instead of being passed over for a better reference.
# The bound is what the depth model could credibly be wrong by — roughly +-55%.
# Anything further out is a mis-measurement, not model drift, and returning an
# uncorrected 1.0 beats acting on it.
SAMPLE_MIN, SAMPLE_MAX = 0.65, 1.55

# Instance-score weights. With one class deciding alone there is no cross-check,
# so which INSTANCE is picked matters — these rank them. Set any weight to 0 to
# drop that signal.
SCORE_W_COVERAGE = 0.35  # valid depth pixels behind the measurement
SCORE_W_MARGIN = 0.30  # clearance from the left/right frame edges
SCORE_W_NEARNESS = 0.20  # near objects have denser, more reliable depth
SCORE_W_ASPECT = 0.15  # does the footprint look like this class should?

SCORE_FULL_COVERAGE = 8000.0  # depth pixels at which coverage scores 1.0
SCORE_FAR_M = 8.0  # metres beyond the near point at which nearness -> 0
# Frame clearance scoring full marks. Actual clipping is already a hard reject,
# so this only has to penalise near-misses — demanding more clearance than this
# would punish perfectly well-framed objects for sitting off-centre.
SCORE_FULL_MARGIN = 0.05

# Sanity bounds for the measured room, same as upstream.
ROOM_MIN, ROOM_MAX = 4.0, 30.0


def _mask_from_bbox(bbox, shape) -> np.ndarray | None:
    """Filled mask from an [x1, y1, x2, y2] box — lets a detector that returns
    only boxes feed the same measurement path as OneFormer's masks, at the
    cost of including background inside the box."""
    if not bbox or len(bbox) < 4:
        return None
    H, W = shape[:2]
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox[:4])
    x1, x2 = max(0, min(x1, x2)), min(W, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(H, max(y1, y2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    mask = np.zeros((H, W), np.uint8)
    mask[y1:y2, x1:x2] = 255
    return mask


def _backproject(depth_m, mask, focal_px, min_pts=200, max_pts=40000):
    """Mask pixels -> 3D camera-space points (metres) via the pinhole model.
    Returns (points Nx3, all valid depths) or (None, None)."""
    H, W = depth_m.shape[:2]
    f = float(focal_px)
    cx, cy = W / 2.0, H / 2.0

    if mask.shape[:2] != (H, W):
        mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
    ys, xs = np.where(mask > 127)
    if len(xs) < min_pts:
        return None, None

    Z = depth_m[ys, xs].astype(np.float64)
    ok = np.isfinite(Z) & (Z > 0.1) & (Z < 30.0)
    xs, ys, Z = xs[ok], ys[ok], Z[ok]
    if len(xs) < min_pts:
        return None, None

    X = (xs - cx) * Z / f
    Y = (ys - cy) * Z / f
    P = np.stack([X, Y, Z], axis=1)
    if len(P) > max_pts:
        idx = np.linspace(0, len(P) - 1, max_pts).astype(np.int64)
        P = P[idx]
    return P, Z


def fit_floor_frame(depth_m, floor_mask, focal_px):
    """Fit the floor plane and build an in-plane coordinate frame.

    Shared by the room-dimension measurement and the reference-object
    calibration so both read the SAME plane, and it is only fitted once per
    request. Returns a dict with the plane (center/normal), an orthonormal
    in-plane basis (u1/u2), the camera-aligned axes the dimensions use
    (d_lat/d_dep), the plane-inlier points, and every valid floor depth —
    or None if a plane can't be fit.
    """
    if depth_m is None or floor_mask is None:
        return None

    P, Z_all = _backproject(depth_m, floor_mask, focal_px)
    if P is None:
        return None

    # Every floor-mask point, kept BEFORE outlier rejection. The rejection below
    # is the right thing for FITTING the plane but the wrong thing for measuring
    # how far the floor reaches: far-floor pixels are sparse and depth-noisy, so
    # four rounds of 2.5-sigma trimming eat them, and any extent measured on the
    # survivors stops short of the floor you can actually see.
    P_all = P.copy()

    # Robust floor-plane fit: SVD normal + iterative outlier rejection.
    c = P.mean(axis=0)
    n = np.array([0.0, 1.0, 0.0])
    for _ in range(4):
        _, _, vt = np.linalg.svd(P - c, full_matrices=False)
        n = vt[-1]
        dist = (P - c) @ n
        keep = np.abs(dist) <= (2.5 * float(np.std(dist)) + 1e-9)
        if keep.sum() < 50:
            break
        P = P[keep]
        c = P.mean(axis=0)

    if len(P) < 20:
        return None

    plane_resid_m = float(np.std((P - c) @ (n / (np.linalg.norm(n) + 1e-9))))

    # Two orthonormal axes spanning the floor plane.
    n = n / (np.linalg.norm(n) + 1e-9)
    seed = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    u1 = seed - (seed @ n) * n
    u1 /= np.linalg.norm(u1) + 1e-9
    u2 = np.cross(n, u1)

    forward = np.array([0.0, 0.0, 1.0])  # camera optical axis
    d_depth = forward - (forward @ n) * n  # forward projected onto the floor plane
    if np.linalg.norm(d_depth) < 1e-6:
        d_depth = u1  # near top-down view -> degenerate
    d_depth = d_depth / (np.linalg.norm(d_depth) + 1e-9)

    d_lat = np.cross(n, d_depth)  # in-plane axis perpendicular to depth
    d_lat = d_lat / (np.linalg.norm(d_lat) + 1e-9)

    return {
        "center": c,
        "normal": n,
        "u1": u1,
        "u2": u2,
        "d_lat": d_lat,
        "d_depth": d_depth,
        "points": P,
        "points_all": P_all,
        "floor_depths": Z_all,
        "plane_resid_m": plane_resid_m,
        "camera_height_m": float(abs(c @ n)),
    }


def room_dims_from_depth(depth_m, floor_mask, focal_px, scale_factor=1.0, frame=None):
    """Room width / length / area (ft) from a METRIC depth map + floor mask.

    Back-projects the floor to a 3D point cloud, robustly fits the floor plane,
    and measures the oriented rectangle that bounds it IN-PLANE (metres -> feet).
    Returns {width_ft, length_ft, area_sqft, median_depth_m, camera_height_m} or
    None if a floor plane can't be fit.

    scale_factor: multiplier from the reference-object calibration (see
    reference_scale_factor). Multiplying BOTH axes is exactly equivalent to
    rescaling the depth map itself, which is the right model for a depth-
    scale error.
    """
    if frame is None:
        frame = fit_floor_frame(depth_m, floor_mask, focal_px)
    if frame is None:
        return None

    P, c = frame["points"], frame["center"]
    lat = (P - c) @ frame["d_lat"]
    dep = (P - c) @ frame["d_depth"]

    lat_lo, lat_hi = np.percentile(lat, [1, 99])
    dep_lo, dep_hi = np.percentile(dep, [1, 99])

    s = float(scale_factor) if scale_factor and scale_factor > 0 else 1.0

    # Scale in METRES, before the sanity clamp. Clamping first and multiplying
    # after would let a 2x correction push a clamped 30 ft room out to 60 ft.
    width_ft = float(np.clip((lat_hi - lat_lo) * M_TO_FT * s, ROOM_MIN, ROOM_MAX))
    length_ft = float(np.clip((dep_hi - dep_lo) * M_TO_FT * s, ROOM_MIN, ROOM_MAX))

    return {
        "width_ft": round(width_ft, 2),
        "length_ft": round(length_ft, 2),
        "area_sqft": round(width_ft * length_ft, 2),
        "median_depth_m": round(float(np.median(frame["floor_depths"])), 2),
        "applied_scale_factor": round(s, 4),
        "camera_height_m": round(frame["camera_height_m"] * s, 2),
    }


def floor_quad_from_depth(depth_m, floor_mask, focal_px, image_shape, coverage=0.99, frame=None, scale_factor=1.0):
    """The floor rectangle to render rugs on, PLUS its own size in feet.

    Returns (quad, floor_top_y, u_span_ft, v_span_ft), where u_span_ft is the
    real length of the TL->TR edge and v_span_ft the TL->BL edge.

    The quad is the camera-aligned bounding box of the whole floor mask, taken
    in the floor plane and projected back through the pinhole model — so it
    covers every floor pixel instead of hugging the dense near-camera part the
    way a minAreaRect over plane inliers alone does (that lands its far edge
    well short of the visible floor, and a rug sized against it can never
    reach the walls).

    frame: a pre-fitted fit_floor_frame(); pass it to avoid refitting.
    scale_factor: same value passed to room_dims_from_depth — the two must
    describe the same plane and scale, since the client normalises rug size
    against these spans and maps the result through this same quad.
    """
    if frame is None:
        frame = fit_floor_frame(depth_m, floor_mask, focal_px)
    if frame is None:
        return None

    H, W = depth_m.shape[:2]
    f = float(focal_px)
    cx, cy = W / 2.0, H / 2.0

    c = frame["center"]
    d_lat, d_dep = frame["d_lat"], frame["d_depth"]

    # Measure the extent over EVERY floor-mask point, not the plane inliers.
    P = frame.get("points_all")
    if P is None or len(P) < 200:
        P = frame["points"]
    n = frame["normal"]
    resid = np.abs((P - c) @ n)
    tol = max(0.20, 4.0 * float(frame.get("plane_resid_m") or 0.0))
    on_plane = resid <= tol
    if on_plane.sum() >= 200:
        P = P[on_plane]

    lat = (P - c) @ d_lat
    dep = (P - c) @ d_dep

    lo = max(0.0, (1.0 - coverage) * 50.0)  # coverage 0.99 -> [0.5, 99.5]
    a_lo, a_hi = np.percentile(lat, [lo, 100 - lo])
    b_lo, b_hi = np.percentile(dep, [lo, 100 - lo])
    if not (a_hi > a_lo and b_hi > b_lo):
        return None

    H_img, W_img = image_shape[:2]

    def _project(a, b, eps=1e-2):
        for _ in range(24):
            P3 = c + a * d_lat + b * d_dep
            Zc = float(P3[2])
            if Zc > eps:
                return [cx + f * float(P3[0]) / Zc, cy + f * float(P3[1]) / Zc], a, b
            a *= 0.85
            b *= 0.85
        return None, a, b

    box = [(a_lo, b_hi), (a_hi, b_hi), (a_hi, b_lo), (a_lo, b_lo)]  # far-L, far-R, near-R, near-L
    img, plane = [], []
    for a, b in box:
        pt, a2, b2 = _project(a, b)
        if pt is None:
            return None
        img.append(pt)
        plane.append([a2, b2])
    img = np.array(img, dtype=np.float32)
    plane = np.array(plane, dtype=np.float64)

    # Order corners TL, TR, BR, BL.
    order = np.argsort(img[:, 1])
    top = order[:2][np.argsort(img[order[:2], 0])]
    bot = order[2:][np.argsort(img[order[2:], 0])]
    idx = [int(top[0]), int(top[1]), int(bot[1]), int(bot[0])]
    quad = img[idx].astype(np.float32)
    plane_quad = plane[idx]

    if not np.all(np.isfinite(quad)):
        return None
    if cv2.contourArea(quad) < 0.02 * W_img * H_img:
        return None
    if float(np.mean(quad[:2, 1])) >= float(np.mean(quad[2:, 1])):
        return None

    s = float(scale_factor) if scale_factor and scale_factor > 0 else 1.0
    u_span_ft = float(np.linalg.norm(plane_quad[1] - plane_quad[0]) * M_TO_FT * s)
    v_span_ft = float(np.linalg.norm(plane_quad[3] - plane_quad[0]) * M_TO_FT * s)

    floor_top_y = float(np.min(quad[:, 1]))
    return quad, floor_top_y, u_span_ft, v_span_ft


def _measure_reference_object(depth_m, focal_px, frame, obj_mask, axis, known_ft=None):
    """Real size of a detected object, in FEET, measured in the floor plane.

    Back-projects the object's mask to 3D, drops its FOOTPRINT onto the fitted
    floor plane (discards the height component), and takes the robust extent
    along the footprint's own principal axes — independent of how the object
    is turned relative to the camera. Returns (size_ft, detail_dict) or
    (None, reason).
    """
    # A reference running off the LEFT or RIGHT edge of the frame is truncated,
    # so it always reads narrower than it is — every measurement here is
    # horizontal. (Touching top/bottom is fine: a door reaches the ceiling, a
    # near bed runs off the bottom; neither truncates its width.)
    if obj_mask.shape[:2] == depth_m.shape[:2]:
        edge = obj_mask
    else:
        edge = cv2.resize(obj_mask, (depth_m.shape[1], depth_m.shape[0]), interpolation=cv2.INTER_NEAREST)
    if edge[:, :2].any() or edge[:, -2:].any():
        return None, "clipped-by-frame-edge"

    P, _ = _backproject(depth_m, obj_mask, focal_px, min_pts=150, max_pts=20000)
    if P is None:
        return None, "too-few-depth-pixels"

    # Drop depth flyers — segmentation edges bleed onto the background, and a
    # single far pixel would stretch the footprint arbitrarily.
    Zo = P[:, 2]
    z_lo, z_hi = np.percentile(Zo, [5, 95])
    band = (Zo >= z_lo - 0.35) & (Zo <= z_hi + 0.35)
    P = P[band]
    if len(P) < 100:
        return None, "depth-too-noisy"

    rel = P - frame["center"]
    pts = np.stack([rel @ frame["u1"], rel @ frame["u2"]], axis=1)

    # Oriented extents: PCA for the footprint's own axes, percentile trim for
    # robustness.
    mean2 = pts.mean(axis=0)
    centered = pts - mean2
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    lo0, hi0 = np.percentile(centered @ vt[0], [2, 98])
    lo1, hi1 = np.percentile(centered @ vt[1], [2, 98])
    s0, s1 = float(hi0 - lo0), float(hi1 - lo1)

    long_m, short_m = max(s0, s1), min(s0, s1)
    chosen_m = long_m if axis == "long" else short_m
    if chosen_m <= 0.05:
        return None, "degenerate-footprint"

    return chosen_m * M_TO_FT, {
        "footprint_short_ft": round(short_m * M_TO_FT, 2),
        "footprint_long_ft": round(long_m * M_TO_FT, 2),
        "median_depth_m": round(float(np.median(P[:, 2])), 2),
        "points": int(len(P)),
    }


def _instance_score(mask, detail, spec, image_w):
    """How much to trust one instance's measurement, in [0, 1].

    With a single class deciding the scale alone there is no cross-check
    left, so WHICH instance gets picked matters. Four signals, all pointing
    the same way — a big, close, well-framed segment whose footprint looks
    like its class is worth more than a small, distant, half-occluded one.
    """
    cols = np.where(mask.any(axis=0))[0]
    if len(cols) == 0:
        return 0.0

    margin = min(int(cols[0]), image_w - 1 - int(cols[-1])) / float(max(1, image_w))
    margin_score = min(1.0, margin / SCORE_FULL_MARGIN)

    coverage = min(1.0, float(detail.get("points", 0)) / SCORE_FULL_COVERAGE)

    near_m = float(detail.get("median_depth_m", 0.0))
    nearness = float(np.clip(1.0 - (near_m - 1.0) / SCORE_FAR_M, 0.0, 1.0))

    lo, hi = spec.get("aspect", (0.0, 1.0))
    long_ft = float(detail.get("footprint_long_ft", 0.0))
    ratio = float(detail.get("footprint_short_ft", 0.0)) / long_ft if long_ft > 1e-6 else 0.0
    if lo <= ratio <= hi:
        aspect = 1.0
    else:
        off = (lo - ratio) if ratio < lo else (ratio - hi)
        aspect = float(max(0.0, 1.0 - off / 0.35))

    return float(
        SCORE_W_COVERAGE * coverage + SCORE_W_MARGIN * margin_score + SCORE_W_NEARNESS * nearness + SCORE_W_ASPECT * aspect
    )


def reference_scale_factor(depth_m, focal_px, frame, detections):
    """ONE reference class sets the depth scale, chosen by priority.

    Walks REFERENCE_PRIORITY (bed -> door -> chair). For the first class that
    is present, every instance is measured and scored, and the best-scoring
    usable one sets scale = known_ft / measured_ft by itself — nothing is
    averaged, not across classes, and not across instances of a class.

    Returns (scale_factor, samples). Returns (1.0, samples) when nothing
    usable was found, leaving the depth map exactly as the model produced it.
    """
    samples = []
    if frame is None or depth_m is None:
        return 1.0, samples

    by_label = {}
    for index, det in enumerate(detections or []):
        if det.get("label") in REFERENCE_OBJECTS:
            by_label.setdefault(det["label"], []).append((index, det))

    def _stub(index, det, status, reason=None):
        entry = {
            "index": index,
            "label": det.get("label"),
            "known_ft": REFERENCE_OBJECTS[det["label"]]["known_ft"],
            "status": status,
        }
        if reason:
            entry["reason"] = reason
        return entry

    selected = None
    for label in REFERENCE_PRIORITY:
        entries = by_label.get(label)
        if not entries:
            continue

        spec = REFERENCE_OBJECTS[label]
        measured_here = []
        for index, det in entries:
            mask = det.get("mask")
            if mask is None:
                mask = _mask_from_bbox(det.get("bbox"), depth_m.shape[:2])
            if mask is None:
                samples.append(_stub(index, det, "rejected", "no-mask-or-bbox"))
                continue

            size_ft, detail = _measure_reference_object(depth_m, focal_px, frame, mask, spec["axis"], spec["known_ft"])
            if size_ft is None:
                samples.append(_stub(index, det, "rejected", detail))
                continue

            scale = spec["known_ft"] / size_ft
            entry = _stub(index, det, "candidate")
            entry.update(
                {
                    "measured_ft": round(float(size_ft), 2),
                    "scale": round(float(scale), 4),
                    "score": round(_instance_score(mask, detail, spec, depth_m.shape[1]), 3),
                    "footprint_short_ft": detail["footprint_short_ft"],
                    "footprint_long_ft": detail["footprint_long_ft"],
                    "median_depth_m": detail["median_depth_m"],
                    "measured_axis": spec["axis"],
                }
            )
            if not (SAMPLE_MIN <= scale <= SAMPLE_MAX):
                entry["status"] = "rejected"
                entry["reason"] = "implausible-scale"
            samples.append(entry)
            measured_here.append(entry)

        usable = [e for e in measured_here if e["status"] == "candidate"]
        if not usable:
            continue  # whole class unusable -> fall through to the next one

        best = max(usable, key=lambda e: e["score"])
        best["status"] = "selected"
        for entry in usable:
            if entry is not best:
                entry["status"] = "not-selected"
                entry["reason"] = f"lower-score-than-{best['score']}"
        selected = best
        break

    seen = {e["index"] for e in samples}
    for index, det in enumerate(detections or []):
        if index not in seen and det.get("label") in REFERENCE_OBJECTS:
            samples.append(_stub(index, det, "skipped", "higher-priority-class-used"))
    samples.sort(key=lambda e: e["index"])

    if selected is None:
        return 1.0, samples
    return float(np.clip(selected["scale"], SCALE_MIN, SCALE_MAX)), samples
