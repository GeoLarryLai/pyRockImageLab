// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Larry Syu-Heng Lai
// viewer.js - canvas image viewer with pan/zoom and draggable 4-corner outlines.
"use strict";
const Viewer = (() => {
  const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
  let img = null, full = [1, 1], k = 1, ox = 0, oy = 0;      // image px (full res) -> screen: x*k*sc + ox
  let sc = 1;                                                   // preview px per full-res px
  let shapes = [], active = -1, drag = null, pan = null, onChange = () => {}, editable = true;
  const CORNERS = ["top-left", "top-right", "bottom-right", "bottom-left"];
  function sortQuad(p) {                                        // same rule as the package (TL, TR, BR, BL)
    const s = [...p].sort((a, b) => a[1] - b[1]);
    const t = s.slice(0, 2).sort((a, b) => a[0] - b[0]), b = s.slice(2).sort((a, b) => a[0] - b[0]);
    return [t[0], t[1], b[1], b[0]];
  }
  function size() { const r = cv.getBoundingClientRect(); cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio; }
  function fit() {
    if (!img) return; size();
    const W = cv.width, H = cv.height, s = Math.min(W / full[0], H / full[1]) * 0.92;
    k = s; ox = (W - full[0] * k) / 2; oy = (H - full[1] * k) / 2; draw();
  }
  const toS = p => [p[0] * k + ox, p[1] * k + oy], toI = (x, y) => [(x - ox) / k, (y - oy) / k];
  function draw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height);
    if (!img) return;
    ctx.imageSmoothingQuality = "high"; ctx.drawImage(img, ox, oy, full[0] * k, full[1] * k);
    const d = devicePixelRatio;
    shapes.forEach((s, i) => {
      if (!s.pts || !s.pts.length) return;
      const on = i === active, P = s.pts.map(toS);
      ctx.lineWidth = (on ? 2.5 : 1.6) * d; ctx.strokeStyle = s.color; ctx.fillStyle = s.color + (on ? "30" : "18");
      ctx.beginPath(); P.forEach((p, j) => j ? ctx.lineTo(...p) : ctx.moveTo(...p)); if (P.length === 4) ctx.closePath();
      if (P.length === 4) ctx.fill(); ctx.stroke();
      if (s.label && P.length === 4) {
        const cx = P.reduce((a, p) => a + p[0], 0) / 4, cy = P.reduce((a, p) => a + p[1], 0) / 4;
        ctx.font = `600 ${13 * d}px -apple-system,system-ui,sans-serif`; ctx.textAlign = "center";
        const w = ctx.measureText(s.label).width + 12 * d;
        ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillRect(cx - w / 2, cy - 11 * d, w, 22 * d);
        ctx.fillStyle = "#1d1d1f"; ctx.fillText(s.label, cx, cy + 4.5 * d);
      }
      if (on && editable) P.forEach((p, j) => {
        ctx.beginPath(); ctx.arc(p[0], p[1], 7 * d, 0, 7); ctx.fillStyle = "#fff"; ctx.fill(); ctx.lineWidth = 2.5 * d; ctx.strokeStyle = s.color; ctx.stroke();
      });
    });
  }
  async function load(url) {
    const r = await fetch(url); if (!r.ok) throw new Error("image " + r.status);
    const fs = r.headers.get("X-Full-Size"), blob = await r.blob();
    const im = new Image(); im.src = URL.createObjectURL(blob); await im.decode();
    img = im; full = fs ? fs.split("x").map(Number) : [im.width, im.height]; sc = im.width / full[0];
    fit(); return full;
  }
  function set(s, a, cb, edit = true) { shapes = s; active = a; if (cb) onChange = cb; editable = edit; draw(); }
  function hit(x, y) {
    const s = shapes[active]; if (!s || !s.pts) return -1;
    let best = -1, bd = 14 * devicePixelRatio;
    s.pts.forEach((p, j) => { const q = toS(p), dd = Math.hypot(q[0] - x, q[1] - y); if (dd < bd) { bd = dd; best = j; } });
    return best;
  }
  const ev = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * devicePixelRatio, (e.clientY - r.top) * devicePixelRatio]; };
  const clamp = p => [Math.max(0, Math.min(full[0] - 1, p[0])), Math.max(0, Math.min(full[1] - 1, p[1]))];
  cv.addEventListener("mousedown", e => {
    if (!img) return; const [x, y] = ev(e);
    if (e.button !== 0 || e.altKey || !editable || active < 0) { pan = [x, y, ox, oy]; cv.classList.add("pan"); return; }
    const s = shapes[active], j = hit(x, y);
    if (j >= 0) { drag = j; return; }
    if (!s.pts || s.pts.length >= 4) { pan = [x, y, ox, oy]; cv.classList.add("pan"); pan.moved = false; pan.click = true; return; }
    s.pts.push(clamp(toI(x, y))); if (s.pts.length === 4) { s.pts = sortQuad(s.pts); onChange(active, s.pts); } draw();
  });
  window.addEventListener("mousemove", e => {
    if (!img) return; const [x, y] = ev(e);
    if (e.target === cv) { const p = toI(x, y); document.getElementById("coord").textContent = `${Math.round(p[0])}, ${Math.round(p[1])} px`; }
    if (drag != null) { shapes[active].pts[drag] = clamp(toI(x, y)); draw(); }
    else if (pan) { ox = pan[2] + x - pan[0]; oy = pan[3] + y - pan[1]; pan.moved = true; draw(); }
  });
  window.addEventListener("mouseup", () => {
    if (drag != null) { const s = shapes[active]; s.pts = sortQuad(s.pts); onChange(active, s.pts); draw(); }
    drag = null; pan = null; cv.classList.remove("pan");
  });
  cv.addEventListener("wheel", e => {
    if (!img) return; e.preventDefault(); const [x, y] = ev(e), f = Math.exp(-e.deltaY * 0.0015);
    ox = x - (x - ox) * f; oy = y - (y - oy) * f; k *= f; draw();
  }, {passive: false});
  const zoom = f => { const x = cv.width / 2, y = cv.height / 2; ox = x - (x - ox) * f; oy = y - (y - oy) * f; k *= f; draw(); };
  document.getElementById("fitBtn").onclick = fit; document.getElementById("zin").onclick = () => zoom(1.25); document.getElementById("zout").onclick = () => zoom(0.8);
  cv.addEventListener("keydown", e => { if (e.key === "f" || e.key === "F") fit(); });
  window.addEventListener("resize", fit);
  function clear() { img = null; shapes = []; draw(); }
  return {load, set, draw, fit, clear, sortQuad, CORNERS, get full() { return full; }};
})();
