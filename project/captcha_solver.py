# -*- coding: utf-8 -*-
"""captcha_solver.py — SadCaptcha untuk Shopee, TANPA PROXY.

Aturan: semua request keluar langsung dari IP VPS (--noproxy).
"""

from __future__ import annotations

import random
import time

from sad_client import credits, solve_puzzle, pre_analyze

# ---------------- konstanta gesture (dari skill, jangan diubah) ----------------
GESTURE_AMP_U = 1.5
GESTURE_PASSES = 4
GESTURE_PACE_MS = 2
PAUSE_BEFORE_NUDGE_MS = (900, 2100)
PAUSE_BEFORE_RELEASE_MS = (750, 1450)
OVERSHOOT_PX = 15
SWING_SAFE_PX = 12
SCATTER_BLOCK_PX = 30
SKIP_CAP = 3

PROBE_JS = """() => {
  const all = [...document.querySelectorAll('canvas')];
  const pz = all.filter(c => c.draggable === false && c.width > 200)
                .sort((a,b) => b.width - a.width)[0];
  const rest = all.filter(c => c !== pz);
  const pc = rest.filter(c => c.width > 20 && c.width < (pz ? pz.width - 5 : 1e9))
                 .sort((a,b) => a.width - b.width)[0];
  const r = e => { if (!e) return null; const b = e.getBoundingClientRect();
                   return {x:b.x, y:b.y, w:b.width, h:b.height}; };
  return {
    puzzle: pz ? {w:pz.width, h:pz.height, rect:r(pz)} : null,
    piece:  pc ? {w:pc.width, h:pc.height, rect:r(pc)} : null,
  };
}"""

READY_JS = """() => {
  const all = [...document.querySelectorAll('canvas')];
  const pz = all.filter(c => c.draggable === false && c.width > 200)
                .sort((a,b) => b.width - a.width)[0];
  const rest = all.filter(c => c !== pz);
  const pc = rest.filter(c => c.width > 20 && c.width < (pz ? pz.width - 5 : 1e9))
                 .sort((a,b) => a.width - b.width)[0];
  if (!pz || !pc) return {ready:false, why:'canvas kurang'};
  let pzB='', pcB='';
  try { pzB = pz.toDataURL(); pcB = pc.toDataURL(); } catch(e) {
    return {ready:false, why:'tainted'};
  }
  const rp = pz.getBoundingClientRect(), rc = pc.getBoundingClientRect();
  if (pzB.length <= 20000) return {ready:false, why:'puzzle belum paint ('+pzB.length+')'};
  if (pcB.length <= 900)   return {ready:false, why:'piece belum paint ('+pcB.length+')'};
  if (rc.x === rp.x && rc.y === rp.y) return {ready:false, why:'piece di origin'};
  return {ready:true, puzzleB64:pzB, pieceB64:pcB,
          puzzle:{w:pz.width,h:pz.height,x:rp.x,y:rp.y},
          piece:{w:pc.width,h:pc.height,x:rc.x,y:rc.y},
          propX: (rc.x - rp.x) / rp.width};
}"""

HANDLE_JS = """(a) => {
  const all = [...document.querySelectorAll('canvas')];
  const pz = all.filter(c => c.draggable === false && c.width > 200)
                .sort((a,b) => b.width - a.width)[0];
  if (!pz) return null;
  const pr = pz.getBoundingClientRect();
  const cands = [...document.querySelectorAll('div')].filter(d => {
    const r = d.getBoundingClientRect();
    if (r.width > 56 || r.width < 30) return false;
    if (Math.abs(r.width - r.height) > 6) return false;
    if (!d.querySelector('svg')) return false;
    if (d.querySelector('canvas')) return false;
    return r.top > pr.bottom - 40 && r.top < pr.bottom + 160;
  }).map(d => { const r = d.getBoundingClientRect();
    let depth = 0, p = d; while (p) { depth++; p = p.parentElement; }
    return {x:r.x + r.width/2, y:r.y + r.height/2, left:r.x, depth}; });
  if (!cands.length) return null;
  cands.sort((a,b) => (b.depth - a.depth) || (a.left - b.left));
  return {x:cands[0].x, y:cands[0].y};
}"""


def wait_ready(page, timeout=100):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = page.evaluate(READY_JS)
        if d.get("ready"):
            return d
        time.sleep(1.2)
    return None


def probe_page(page):
    d = page.evaluate(READY_JS)
    return d if d.get("ready") else page.evaluate(PROBE_JS)


def solve_on_page(page, key, log=print) -> bool:
    """Solve captcha yang sedang tampil. True kalau sudah lewat."""
    for attempt in range(1, SKIP_CAP + 1):
        st = wait_ready(page, timeout=90)
        if not st:
            log(f"attempt {attempt}: canvas tidak pernah siap")
            return False

        pw, ph = st["puzzle"]["w"], st["puzzle"]["h"]
        log(f"attempt {attempt}: puzzle {pw}x{ph} piece {st['piece']['w']} "
            f"propX={st['propX']:.3f}")

        # pre-analyze dulu (opsional tapi membantu)
        pa = pre_analyze(key, st["puzzleB64"]) or {}
        target = pa.get("slideXProportion")
        if pa.get("skipRecommended"):
            log("  pre-analyze: skip disarankan -> refresh")
            _refresh(page)
            continue

        if target is None:
            target = solve_puzzle(key, st["puzzleB64"], st["pieceB64"])
        if target is None:
            log("  solver gagal -> refresh")
            _refresh(page)
            continue
        log(f"  target propX={target:.4f}")

        if _drag(page, target, st, log):
            page.wait_for_timeout(2500)
            if "/verify/" not in page.url:
                log(f"  LULUS -> {page.url[:60]}")
                return True
            log("  drag selesai tapi masih di /verify -> ulang")
        _refresh(page)
    return False


def _refresh(page):
    try:
        btn = page.locator("text=/Coba Lagi|Try Again/i").first
        if btn.is_visible(timeout=1500):
            btn.click()
            page.wait_for_timeout(3000)
            return
    except Exception:
        pass
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)


def _drag(page, target_prop, st, log) -> bool:
    h = page.evaluate(HANDLE_JS, {})
    if not h:
        log("  handle tidak ketemu")
        return False
    gx, gy = h["x"], h["y"]
    pw = st["puzzle"]["w"]
    page.mouse.move(gx, gy)
    page.mouse.down()
    time.sleep(random.uniform(0.15, 0.35))

    cur, moved = st["propX"], 0.0
    max_move = pw * 0.92
    while moved < max_move:
        if abs(target_prop - cur) < 0.010:
            break
        moved += 2.0
        jx = random.uniform(-0.6, 0.6)
        jy = random.uniform(-0.6, 0.6) - 6 * min(1, moved / (pw * 0.9))
        page.mouse.move(gx + moved + jx, gy + jy)
        time.sleep(random.uniform(9, 20) / 1000)
        p = page.evaluate(READY_JS)
        if p.get("ready"):
            cur = p["propX"]

    time.sleep(random.uniform(*PAUSE_BEFORE_RELEASE_MS) / 1000)
    page.mouse.up()
    log(f"  release di +{moved:.0f}px, propX={cur:.3f}")
    return True


def key_credits(key):
    return credits(key)
