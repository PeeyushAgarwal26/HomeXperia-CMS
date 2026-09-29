"""Faithful port of the Flask client-backend's `utils/curtain_geometry.py`
(`plan_panel_quads` and its helpers) — works out a perspective-correct quad
for each curtain panel in a window, so a single non-repeating pattern can be
warped into it (see curtain.py::warp_panel_texture) instead of tiling flat
and square inside each panel's own bounding box.

Kept as a near-verbatim port (constants, function names, debug prints
included) rather than rewritten: every rule here — the extreme-half profile
pick, the joint rod/hem fit across sibling panels, the occlusion inference,
the plausibility/sanity gates — exists because of a specific measured
production failure documented in its own comments, and re-deriving that from
scratch risks silently dropping one of those gates.
"""

from __future__ import annotations

import os
import time

import cv2
import numpy as np

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
RESET = "\033[0m"

# --- Sanity limits -----------------------------------------------------------
# A rod or hem steeper than this is a bad fit, not a room.
MAX_LINE_SLOPE = 0.6
# How far a panel's own vertical edges may lean off plumb (dx per dy).
MAX_SIDE_LEAN = 0.30
# A panel needing more than this much of its visible drop added back is
# evidence of a broken mask, not of furniture — it keeps its own edges.
MAX_EXTENSION_RATIO = 2.0
# A quad that fails to cover this much of the visible mask is rejected.
MIN_QUAD_CONTAINMENT = 0.85


def _line_at(line, u):
    return line[0] * u + line[1]


def _select_extreme(pts, is_top):
    """Keep the half of a boundary profile that lies on the real edge.

    A pleated curtain's top profile is a sawtooth of peaks and valleys, and its
    bottom profile is part hem, part occluder outline. The extreme half is the
    fabric; the other half is sag and furniture.
    """
    v = pts[:, 1]
    thr = np.percentile(v, 50)
    sel = pts[v <= thr] if is_top else pts[v >= thr]
    return sel if len(sel) >= 10 else pts


def _fit_line(pts, max_slope):
    """L1 line fit through a point cloud, as v = m*u + c. None if implausible."""
    if pts is None or len(pts) < 10:
        return None
    vx, vy, cx, cy = cv2.fitLine(pts, cv2.DIST_L1, 0, 0.01, 0.01)
    if abs(float(vx[0])) < 1e-6:
        return 0.0, float(np.median(pts[:, 1]))
    m = float(vy[0] / vx[0])
    if not np.isfinite(m) or abs(m) > max_slope:
        return None
    # Re-centre on the medians: fitLine's own anchor drifts on noisy profiles.
    c = float(np.median(pts[:, 1]) - m * np.median(pts[:, 0]))
    return m, c


def _robust_line(pts, is_top, max_slope=MAX_LINE_SLOPE, min_span=0.0):
    if pts is None or len(pts) < 10:
        return None
    if float(pts[:, 0].max() - pts[:, 0].min()) < min_span:
        # Too short a baseline to read a slope from — call it flat.
        return 0.0, float(np.median(pts[:, 1]))
    return _fit_line(_select_extreme(pts, is_top), max_slope)


def _joint_line(point_sets, is_top, max_slope=MAX_LINE_SLOPE):
    """One line through several panels' profiles.

    The extreme-half pick happens per panel and only then are the points
    pooled: a shared percentile would throw away the far panel entirely,
    because in perspective its whole edge sits above the near panel's.
    """
    sets = [_select_extreme(p, is_top) for p in point_sets if p is not None and len(p) >= 10]
    if not sets:
        return None
    return _fit_line(np.vstack(sets), max_slope)


def _corner(side, horiz):
    """Intersect a near-vertical edge (u = a*v + b) with a rod/hem (v = m*u + c)."""
    a, b = side
    m, c = horiz
    den = 1.0 - m * a
    if abs(den) < 1e-6:
        return None
    v = (m * b + c) / den
    return [a * v + b, v]


