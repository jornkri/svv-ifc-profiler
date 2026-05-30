// web/src/job.js
// Job status page: poll GET /api/jobs/{id} every 2s, update UI.

const API_BASE = "";

// ── URL params (profile selection passed from wizard) ──
const _params = new URLSearchParams(window.location.search);
const _tp  = _params.get("tp")  !== "0";
const _np  = _params.get("np")  !== "0";
const _lp  = _params.get("lp")  !== "0";
const _bim = _params.get("bim") === "1";

// ── Stage builder ──
function buildStages(tp, np, lp, bim) {
  const profilTypes = [
    tp && "tverrprofil",
    np && "normalprofil",
    lp && "lengdeprofil",
  ].filter(Boolean);

  const stages = [];

  // Always: IFC prosessering
  stages.push({
    from: 0, to: 50,
    title: "IFC-prosessering",
    meta: profilTypes.length
      ? `genererer ${profilTypes.join(", ")} langs senterlinje`
      : "prosesserer IFC-modellen",
  });

  // Always: Senterlinje AGOL
  stages.push({
    from: 50, to: 70,
    title: "Publiserer senterlinje",
    meta: "lager PolylineZ-lag i ArcGIS Online",
  });

  // Tverrprofiler AGOL (publishes tp + np SVG-attachments)
  if (tp) {
    const attachTypes = [tp && "tverrprofil", np && "normalprofil"].filter(Boolean);
    stages.push({
      from: 70, to: bim ? 80 : 100,
      title: "Publiserer profilstasjoner",
      meta: `PointZ-lag med ${attachTypes.join(" + ")} som SVG-vedlegg`,
    });
  }

  // BIM AGOL
  if (bim) {
    stages.push({
      from: tp ? 80 : 70, to: 100,
      title: "Publiserer BIM-modell",
      meta: "konverterer IFC til 3D GIS-lag i ArcGIS Online",
    });
  }

  // Fallback if nothing gets published after senterlinje
  if (!tp && !bim) {
    stages.push({
      from: 70, to: 100,
      title: "Ferdigstiller",
      meta: "verifiserer og avslutter pipeline",
    });
  }

  return stages;
}

const STAGES = buildStages(_tp, _np, _lp, _bim);

