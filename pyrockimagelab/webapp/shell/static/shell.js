// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Larry Syu-Heng Lai
// shell.js - step rail, progress, jobs, toasts, api(). Project independent (copied from pyPetrograph).
"use strict";
const Shell = (() => {
  const $ = id => document.getElementById(id);
  let steps = [], cur = 0, done = new Set(), unlocked = 1, onStep = () => {};
  function toast(msg, err) {
    const d = document.createElement("div"); d.textContent = msg; if (err) d.className = "e";
    $("toast").appendChild(d); setTimeout(() => d.remove(), err ? 7000 : 3500);
  }
  async function api(method, url, body) {
    const r = await fetch(url, {method, headers: {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
    const j = (r.headers.get("content-type") || "").includes("json") ? await r.json() : null;
    if (!r.ok) { const m = (j && j.detail) || ("HTTP " + r.status); toast(m, true); throw new Error(m); }
    return j;
  }
  function progress(n, N, msg) {
    const on = N != null; $("prog").classList.toggle("on", on);
    if (!on) { $("progtxt").textContent = ""; return; }
    const pct = Math.round(100 * Math.min(n, N) / Math.max(1, N));
    $("prog").firstElementChild.style.width = pct + "%";
    $("progtxt").textContent = `${n} / ${N} (${pct}%)` + (msg ? " · " + msg : "");
  }
  // POST url -> {job:{id}}; poll until done. Resolves with the job result, rejects on error.
  async function runJob(url, body, label) {
    busy(true);
    try {
      let j = (await api("POST", url, body)).job, wait = 40;
      while (j.state === "running") {
        progress(j.n, j.N, j.message || label); await new Promise(r => setTimeout(r, wait)); wait = Math.min(250, wait * 2);
        j = await api("GET", "/shell/api/jobs/" + j.id);
      }
      progress(j.N, j.N, (label || j.title) + (j.state === "done" ? ` · done in ${j.seconds} s` : ""));
      setTimeout(() => progress(), 2500);
      if (j.state === "error") { toast(j.error, true); throw new Error(j.error); }
      return j.result;
    } finally { busy(false); }
  }
  function busy(b) { document.body.style.cursor = b ? "progress" : ""; document.querySelectorAll("button.main").forEach(x => x.dataset.busy = b ? 1 : ""); }
  function renderRail() {
    $("rail").innerHTML = "<ol>" + steps.map((s, i) => `<li data-i="${i}" class="${i === cur ? "cur" : ""} ${done.has(i) ? "done" : ""} ${i >= unlocked ? "locked" : ""}">${s.title}</li>`).join("") + "</ol>";
    $("rail").querySelectorAll("li").forEach(li => li.onclick = () => { const i = +li.dataset.i; if (i < unlocked) go(i); });
  }
  function go(i) { cur = i; renderRail(); onStep(i, steps[i]); }
  function complete(i, next = true) { done.add(i); unlocked = Math.max(unlocked, i + 2); if (next && i + 1 < steps.length) go(i + 1); else renderRail(); }
  function reset(fromStep) { [...done].forEach(i => { if (i >= fromStep) done.delete(i); }); unlocked = Math.min(unlocked, fromStep + 1); renderRail(); }
  function help(html) { $("help").innerHTML = html; }
  function init(o) { steps = o.steps; onStep = o.onStep; renderRail();
    $("quitBtn").onclick = async () => { if (!confirm("Quit the app? Everything you saved stays on disk.")) return;
      try { await api("POST", "/shell/api/quit"); } catch (e) {} document.body.innerHTML = "<p style='padding:40px'>Stopped. You can close this tab.</p>"; };
  }
  return {init, go, complete, reset, api, runJob, toast, progress, help, $, get cur() { return cur; }, get unlocked() { return unlocked; }};
})();
