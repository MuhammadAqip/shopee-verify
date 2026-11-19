# -*- coding: utf-8 -*-
"""sad_client.py — client SadCaptcha minimal (tanpa proxy)."""
import base64, json, urllib.request

BASE = "https://www.sadcaptcha.com/api/v1"


def _post(path, key, body, timeout=90):
    url = f"{BASE}{path}?licenseKey={key}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(path, key, timeout=30):
    url = f"{BASE}{path}?licenseKey={key}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def credits(key):
    try:
        return _get("/license/credits", key).get("credits")
    except Exception:
        return None


def strip_b64(data_url):
    """canvas.toDataURL() -> b64 murni (buang prefix data:)."""
    if data_url.startswith("data:"):
        return data_url.split(",", 1)[1]
    return data_url


def solve_puzzle(key, puzzle_b64, piece_b64):
    """Slide puzzle 2-gambar. Balikin slideXProportion (0..1) atau None."""
    body = {"puzzleImageB64": strip_b64(puzzle_b64),
            "pieceImageB64": strip_b64(piece_b64)}
    try:
        return _post("/puzzle", key, body).get("slideXProportion")
    except Exception:
        return None


def pre_analyze(key, image_b64):
    try:
        return _post("/shopee-image-crawl-pre-analyze", key,
                     {"image_b64": strip_b64(image_b64)})
    except Exception:
        return {}


def solve_image_crawl(key, puzzle_b64, piece_b64, trajectory):
    body = {"puzzle_image_b64": strip_b64(puzzle_b64),
            "piece_image_b64": strip_b64(piece_b64),
            "slide_piece_trajectory": trajectory}
    try:
        return _post("/shopee-image-crawl", key, body).get("pixelsFromSliderOrigin")
    except Exception:
        return None