def _binarise(mask, canvas_w, canvas_h):
    """A mask at any resolution -> clean binary mask on the render canvas."""
    if mask is None:
        return None
    if len(mask.shape) == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[0] != canvas_h or mask.shape[1] != canvas_w:
        mask = cv2.resize(mask, (canvas_w, canvas_h), interpolation=cv2.INTER_NEAREST)

    b = (mask > 127).astype(np.uint8)
    if not b.any():
        return None

    k = max(3, (canvas_w // 500) | 1)
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    if not b.any():
        return None

    # Keep the panel body plus any piece furniture split off from it, and drop
    # unrelated blobs (a sheer behind the panel, a speck on another wall).
    n, labels, stats, _ = cv2.connectedComponentsWithStats(b, 8)
    if n > 2:
        main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mx0 = stats[main, cv2.CC_STAT_LEFT]
        mx1 = mx0 + stats[main, cv2.CC_STAT_WIDTH]
        keep = np.zeros(n, dtype=bool)
        keep[main] = True
        for i in range(1, n):
            if i == main or stats[i, cv2.CC_STAT_AREA] < 0.10 * stats[main, cv2.CC_STAT_AREA]:
                continue
            x0 = stats[i, cv2.CC_STAT_LEFT]
            x1 = x0 + stats[i, cv2.CC_STAT_WIDTH]
            if min(x1, mx1) - max(x0, mx0) > 0:
                keep[i] = True
        b = keep[labels].astype(np.uint8)

    return b


def _profile_panel(hotspot_id, b):
    """Measure one panel: bounding box plus its four boundary lines.

    Each boundary is kept twice. The `*_all` profile is every boundary pixel
    and is what the quad has to cover, or the warp's border mode smears the
    design's edge across whatever it missed. The filtered profile drops pixels
    sitting on the canvas edge — a frame cut is not fabric geometry — and is
    what the lines are fitted from.
    """
    H, W = b.shape[:2]
    bm = b.astype(bool)

    cols = np.flatnonzero(bm.any(axis=0))
    rows = np.flatnonzero(bm.any(axis=1))
    if len(cols) < 10 or len(rows) < 10:
        return None

    tops = bm.argmax(axis=0)[cols]
    bots = H - 1 - bm[::-1].argmax(axis=0)[cols]
    lefts = bm.argmax(axis=1)[rows]
    rights = W - 1 - bm[:, ::-1].argmax(axis=1)[rows]

    bbox = (int(cols[0]), int(tops.min()), int(cols[-1] - cols[0] + 1), int(bots.max() - tops.min() + 1))
    w, h = bbox[2], bbox[3]

    top_all = np.stack([cols, tops], axis=1).astype(np.float32)
    bot_all = np.stack([cols, bots], axis=1).astype(np.float32)
    left_all = np.stack([rows, lefts], axis=1).astype(np.float32)
    right_all = np.stack([rows, rights], axis=1).astype(np.float32)

    top = top_all[top_all[:, 1] > 1]
    bot = bot_all[bot_all[:, 1] < H - 2]
    left = left_all[left_all[:, 1] > 1]
    right = right_all[right_all[:, 1] < W - 2]

    # An edge is "clipped" once too little of it survives to fit a line worth
    # trusting. A clipped top means the rod is off-frame: better to take the
    # rod from a sibling panel, or to stay level, than to fit the few columns
    # where the fabric happens to dip into view.
    top_clipped = len(top) < max(10, 0.3 * len(top_all))
    bot_clipped = len(bot) < max(10, 0.3 * len(bot_all))

    return {
        "hid": hotspot_id,
        "b": b,
        "bbox": bbox,
        "top": top,
        "bot": bot,
        "top_all": top_all,
        "bot_all": bot_all,
        "left_all": left_all,
        "right_all": right_all,
        "top_clipped": top_clipped,
        "bot_clipped": bot_clipped,
        "ltop": None if top_clipped else _robust_line(top, True, min_span=0.15 * w),
        "lbot": None if bot_clipped else _robust_line(bot, False, min_span=0.15 * w),
        # Side edges are fitted as u = a*v + b (x as a function of y) so a
        # plumb edge reads as slope 0 instead of infinity.
        "lleft": _robust_line(left, True, max_slope=MAX_SIDE_LEAN, min_span=0.25 * h),
        "lright": _robust_line(right, False, max_slope=MAX_SIDE_LEAN, min_span=0.25 * h),
    }


def _group_rod(members):
    """The rod line for a window: one line through every measurable top edge.

    Returns (line, measured). Panels whose top is cut off by the frame
    contribute nothing to the fit but still inherit the result, which is the
    point — a clipped panel gets its rod from the sibling that can still see
    it. With nothing to fit at all the rod stays level at the highest fabric
    and is flagged unmeasured, because guessing a tilt from a few stray columns
    is how a panel ends up visibly askew.
    """
    usable = [p for p in members if not p["top_clipped"] and p["ltop"] is not None]
    if usable:
        rod = _joint_line([p["top"] for p in usable], True)
        if rod is not None:
            return rod, True
    return (0.0, float(min(p["bbox"][1] for p in members))), False


def _rod_from_hem(hem, panels):
    """A rod line inferred from the hem, for a window whose tops are all cut
    off by the frame. The mirror image of _hem_from_rod: the measured edge
    dictates the wall's tilt, and the inferred one is anchored to the fabric."""
    slope = -hem[0] / 1.1
    offset = min(float((p["top_all"][:, 1] - (slope * p["top_all"][:, 0])).min()) for p in panels)
    return slope, offset


def _end_disagreement(p, rod):
    """How much a candidate rod tilts against this panel's own top edge.

    Compares the median residual over the panel's left third with the right
    third. Pleats and mask fuzz scatter a profile without tilting it, so this
    reads real disagreement about slope and ignores noise — which matters
    because a narrow panel's own fitted slope is not trustworthy on its own.
    """
    pts = _select_extreme(p["top"], True)
    if len(pts) < 20:
        return 0.0
    x = pts[:, 0]
    lo, hi = np.percentile(x, 33), np.percentile(x, 67)
    left, right = pts[x <= lo], pts[x >= hi]
    if len(left) < 5 or len(right) < 5:
        return 0.0
    res_l = float(np.median(left[:, 1] - (rod[0] * left[:, 0] + rod[1])))
    res_r = float(np.median(right[:, 1] - (rod[0] * right[:, 0] + rod[1])))
    return abs(res_r - res_l)


def _group_panels(panels, tol_split):
    """Split panels into windows, starting from the assumption of one window.

    Curtains in one room almost always hang on one wall, and splitting a window
    that is really one window is the more damaging mistake: each panel then
    fits its own noisy slope and loses the sibling evidence that carries an
    occluded panel to the floor. So everything starts in a single group and a
    panel is only cut loose when a shared rod would visibly contradict its own
    top edge.
    """
    groups = [{"members": list(panels)}]
    for _ in range(len(panels)):
        changed = False
        for g in list(groups):
            if len(g["members"]) < 2:
                continue
            rod, _ = _group_rod(g["members"])
            # Only a panel that can actually see its own rod gets a vote. A
            # top cut off by the frame leaves a handful of columns where the
            # fabric dips into view, and those disagree with everything.
            scores = [
                (_end_disagreement(p, rod), p)
                for p in g["members"]
                if not p["top_clipped"] and p["ltop"] is not None
            ]
            if not scores:
                continue
            worst_score, worst = max(scores, key=lambda s: s[0])
            if worst_score > tol_split:
                print(
                    f"{YELLOW}   [GEOMETRY] {worst['hid']}: top edge disagrees with the "
                    f"shared rod by {worst_score:.0f}px, treating it as its own window{RESET}"
                )
                g["members"].remove(worst)
                groups.append({"members": [worst]})
                changed = True
                break
        if not changed:
            break

    for g in groups:
        g["rod"], g["rod_measured"] = _group_rod(g["members"])
    return groups


def _group_hem(group, tol):
    """The floor line shared by a window's panels.

    Furniture can only ever make a panel look shorter, never longer, so the
    lowest bottom edge in the group is the one that reached the floor. Panels
    whose own bottoms agree with it are pooled in to lengthen the baseline;
    panels sitting above it are the occluded ones, and they get extended down
    to it.
    """
    donors = [p for p in group["members"] if p["lbot"] is not None and not p["bot_clipped"]]
    if not donors:
        return None, []

    xmid = float(np.mean([p["bbox"][0] + p["bbox"][2] / 2.0 for p in group["members"]]))
    deepest = max(donors, key=lambda p: _line_at(p["lbot"], xmid))
    hem = deepest["lbot"]

    agreeing = [deepest]
    for p in donors:
        if p is deepest:
            continue
        cx = p["bbox"][0] + p["bbox"][2] / 2.0
        if abs(_line_at(p["lbot"], cx) - _line_at(hem, cx)) <= tol:
            agreeing.append(p)

    if len(agreeing) > 1:
        joint = _joint_line([p["bot"] for p in agreeing], False)
        # A refit may only ever move the hem DOWN. A visible bottom edge can
        # sit above the true hem (furniture) but never below it, so a pooled
        # fit that rises is one that got dragged up by a half-hidden panel.
        span = [min(p["bbox"][0] for p in group["members"]), max(p["bbox"][0] + p["bbox"][2] for p in group["members"])]
        if joint is not None:
            rise = max(_line_at(hem, u) - _line_at(joint, u) for u in span)
            if rise <= tol / 3.0:
                hem = joint
            else:
                agreeing = [deepest]
                print(
                    f"{YELLOW}   [GEOMETRY] pooled hem fit rose {rise:.0f}px above the "
                    f"deepest panel's own edge, keeping that panel's line{RESET}"
                )

    return hem, agreeing


def _hem_is_plausible(rod, hem):
    """Does this hem line agree with the wall the rod describes?

    Rod and hem are both horizontal lines in the wall plane, so they converge
    on that wall's vanishing point. The camera sits between hem height and rod
    height in any normal interior shot, which puts the horizon between them and
    makes the two slopes point opposite ways, at broadly similar magnitudes.
    A hem that tilts the same way as the rod, or many times harder, is not a
    floor line — it is the silhouette of whatever is standing in front of the
    curtain.
    """
    mr, mh = abs(rod[0]), abs(hem[0])
    if max(mr, mh) < 0.10:
        return True  # near-frontal wall; both slopes are noise
    if rod[0] * hem[0] >= 0:
        return False  # must converge, not diverge
    ratio = mh / max(1e-6, mr)
    return 0.2 <= ratio <= 4.0


def _hem_from_rod(rod, panels):
    """A hem line inferred from the rod when the measured one can't be trusted.

    Mirrors the rod's tilt (the camera's height between hem and rod makes the
    two roughly opposite) and drops it to the lowest fabric in the group, so it
    adds no height that was not already visible.
    """
    slope = -1.1 * rod[0]
    offset = max(float((p["bot_all"][:, 1] - (slope * p["bot_all"][:, 0])).max()) for p in panels)
    return slope, offset


def _clear_line(line, panels, key, direction, cap, label):
    """Push a fitted boundary outward until the quad covers the masks.

    Every line here is fitted through the middle of a wobbly edge, so about
    half of a pleated hem or a bulging side sits outside it. The mask is the
    final cutout, so anything it holds that the quad misses gets painted by the
    warp's border mode — i.e. the design's edge pixels dragged out into
    streaks. Nudging the boundary out to the fabric costs a few per cent of
    design scale and removes that artifact class outright.
    """
    m, c = line
    worst = 0.0
    for p in panels:
        pts = p[key]
        if len(pts) == 0:
            continue
        resid = (pts[:, 1] - (m * pts[:, 0] + c)) * direction
        # 99.5th percentile, so a few stray mask pixels can't drag the edge out.
        worst = max(worst, float(np.percentile(resid, 99.5)))
    if worst <= 1.0:
        return line
    shift = min(worst + 2.0, cap)
    if worst > cap:
        print(
            f"{YELLOW}   [GEOMETRY] {label} needed {worst:.0f}px to clear the mask, "
            f"capped at {cap:.0f}px — mask likely overruns the fabric{RESET}"
        )
    else:
        print(f"{BLUE}   [GEOMETRY] {label} nudged {shift:.0f}px to cover the mask edge{RESET}")
    return m, c + direction * shift


def _containment(quad, b):
    poly = np.zeros(b.shape[:2], np.uint8)
    cv2.fillPoly(poly, [np.round(quad).astype(np.int32)], 255)
    total = int(b.sum())
    if total == 0:
        return 0.0
    return float((poly[b > 0] > 0).sum()) / float(total)


def _build_quad(p, rod, hem, canvas_w, canvas_h):
    """Corners TL, TR, BR, BL for one panel, or None if the geometry is unsound."""
    if rod is None or hem is None:
        return None

    x, y, w, h = p["bbox"]
    # Every edge must clear this panel's mask. For the shared rod and hem that
    # already happened at window level, so this is a no-op there and only bites
    # on the per-panel fallback path — coverage holds however the quad was
    # arrived at.
    rod = _clear_line(rod, [p], "top_all", -1, max(24.0, 0.10 * h), f"{p['hid'][:8]} top")
    hem = _clear_line(hem, [p], "bot_all", +1, max(24.0, 0.15 * h), f"{p['hid'][:8]} hem")

    side_l = p["lleft"] if p["lleft"] is not None else (0.0, float(x))
    side_r = p["lright"] if p["lright"] is not None else (0.0, float(x + w))
    side_cap = max(8.0, 0.15 * w)
    side_l = _clear_line(side_l, [p], "left_all", -1, side_cap, f"{p['hid'][:8]} left edge")
    side_r = _clear_line(side_r, [p], "right_all", +1, side_cap, f"{p['hid'][:8]} right edge")

    corners = [_corner(side_l, rod), _corner(side_r, rod), _corner(side_r, hem), _corner(side_l, hem)]
    if any(c is None for c in corners):
        return None

    quad = np.array(corners, dtype=np.float32)
    if not np.all(np.isfinite(quad)):
        return None
    if np.any(np.abs(quad) > 10.0 * max(canvas_w, canvas_h)):
        return None
    # Top must stay above bottom, and left of right.
    if quad[0][1] >= quad[3][1] or quad[1][1] >= quad[2][1]:
        return None
    if quad[0][0] >= quad[1][0] or quad[3][0] >= quad[2][0]:
        return None

    cx = x + w / 2.0
    drop = _line_at(hem, cx) - _line_at(rod, cx)
    if drop > MAX_EXTENSION_RATIO * h:
        print(
            f"{YELLOW}   [QUAD REJECT] {p['hid']}: drop {drop:.0f}px is "
            f"{drop / max(1.0, float(h)):.1f}x the visible {h}px — mask looks broken{RESET}"
        )
        return None

    cov = _containment(quad, p["b"])
    if cov < MIN_QUAD_CONTAINMENT:
        print(f"{YELLOW}   [QUAD REJECT] {p['hid']}: quad covers only {cov * 100:.0f}% of the mask{RESET}")
        return None

    return quad


def plan_panel_quads(masks_by_hotspot, canvas_w, canvas_h, debug_img=None, debug_tag=None):
    """Work out where each curtain panel really hangs.

    Panels on one window hang from one rod and end on one floor line, so in the
    image their tops lie on one straight line and their hems on another, the two
    converging on that wall's vanishing point. Fitting both lines from every
    panel at once gives each panel a trapezoid consistent with its neighbours —
    which is what stops a panel half hidden behind a bed from rendering its
    pattern at the wrong height, at the wrong scale, or square against a curtain
    that is itself skewed.

    Returns {hotspot_id: {"quad_norm": [[x, y] x 4], "source": str, "group": int}}
    with corners ordered TL, TR, BR, BL and normalised to 0..1, so the caller
    can render the panel at any resolution.
    """
    panels = []
    for hotspot_id, mask in masks_by_hotspot.items():
        b = _binarise(mask, canvas_w, canvas_h)
        if b is None:
            print(f"{YELLOW}   [GEOMETRY] {hotspot_id}: empty mask, skipped{RESET}")
            continue
        p = _profile_panel(hotspot_id, b)
        if p is None:
            print(f"{YELLOW}   [GEOMETRY] {hotspot_id}: mask too small to profile, skipped{RESET}")
            continue
        panels.append(p)

    if not panels:
        return {}

    tol = max(0.015 * canvas_h, 12.0)
    groups = _group_panels(panels, max(0.04 * canvas_h, 60.0))
    print(
        f"{BLUE}[INFO] Curtain geometry: {len(panels)} panel(s) in {len(groups)} window group(s) "
        f"on a {canvas_w}x{canvas_h} canvas{RESET}"
    )

    plan = {}
    debug_lines = []

    for gi, group in enumerate(groups):
        rod = group["rod"]
        hem, donors = _group_hem(group, tol)
        donor_ids = {p["hid"] for p in donors}
        hem_kind = "group" if len(group["members"]) > 1 else "solo"

        # Whichever edge is actually visible dictates the wall's tilt and the
        # other is inferred from it. With the rod cut off by the frame, a
        # measured hem is the only real evidence there is, and judging it
        # against a level stand-in rod would throw it away.
        if hem is None:
            print(
                f"{YELLOW}   [GEOMETRY] group {gi}: no panel shows its hem; "
                f"inferring the floor line from the rod{RESET}"
            )
            hem = _hem_from_rod(rod, group["members"])
            hem_kind = "rod-prior"
            donor_ids = set()
        elif not group.get("rod_measured", True):
            rod = _rod_from_hem(hem, group["members"])
            print(
                f"{BLUE}   [GEOMETRY] group {gi}: every top is cut off by the frame; "
                f"taking the wall's tilt from the hem{RESET}"
            )
        elif not _hem_is_plausible(rod, hem):
            print(
                f"{YELLOW}   [GEOMETRY] group {gi}: hem slope {hem[0]:+.3f} contradicts rod "
                f"{rod[0]:+.3f}; inferring the hem from the rod instead{RESET}"
            )
            hem = _hem_from_rod(rod, group["members"])
            hem_kind = "rod-prior"
            donor_ids = set()

        # A hem above the rod means the fit is upside down. Fall back to the
        # rod's geometry rather than to an unvetted per-panel edge, which is
        # exactly the measurement that just failed.
        span = [min(p["bbox"][0] for p in group["members"]), max(p["bbox"][0] + p["bbox"][2] for p in group["members"])]
        if any(_line_at(hem, u) <= _line_at(rod, u) + 10 for u in span):
            print(
                f"{YELLOW}   [GEOMETRY] group {gi}: hem line is not below the rod, "
                f"inferring it from the rod instead{RESET}"
            )
            hem = _hem_from_rod(rod, group["members"])
            hem_kind = "rod-prior"
            donor_ids = set()

        # Clear the window's band outward once, so every panel in it keeps the
        # same rod, the same hem and therefore the same design scale.
        tallest = max(p["bbox"][3] for p in group["members"])
        rod = _clear_line(rod, group["members"], "top_all", -1, max(24.0, 0.10 * tallest), f"group {gi} rod")
        hem = _clear_line(hem, group["members"], "bot_all", +1, max(24.0, 0.15 * tallest), f"group {gi} hem")

        print(
            f"{BLUE}   [GROUP {gi}] rod y = {rod[0]:+.4f}x {rod[1]:+.1f} | "
            f"hem y = {hem[0]:+.4f}x {hem[1]:+.1f} "
            f"(hem from {len(donors)} floor-reaching panel(s)){RESET}"
        )
        debug_lines.append((rod, hem))

        for p in group["members"]:
            x, y, w, h = p["bbox"]
            # A lone panel's "shared" hem is just its own edge — say so, so a
            # debug log never suggests a neighbour vouched for it.
            quad, source = _build_quad(p, rod, hem, canvas_w, canvas_h), hem_kind

            if quad is None:
                # The window's band does not describe this panel: retry on its
                # own edges, which fixes the skew and adds no height.
                quad = _build_quad(p, p["ltop"] or rod, p["lbot"], canvas_w, canvas_h)
                source = "panel"

            if quad is None:
                quad = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32)
                source = "bbox"

            # Report the extension against the panel's own hem at its centre,
            # not against the bounding box: on a slanted rod the box is taller
            # than the panel's actual drop and the comparison means nothing.
            cx = x + w / 2.0
            drop = float((quad[3][1] + quad[2][1]) / 2.0 - (quad[0][1] + quad[1][1]) / 2.0)
            added = ""
            if source in ("group", "solo", "rod-prior") and p["lbot"] is not None:
                delta = _line_at(hem, cx) - _line_at(p["lbot"], cx)
                added = f", hem extended {delta:+.0f}px past the visible edge"
            print(
                f"{GREEN}   [PANEL] {p['hid']}: source={source} group={gi} "
                f"drop {drop:.0f}px{added}"
                f"{' [floor-reaching]' if p['hid'] in donor_ids else ''}{RESET}"
            )

            plan[p["hid"]] = {
                "quad_norm": [[float(px) / canvas_w, float(py) / canvas_h] for px, py in quad],
                "source": source,
                "group": gi,
            }

    if debug_img is not None:
        _draw_debug(debug_img, panels, plan, debug_lines, canvas_w, canvas_h, debug_tag)

    return plan


def _draw_debug(room_img, panels, plan, group_lines, canvas_w, canvas_h, tag):
    """One overlay per render: every mask box, every quad, every rod/hem pair."""
    try:
        os.makedirs("Debugs", exist_ok=True)
        dbg = room_img.copy()
        th = max(2, canvas_w // 600)
        colors = [(0, 0, 255), (0, 255, 0), (255, 128, 0), (0, 255, 255)]

        for rod, hem in group_lines:
            for line in (rod, hem):
                cv2.line(dbg, (0, int(_line_at(line, 0))), (canvas_w, int(_line_at(line, canvas_w))), (255, 255, 255), th)

        for i, p in enumerate(panels):
            color = colors[i % len(colors)]
            x, y, w, h = p["bbox"]
            cv2.rectangle(dbg, (x, y), (x + w, y + h), color, th)
            entry = plan.get(p["hid"])
            if entry is None:
                continue
            quad = np.array(entry["quad_norm"], np.float32) * np.array([canvas_w, canvas_h], np.float32)
            cv2.polylines(dbg, [np.round(quad).astype(np.int32)], True, color, th * 2)
            cv2.putText(
                dbg,
                f"{entry['source']} g{entry['group']} h{h}",
                (x, max(40, y - 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                canvas_w / 1600.0,
                color,
                th,
            )

        name = f"Debugs/curtain_quad_debug_{tag or int(time.time() * 1000)}.jpg"
        cv2.imwrite(name, dbg, [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f"{BLUE}   [DEBUG] Curtain geometry overlay -> {name}{RESET}")
    except Exception as e:
        print(f"{YELLOW}   [WARN] Curtain geometry debug overlay failed: {e}{RESET}")
