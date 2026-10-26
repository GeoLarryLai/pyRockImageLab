// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Larry Syu-Heng Lai
// app.js - pyRockImageLab: start screen + two tools (Crop core-box photo, Stitch close-up photos).
"use strict";
const {$, api, runJob, toast, help} = Shell;
const COLORS = ["#2563eb", "#e11d48", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const S = {tool: null, folder: null, crop: null, cur: 1, seg: 1, sel: [], st: null, photo: 0, joined: null, saved: []};

function frame(title, lead, btns = [], body = "", helpHtml = "") {
  $("stepTitle").textContent = title; $("stepLead").textContent = lead;
  $("mainBtns").innerHTML = btns.map((b, i) => `<button id="mb${i}" class="${b.main === false ? "" : "main"}" ${b.disabled ? "disabled" : ""}>${b.label}</button>`).join("");
  btns.forEach((b, i) => $("mb" + i).onclick = b.fn);
  $("stepBody").innerHTML = body; help(helpHtml);
}
function show(what) { $("grid").hidden = what !== "grid"; }
function setDoc() {
  $("doc").textContent = (S.tool === "crop" ? "Crop core-box photo" : "Stitch close-up photos") +
    (S.folder ? ` · ${S.folder.uwi} / ${S.folder.folder} ft` : " · no folder open");
}

// ---------- start screen ----------
function home() { document.body.classList.add("home"); S.tool = null; $("doc").textContent = "Choose a tool"; help(""); }
function start(tool) {
  S.tool = tool; document.body.classList.remove("home"); Viewer.clear(); setDoc();
  const steps = tool === "crop"
    ? [{title: "Choose a folder", r: stepFolder}, {title: "Choose the box photo", r: cropPhoto}, {title: "Mark core sections", r: cropMark}, {title: "Saved images", r: cropDone}]
    : [{title: "Choose a folder", r: stepFolder}, {title: "Choose close-up photos", r: stPick}, {title: "Trim each photo", r: stTrim}, {title: "Join the photos", r: stJoin}, {title: "Straighten and save", r: stSave}];
  Shell.init({steps, onStep: (i, s) => s.r()}); Shell.reset(0); Shell.go(0);
}
$("goCrop").onclick = () => start("crop"); $("goStitch").onclick = () => start("stitch"); $("homeBtn").onclick = home;

// ---------- shared: folder ----------
async function stepFolder() {
  show("grid"); $("grid").innerHTML = "";
  const p = await api("GET", "/api/project");
  frame("Choose a folder", "Type the project folder that holds your photos, then click the well and depth range you want to work on.",
    [{label: "Show photo folders", fn: loadRoot}],
    `<div class="f"><label>Project folder</label><input id="root" type="text" placeholder="/path/to/CoreImages" value="${esc(p.root || "")}"></div>
     <p class="hintt">Expected layout: <code>Project / Well name / start-end</code>, e.g. <code>CoreImages/MyWell/2563-2572/</code> with the photos inside. Saved images go in the well folder.</p>
     <div id="flist"></div>`,
    "Press <b>Show photo folders</b>, then click a row to open it.");
  $("root").onkeydown = e => { if (e.key === "Enter") loadRoot(); };
  if (p.root) listFolders(p.folders);
}
async function loadRoot() { const r = await api("POST", "/api/project", {root: $("root").value}); listFolders(r.folders); }
function listFolders(rows) {
  const t = S.tool === "crop";
  $("flist").innerHTML = `<h3>${rows.length} photo folder${rows.length === 1 ? "" : "s"}</h3><table class="t"><tr><th>Well</th><th>Depth (ft)</th><th>Photos</th><th>${t ? "Sections saved" : "Stitched"}</th></tr>` +
    rows.map((r, i) => { const n = t ? r.cropped : r.stitched, all = t ? r.crop_complete : r.stitch_complete;
      return `<tr class="pick" data-i="${i}"><td>${esc(r.uwi)}</td><td>${esc(r.folder)}</td><td>${r.photos}</td><td><span class="tag ${all ? "ok" : n ? "todo" : ""}">${all ? "done" : n ? n + " of " + r.sections : "not started"}</span></td></tr>`; }).join("") + "</table>";
  $("flist").querySelectorAll("tr.pick").forEach(tr => tr.onclick = async () => {
    const r = rows[+tr.dataset.i]; S.folder = await api("POST", "/api/open", {uwi: r.uwi, folder: r.folder}); setDoc();
    S.crop = null; S.joined = null; S.saved = []; Shell.reset(1); Shell.complete(0);
  });
}
function thumbs(onClick, badge) {
  show("grid");
  $("grid").innerHTML = S.folder.photos.map((n, i) => `<div class="th" data-i="${i}"><img loading="lazy" src="/api/thumb/${i}"><div>${esc(n)}</div></div>`).join("");
  $("grid").querySelectorAll(".th").forEach(d => d.onclick = () => onClick(+d.dataset.i));
  badge();
}

// ---------- crop tool ----------
function cropPhoto() {
  let sel = S.folder.photos.indexOf(S.folder.box_photo);
  const mark = () => $("grid").querySelectorAll(".th").forEach(d => d.classList.toggle("sel", +d.dataset.i === sel));
  frame("Choose the box photo", "Click the photo that shows the whole core box.",
    [{label: "Use this photo", fn: async () => { if (sel < 0) return toast("Click a photo first.", true);
      S.crop = await api("POST", "/api/crop/box", {index: sel}); S.folder.box_photo = S.crop.box_photo; Shell.complete(1); }}],
    `<p class="hintt">${S.folder.photos.length} photos in this folder.</p>`, "Click a photo, then press <b>Use this photo</b>.");
  thumbs(i => { sel = i; mark(); }, mark);
}
async function cropMark() {
  show("canvas"); S.crop = S.crop || await api("GET", "/api/crop");
  await Viewer.load(`/api/photo/${S.crop.index}`);
  if (S.cur > S.crop.sections.length) S.cur = 1;
  renderCrop();
}
function cropShapes() {
  return S.crop.sections.map((s, i) => ({pts: s.corners ? s.corners.map(p => [...p]) : [], color: COLORS[i % COLORS.length], label: `${i + 1}`}));
}
function renderCrop() {
  const secs = S.crop.sections, marked = secs.filter(s => s.corners).length;
  frame("Mark core sections", "For each core section, click its four corners on the photo (or drag a corner to adjust); depth and file name fill in automatically.",
    [{label: `Save ${marked || ""} section image${marked === 1 ? "" : "s"}`, disabled: !marked, fn: cropSave}],
    `<div class="f"><label>Core sections</label><input id="nsec" type="number" min="1" max="20" value="${secs.length}"></div>` +
    secs.map((s, i) => `<div class="sec ${s.seg === S.cur ? "cur" : ""}" data-s="${s.seg}">
      <h4><span><span class="dot" style="background:${COLORS[i % COLORS.length]}"></span>Section ${s.seg}${s.seg === 1 ? " (top)" : ""}</span>
      <span class="tag ${s.saved ? "ok" : s.corners ? "todo" : ""}">${s.saved ? "saved" : s.corners ? "corners marked" : "click 4 corners"}</span></h4>
      ${s.seg === S.cur ? `<div class="f"><label>Length (ft)</label><input class="len" type="number" step="0.1" value="${esc(s.length_ft)}"></div>
      <div class="f"><label>File name</label><input class="nm" type="text" value="${esc(s.output_name)}"></div>
      <div class="btns"><button class="clr">Clear corners</button><button class="pv" ${s.corners ? "" : "disabled"}>Preview</button></div><div class="pvo"></div>` : ""}</div>`).join(""),
    "Click 4 corners · drag a white dot to adjust · scroll to zoom · drag the photo to move it · <kbd>F</kbd> fit");
  Viewer.set(cropShapes(), S.cur - 1, async (i, pts) => {
    const r = await api("POST", "/api/crop/sections", {sections: [{seg: i + 1, corners: pts}]}); keepIdx(r);
    const nxt = S.crop.sections.find(s => !s.corners); if (nxt && S.cur === i + 1) S.cur = nxt.seg; renderCrop();
  });
  $("nsec").onchange = async e => { const r = await api("POST", "/api/crop/sections", {n_sections: +e.target.value}); keepIdx(r); renderCrop(); };
  $("stepBody").querySelectorAll(".sec").forEach(d => d.onclick = e => { if (e.target.closest("input,button")) return; S.cur = +d.dataset.s; renderCrop(); });
  const c = $("stepBody").querySelector(".sec.cur"); if (!c) return;
  c.querySelector(".len").onchange = async e => { const r = await api("POST", "/api/crop/sections", {sections: [{seg: S.cur, length_ft: e.target.value}]}); keepIdx(r); renderCrop(); };
  c.querySelector(".nm").onchange = async e => { const r = await api("POST", "/api/crop/sections", {sections: [{seg: S.cur, output_name: e.target.value}]}); keepIdx(r); };
  c.querySelector(".clr").onclick = async () => { keepIdx(await api("POST", "/api/crop/sections", {sections: [{seg: S.cur, clear: true}]})); renderCrop(); };
  c.querySelector(".pv").onclick = async () => {
    const s = S.crop.sections[S.cur - 1]; const r = await fetch("/api/crop/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({corners: s.corners})});
    c.querySelector(".pvo").innerHTML = `<div class="prevbox"><img src="${URL.createObjectURL(await r.blob())}"></div>`;
  };
}
function keepIdx(r) { S.crop = r; }
async function cropSave() {
  const r = await runJob("/api/crop/save", {}, "Saving section images");
  S.saved = r.saved; S.outDir = r.out_dir; S.crop = await api("GET", "/api/crop"); toast(`Saved ${r.saved.length} image(s).`); Shell.complete(2);
}
function outList(items) {
  return `<div class="out">` + items.map(s => `<a href="#" data-n="${esc(s.name)}.png">${esc(s.name)}</a><span class="note">${s.size[0]} × ${s.size[1]} px · ${s.files.join(", ")}</span>`).join("") + `</div>`;
}
function wireOut() {
  $("stepBody").querySelectorAll(".out a").forEach(a => a.onclick = async e => { e.preventDefault(); show("canvas"); Viewer.set([], -1); await Viewer.load("/api/output/" + encodeURIComponent(a.dataset.n)); });
  const o = $("openOut"); if (o) o.onclick = () => api("POST", "/shell/api/open_folder", {path: S.outDir});
}
async function cropDone() {
  frame("Saved images", "Each core section is saved as a straightened TIFF and PNG (300 dpi) in the well folder; click a name to view it.",
    [{label: "Open output folder", fn: () => api("POST", "/shell/api/open_folder", {path: S.outDir || S.folder.out_dir})},
     {label: "Crop another folder", main: false, fn: () => Shell.go(0)}, {label: "Back to start", main: false, fn: home}],
    `<p class="hintt">Saved to <code>${esc(S.outDir || S.folder.out_dir)}</code></p>` + outList(S.saved || []));
  wireOut(); if (S.saved && S.saved[0]) { show("canvas"); Viewer.set([], -1); await Viewer.load("/api/output/" + encodeURIComponent(S.saved[0].name + ".png")); }
}

// ---------- stitch tool ----------
function stPick() {
  const n = S.folder.n_sections, A = S.folder.assignments;
  S.sel = [...(A["seg" + S.seg] || [])];
  const used = {}; Object.entries(A).forEach(([k, v]) => { if (k !== "seg" + S.seg) v.forEach(i => used[i] = k.slice(3)); });
  const mark = () => {
    $("grid").querySelectorAll(".th").forEach(d => { const i = +d.dataset.i, o = S.sel.indexOf(i);
      d.classList.toggle("sel", o >= 0); d.querySelectorAll(".badge,.used").forEach(x => x.remove());
      if (o >= 0) d.insertAdjacentHTML("beforeend", `<span class="badge">${o + 1}</span>`);
      else if (used[i]) d.insertAdjacentHTML("beforeend", `<span class="used">section ${used[i]}</span>`); });
    const b = $("mb0"); if (b) { b.disabled = !S.sel.length; b.textContent = `Use these ${S.sel.length || ""} photos`; }
  };
  frame("Choose close-up photos", "Pick the core section you are stitching, then click its close-up photos in order from top to bottom.",
    [{label: "Use these photos", fn: async () => { const r = await api("POST", "/api/stitch/assign", {seg: S.seg, indices: S.sel});
      S.folder.assignments = r.assignments; S.photo = 0; S.joined = null; Shell.reset(2); Shell.complete(1); }}],
    `<div class="f"><label>Core section</label><select id="segSel">${Array.from({length: n}, (_, i) => `<option value="${i + 1}" ${i + 1 === S.seg ? "selected" : ""}>Section ${i + 1}${A["seg" + (i + 1)] ? " · " + A["seg" + (i + 1)].length + " photos" : ""}</option>`).join("")}</select></div>
     <p class="hintt">Numbers on the photos show the joining order. Click a photo again to remove it.</p>
     <div class="btns"><button id="clrSel">Clear selection</button></div>`,
    "Click photos in order, top of the core first, then press <b>Use these photos</b>.");
  $("segSel").onchange = e => { S.seg = +e.target.value; stPick(); };
  $("clrSel").onclick = () => { S.sel = []; mark(); };
  thumbs(i => { const o = S.sel.indexOf(i); o >= 0 ? S.sel.splice(o, 1) : S.sel.push(i); mark(); }, mark);
}
async function stTrim() {
  show("canvas"); S.st = await api("GET", `/api/stitch/${S.seg}`);
  if (S.photo >= S.st.photos.length) S.photo = 0;
  const p = S.st.photos[S.photo];
  await Viewer.load(`/api/photo/${p.index}`);
  const done = S.st.photos.filter(x => x.corners).length;
  frame("Trim each photo", "Click the four corners of the core in each photo to cut away the background; drag a corner to adjust.",
    [{label: "Next: join the photos", fn: () => { Shell.complete(2); }}],
    `<p class="hintt">Section ${S.seg} · photo ${S.photo + 1} of ${S.st.photos.length} · ${done} trimmed</p>
     <div class="strip">${S.st.photos.map((x, j) => `<img src="/api/thumb/${x.index}" data-j="${j}" class="${j === S.photo ? "cur" : ""} ${x.corners ? "ok" : ""}" title="${esc(x.name)}">`).join("")}</div>
     <p><b>${esc(p.name)}</b> <span class="tag ${p.corners ? "ok" : ""}">${p.corners ? "trimmed" : "whole photo"}</span></p>
     <div class="btns"><button id="prevPh" ${S.photo ? "" : "disabled"}>‹ Previous photo</button><button id="nextPh" ${S.photo < S.st.photos.length - 1 ? "" : "disabled"}>Next photo ›</button></div>
     <div class="btns"><button id="wholePh">Use whole photo</button></div>`,
    "Click 4 corners · drag a white dot to adjust · scroll to zoom · drag the photo to move it");
  Viewer.set([{pts: p.corners ? p.corners.map(q => [...q]) : [], color: COLORS[0]}], 0, async (i, pts) => {
    await api("POST", "/api/stitch/trim", {index: p.index, corners: pts}); S.joined = null;
    if (S.photo < S.st.photos.length - 1 && !p.corners) { S.photo++; } stTrim();
  });
  $("stepBody").querySelectorAll(".strip img").forEach(im => im.onclick = () => { S.photo = +im.dataset.j; stTrim(); });
  $("prevPh").onclick = () => { S.photo--; stTrim(); }; $("nextPh").onclick = () => { S.photo++; stTrim(); };
  $("wholePh").onclick = async () => { await api("POST", "/api/stitch/trim", {index: p.index, corners: null}); S.joined = null; stTrim(); };
}
const PARAMS = [["NFEATURES", "Features to find per photo", 1000], ["MATCH_RATIO", "Match strictness (lower = stricter)", 0.01], ["RANSAC_REPROJ", "Alignment tolerance (px)", 0.5], ["WORK_MEGAPIX", "Working size (megapixels)", 0.5]];
async function stJoin() {
  S.st = await api("GET", `/api/stitch/${S.seg}`);
  const pr = S.st.params;
  frame("Join the photos", "Join the trimmed photos into one image; if the photos line up badly, change the matching settings and join again.",
    [{label: S.joined ? "Join again" : "Join photos", fn: doJoin}, ...(S.joined ? [{label: "Next: straighten and save", fn: () => Shell.complete(3)}] : [])],
    `<p class="hintt">Section ${S.seg} · ${S.st.photos.length} photos, joined top to bottom.</p>
     ${S.joined ? `<p>Joined image: <b>${S.joined[0]} × ${S.joined[1]} px</b></p>` : ""}
     <details ${S.joined ? "" : ""}><summary>Matching settings</summary>${PARAMS.map(([k, l, s]) => `<div class="f"><label>${l}</label><input id="p_${k}" type="number" step="${s}" value="${pr[k]}"></div>`).join("")}
     <p class="hintt">The defaults work for most core photos. More features or a looser match can help photos with little texture.</p></details>`,
    "Joining takes a few seconds per photo.");
  if (S.joined) { show("canvas"); Viewer.set([], -1); await Viewer.load(`/api/stitch/${S.seg}/joined.jpg`); }
  else { show("grid"); $("grid").innerHTML = S.st.photos.map((x, j) => `<div class="th"><img src="/api/thumb/${x.index}"><span class="badge">${j + 1}</span><div>${esc(x.name)}</div></div>`).join(""); }
}
async function doJoin() {
  const params = {}; PARAMS.forEach(([k]) => params[k] = +$("p_" + k).value);
  const changed = PARAMS.some(([k]) => params[k] !== S.st.params[k]);
  const r = await runJob("/api/stitch/join", {seg: S.seg, params: changed ? params : undefined}, "Joining photos");
  S.joined = r.size; stJoin();
}
async function stSave() {
  show("canvas"); S.st = await api("GET", `/api/stitch/${S.seg}`);
  if (!S.st.joined) { toast("Join the photos first.", true); return Shell.go(3); }
  await Viewer.load(`/api/stitch/${S.seg}/joined.jpg`);
  const shape = [{pts: S.st.corners ? S.st.corners.map(q => [...q]) : [], color: COLORS[1]}];
  frame("Straighten and save", "Drag the four corners to the edges of the core (or click them if none are shown), check the file name, then save.",
    [{label: "Save image", fn: async () => {
      const r = await runJob("/api/stitch/save", {seg: S.seg, corners: shape[0].pts.length === 4 ? shape[0].pts : null, output_name: $("hrName").value}, "Saving image");
      S.outDir = r.out_dir; S.saved = [r]; toast("Saved " + r.name);
      $("res").innerHTML = `<h3>Saved</h3>` + outList([r]) + `<div class="btns"><button id="openOut">Open output folder</button><button id="another">Stitch another section</button></div>`;
      wireOut(); $("another").onclick = () => { S.seg = Math.min(S.folder.n_sections, S.seg + 1); S.joined = null; Shell.reset(1); Shell.go(1); }; }}],
    `<div class="f"><label>File name</label><input id="hrName" type="text" value="${esc(S.st.output_name)}"></div>
     <p class="hintt">Saved as TIFF and PNG (600 dpi) in the well folder. Rows left empty after straightening are trimmed off.</p><div id="res"></div>`,
    "Drag a white dot to adjust · scroll to zoom · drag the image to move it");
  Viewer.set(shape, 0, () => {});
}
home();