const CHECK_SVG = `<svg viewBox="0 0 24 24" fill="none" width="14" height="14" stroke-width="2"><path d="m4 12 5 5L20 6" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// ── State ──
const startTime = Date.now();
const logMessages = new Set();
let lastMessage = null;
let pollHandle = null;

// ── Job ID ──
const jobId = _params.get("id");

// ── Render stage list ──
function renderStages() {
  const container = document.getElementById("stages-container");
  container.innerHTML = STAGES.map((s, i) => `
    <div class="run-stage todo" id="stage-${i}">
      <div class="stage-marker" id="stage-${i}-marker">${i + 1}</div>
      <div class="stage-body">
        <div class="stage-title">
          <span>${s.title}</span>
          <span class="stage-status" id="stage-${i}-status">venter</span>
        </div>
        <div class="stage-meta">${s.meta}</div>
        <div class="stage-bar"><div class="stage-bar-fill" id="stage-${i}-bar"></div></div>
      </div>
    </div>
  `).join("");
}
renderStages();

// ── DOM refs ──
const jobTitle      = document.getElementById("job-title");
const jobSubtitle   = document.getElementById("job-subtitle");
const runningView   = document.getElementById("view-running");
const resultView    = document.getElementById("view-result");
const runLog        = document.getElementById("run-log");
const elapsedEl     = document.getElementById("elapsed");
const runningTitle  = document.getElementById("running-title");
const runningChip   = document.getElementById("running-chip");
const runningIcon   = document.getElementById("running-icon");

const resultHeading    = document.getElementById("result-heading");
const resultSubheading = document.getElementById("result-subheading");
const resultChip       = document.getElementById("result-chip");
const resultName       = document.getElementById("result-name");
const statCross        = document.getElementById("stat-cross");
const statKm           = document.getElementById("stat-km");
const statTime         = document.getElementById("stat-time");
const errorNotice      = document.getElementById("error-notice");
const linkCl           = document.getElementById("link-cl");
const linkTp           = document.getElementById("link-tp");
const linkBim          = document.getElementById("link-bim");
const linkBimPlan      = document.getElementById("link-bim-plan");

// ── Helpers ──
function elapsed() {
  return Math.floor((Date.now() - startTime) / 1000);
}

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatElapsedFull(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

function getStageState(from, to, pct) {
  if (pct >= to)   return "done";
  if (pct >= from) return "active";
  return "todo";
}

function getStageProg(from, to, pct) {
  if (pct >= to)   return 1;
  if (pct <= from) return 0;
  return (pct - from) / (to - from);
}

// ── Stage update ──
function updateStages(pct) {
  for (let i = 0; i < STAGES.length; i++) {
    const { from, to } = STAGES[i];
    const state = getStageState(from, to, pct);
    const prog  = getStageProg(from, to, pct);

    const stageEl  = document.getElementById(`stage-${i}`);
    const markerEl = document.getElementById(`stage-${i}-marker`);
    const statusEl = document.getElementById(`stage-${i}-status`);
    const barEl    = document.getElementById(`stage-${i}-bar`);

    // Update class
    stageEl.className = `run-stage ${state}`;

    // Marker
    if (state === "done") {
      markerEl.innerHTML = CHECK_SVG;
    } else {
      markerEl.textContent = String(i + 1);
    }

    // Status text
    if (state === "done") {
      statusEl.textContent = "ferdig";
    } else if (state === "active") {
      statusEl.textContent = Math.round(prog * 100) + "%";
    } else {
      statusEl.textContent = "venter";
    }

    // Progress bar
    barEl.style.width = Math.round(prog * 100) + "%";
  }
}

// ── Log ──
function addLogEntry(message, kind = "info") {
  if (logMessages.has(message)) return;
  logMessages.add(message);

  const sec = elapsed();
  const line = document.createElement("div");
  line.className = `log-line ${kind}`;

  const t = document.createElement("span");
  t.className = "t";
  t.textContent = formatTime(sec);

  const m = document.createElement("span");
  m.className = "m";
  m.textContent = message;

  line.appendChild(t);
  line.appendChild(m);
  runLog.appendChild(line);
  runLog.scrollTop = runLog.scrollHeight;
}

// ── Elapsed timer ──
function tickElapsed() {
  elapsedEl.textContent = formatTime(elapsed());
}
const elapsedHandle = setInterval(tickElapsed, 1000);

// ── Update UI ──
function updateUI(data) {
  updateStages(data.progress_pct ?? 0);

  if (data.message && data.message !== lastMessage) {
    const kind = data.status === "failed" ? "warn"
                : data.status === "done"   ? "ok"
                : "info";
    addLogEntry(data.message, kind);
    lastMessage = data.message;
  }

  if (data.status === "done" || data.status === "done_with_warnings") {
    clearInterval(pollHandle);
    clearInterval(elapsedHandle);
    showResult(data);
    return;
  }

  if (data.status === "failed") {
    clearInterval(pollHandle);
    clearInterval(elapsedHandle);
    showFailed(data);
    return;
  }
}

// ── Extract profile count from logged messages ──
function extractProfileCount() {
  for (const msg of logMessages) {
    const m = msg.match(/(\d+)\s*profiler/i);
    if (m) return m[1];
  }
  return null;
}

// ── Show result ──
function showResult(data) {
  // Switch views
  runningView.style.display = "none";
  resultView.style.display = "";

  const isWarnings = data.status === "done_with_warnings";

  // Page title
  jobTitle.textContent = isWarnings ? "Ferdig med advarsler" : "Tjenesten er publisert!";
  jobSubtitle.textContent = isWarnings
    ? "Pipeline fullført, men noen steg hadde advarsler."
    : "Alle lag er publisert og delt med organisasjonen.";

  // Card head
  resultHeading.textContent = isWarnings ? "Ferdig med advarsler" : "Tjenesten er publisert";
  resultSubheading.textContent = isWarnings ? "Noen steg hadde advarsler" : "Pipeline fullført uten feil";
  resultChip.className = isWarnings ? "chip amber" : "chip green";
  resultChip.textContent = isWarnings ? "Advarsler" : "Live";

  // Result name: use first 8 chars of job id
  const shortId = jobId ? jobId.slice(0, 8) + "…" : "—";
  resultName.textContent = shortId;

  // Stats
  const count = extractProfileCount();
  statCross.textContent = count || "—";
  statKm.textContent = "—";
  statTime.textContent = formatElapsedFull(elapsed());

  // Links
  if (data.centerline_url) {
    linkCl.href = data.centerline_url;
  } else {
    linkCl.style.display = "none";
  }
  if (data.sections_url) {
    linkTp.href = data.sections_url;
    const tpTypes = [_tp && "tverrprofil", _np && "normalprofil"].filter(Boolean);
    linkTp.childNodes[linkTp.childNodes.length - 1].textContent =
      ` ${tpTypes.length ? tpTypes.join(" + ") : "Profilstasjoner"} i ArcGIS Online`;
  } else {
    linkTp.style.display = "none";
  }
  if (data.bim_url) {
    linkBim.style.display = "";
    linkBim.href = data.bim_url;
  }
  if (linkBimPlan && data.bim_plan_url) {
    linkBimPlan.style.display = "";
    linkBimPlan.href = data.bim_plan_url;
  }

  // Error notice for warnings
  if (isWarnings && data.error) {
    errorNotice.style.display = "";
    errorNotice.innerHTML = `<strong>Advarsel:</strong> ${data.error}`;
  }
}

// ── Show failed state ──
function showFailed(data) {
  jobTitle.textContent = "Pipeline feilet";
  jobSubtitle.textContent = "Det oppsto en feil under prosesseringen.";
  runningTitle.textContent = "Feil under kjøring";
  runningChip.className = "chip red";
  runningChip.textContent = "Feilet";
  runningIcon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" width="24" height="24" stroke-width="1.8"><circle cx="12" cy="12" r="9" stroke="currentColor"/><path d="M15 9l-6 6M9 9l6 6" stroke="currentColor" stroke-linecap="round"/></svg>`;

  addLogEntry(`Pipeline feilet: ${data.error || "Ukjent feil"}`, "warn");
}

// ── Poll ──
async function pollJob() {
  if (!jobId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
      credentials: "include",
    });
    if (!resp.ok) {
      addLogEntry(`HTTP ${resp.status} – jobb ikke funnet`, "warn");
      clearInterval(pollHandle);
      clearInterval(elapsedHandle);
      return;
    }
    const data = await resp.json();
    updateUI(data);
  } catch (err) {
    addLogEntry(`Tilkoblingsfeil: ${err.message}`, "warn");
  }
}

// ── Init ──
if (!jobId) {
  jobTitle.textContent = "Ingen jobb-ID";
  jobSubtitle.textContent = "Gå tilbake til forsiden og start en ny jobb.";
} else {
  pollJob();
  pollHandle = setInterval(pollJob, 2000);
}
