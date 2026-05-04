# Tverrprofil-pipeline Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing map-viewer frontend with a wizard landing page (login → upload → settings → run) and a job status page that shows live progress and AGOL links when done.

**Architecture:** Vanilla JS + Vite (existing tooling). Two pages: `index.html` (wizard) and `job.html` (status). No framework. Talks to FastAPI at `http://localhost:8000` with `credentials: 'include'` for session cookies.

**Tech Stack:** Vanilla JavaScript ES modules, Vite (existing), fetch API, HTML/CSS. No ArcGIS JS SDK needed for these pages (user views results in AGOL directly).

**Prerequisites:** Backend plan (`2026-05-04-tverrprofil-backend.md`) must be complete. Run `uvicorn src.api.server:app --reload` before manual testing.

---

## File Structure

**Replace:**
- `web/index.html` — wizard landing page (3 steps: login, upload, settings+run)
- `web/src/main.js` — wizard logic (auth check, file validation, form submission)

**Create:**
- `web/job.html` — job status page (progress bar, log, result links)
- `web/src/job.js` — polling logic (GET /api/jobs/{id} every 2s, DOM updates)

**No automated tests** (per spec: manuell røyktest). Each task ends with manual verification steps.

---

### Task 1: Wizard landing page (index.html + main.js)

**Files:**
- Replace: `web/index.html`
- Replace: `web/src/main.js`

- [ ] **Step 1: Replace web/index.html**

```html
<!DOCTYPE html>
<html lang="nb">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SVV IFC Profiler</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #f0f2f5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #1a3a5c;
      color: white;
      padding: 0.75rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 { font-size: 1.1rem; font-weight: 600; }
    #user-info { font-size: 0.85rem; opacity: 0.85; }

    main {
      max-width: 640px;
      margin: 2rem auto;
      padding: 0 1rem;
      width: 100%;
    }

    /* Step indicator */
    .steps {
      display: flex;
      margin-bottom: 1.5rem;
      border-radius: 6px;
      overflow: hidden;
    }
    .step {
      flex: 1;
      text-align: center;
      padding: 0.5rem;
      font-size: 0.8rem;
      background: #dde1e7;
      color: #666;
    }
    .step.active { background: #1a3a5c; color: white; }
    .step.done { background: #2e7d32; color: white; }

    /* Cards */
    .card {
      background: white;
      border-radius: 8px;
      padding: 1.25rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .card.disabled { opacity: 0.4; pointer-events: none; }
    .card h2 { font-size: 1rem; margin-bottom: 0.75rem; color: #1a3a5c; }

    /* Form elements */
    label { display: block; font-size: 0.8rem; color: #555; margin-bottom: 0.25rem; margin-top: 0.6rem; }
    label:first-child { margin-top: 0; }
    input[type="file"], input[type="number"], input[type="text"] {
      width: 100%;
      padding: 0.45rem 0.6rem;
      border: 1px solid #ccc;
      border-radius: 4px;
      font-size: 0.9rem;
    }
    .row { display: flex; gap: 0.75rem; }
    .row > div { flex: 1; }

    /* Buttons */
    .btn {
      display: block;
      width: 100%;
      padding: 0.65rem;
      border: none;
      border-radius: 5px;
      font-size: 0.95rem;
      cursor: pointer;
      font-weight: 500;
    }
    .btn-primary { background: #1a3a5c; color: white; }
    .btn-primary:hover { background: #163050; }
    .btn-success { background: #2e7d32; color: white; }
    .btn-success:hover { background: #256427; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .note { font-size: 0.75rem; color: #888; margin-top: 0.4rem; text-align: center; }
    .error-msg { color: #c62828; font-size: 0.8rem; margin-top: 0.3rem; }
  </style>
</head>
<body>
  <header>
    <h1>SVV IFC Profiler</h1>
    <span id="user-info">Ikke innlogget</span>
  </header>

  <main>
    <div class="steps">
      <div class="step active" id="step-ind-1">① Logg inn</div>
      <div class="step" id="step-ind-2">② Last opp</div>
      <div class="step" id="step-ind-3">③ Kjør</div>
    </div>

    <!-- Step 1: Login -->
    <div class="card" id="step1">
      <h2>Logg inn med ArcGIS Online</h2>
      <button class="btn btn-primary" id="login-btn" onclick="window.location='/auth/login'">
        🔐 Logg inn med ArcGIS Online
      </button>
      <p class="note">Omdirigerer til ArcGIS Online for sikker innlogging</p>
    </div>

    <!-- Step 2: Upload -->
    <div class="card disabled" id="step2">
      <h2>Last opp filer</h2>
      <label for="ifc-file">IFC-fil (.ifc, maks 500 MB) *</label>
      <input type="file" id="ifc-file" accept=".ifc" />
      <span class="error-msg" id="ifc-error"></span>

      <label for="xml-file">Senterlinje (.xml LandXML) *</label>
      <input type="file" id="xml-file" accept=".xml" />
      <span class="error-msg" id="xml-error"></span>
    </div>

    <!-- Step 3: Settings + Run -->
    <div class="card disabled" id="step3">
      <h2>Innstillinger</h2>
      <div class="row">
        <div>
          <label for="interval">Tverrprofilintervall (m)</label>
          <input type="number" id="interval" value="10" min="1" max="100" step="1" />
        </div>
        <div>
          <label for="service-name">Tjenestenavn i AGOL</label>
          <input type="text" id="service-name" placeholder="Rv4_Roa_profiler" maxlength="60" />
        </div>
      </div>
      <span class="error-msg" id="form-error"></span>
      <button class="btn btn-success" id="run-btn" style="margin-top:1rem" disabled>
        ▶ Kjør pipeline
      </button>
    </div>
  </main>

  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: Replace web/src/main.js**

```javascript
// web/src/main.js
// Wizard landing page: auth check, file validation, job submission.

const API_BASE = "http://localhost:8000";

const step2Card = document.getElementById("step2");
const step3Card = document.getElementById("step3");
const step1Ind = document.getElementById("step-ind-1");
const step2Ind = document.getElementById("step-ind-2");
const step3Ind = document.getElementById("step-ind-3");
const userInfo = document.getElementById("user-info");
const loginBtn = document.getElementById("login-btn");
const ifcFile = document.getElementById("ifc-file");
const xmlFile = document.getElementById("xml-file");
const ifcError = document.getElementById("ifc-error");
const xmlError = document.getElementById("xml-error");
const runBtn = document.getElementById("run-btn");
const formError = document.getElementById("form-error");
const serviceNameInput = document.getElementById("service-name");
const intervalInput = document.getElementById("interval");

function sanitizeName(filename) {
  return filename.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_]/g, "_").slice(0, 60);
}

function activateStep2() {
  step1Ind.classList.remove("active");
  step1Ind.classList.add("done");
  step2Ind.classList.add("active");
  step2Card.classList.remove("disabled");
}

function activateStep3() {
  step2Ind.classList.remove("active");
  step2Ind.classList.add("done");
  step3Ind.classList.add("active");
  step3Card.classList.remove("disabled");
  runBtn.disabled = false;
}

// Check if both files are selected and valid
function validateFiles() {
  let ok = true;
  ifcError.textContent = "";
  xmlError.textContent = "";

  if (ifcFile.files.length === 0) {
    ok = false;
  } else if (!ifcFile.files[0].name.toLowerCase().endsWith(".ifc")) {
    ifcError.textContent = "Velg en .ifc-fil";
    ok = false;
  }

  if (xmlFile.files.length === 0) {
    ok = false;
  } else if (!xmlFile.files[0].name.toLowerCase().endsWith(".xml")) {
    xmlError.textContent = "Velg en .xml LandXML-fil";
    ok = false;
  }

  if (ok && !step3Card.classList.contains("disabled") === false) {
    activateStep3();
  }

  if (ok && step3Card.classList.contains("disabled")) {
    activateStep3();
    // Pre-fill service name from IFC filename
    if (ifcFile.files.length > 0 && !serviceNameInput.value) {
      serviceNameInput.value = sanitizeName(ifcFile.files[0].name);
    }
  }
}

ifcFile.addEventListener("change", validateFiles);
xmlFile.addEventListener("change", validateFiles);

// Submit
runBtn.addEventListener("click", async () => {
  formError.textContent = "";
  const name = serviceNameInput.value.trim();
  const interval = parseFloat(intervalInput.value);

  if (!name) {
    formError.textContent = "Tjenestenavn er påkrevd";
    return;
  }
  if (isNaN(interval) || interval < 1 || interval > 100) {
    formError.textContent = "Tverrprofilintervall må være mellom 1 og 100";
    return;
  }
  if (ifcFile.files.length === 0 || xmlFile.files.length === 0) {
    formError.textContent = "Begge filer er påkrevd";
    return;
  }

  runBtn.disabled = true;
  runBtn.textContent = "Laster opp…";

  const fd = new FormData();
  fd.append("ifc_file", ifcFile.files[0]);
  fd.append("xml_file", xmlFile.files[0]);
  fd.append("name", name);
  fd.append("interval", String(interval));

  try {
    const resp = await fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `Feil ${resp.status}`);
    }
    const data = await resp.json();
    window.location = `/job.html?id=${data.job_id}`;
  } catch (err) {
    formError.textContent = `Feil: ${err.message}`;
    runBtn.disabled = false;
    runBtn.textContent = "▶ Kjør pipeline";
  }
});

// On load: check auth status
async function checkAuth() {
  try {
    const resp = await fetch(`${API_BASE}/auth/me`, { credentials: "include" });
    if (resp.ok) {
      const user = await resp.json();
      userInfo.textContent = `Innlogget som ${user.full_name || user.username}`;
      loginBtn.disabled = true;
      loginBtn.textContent = "✅ Innlogget";
      activateStep2();
    }
  } catch {
    // Not logged in — leave UI in initial state
  }
}

checkAuth();
```

- [ ] **Step 3: Start dev server and verify**

```bash
# Terminal 1: backend
uvicorn src.api.server:app --reload

# Terminal 2: frontend
cd web && npm run dev
```

Open `http://localhost:5173` and verify:
- [ ] Page loads without JS errors in browser console
- [ ] "Logg inn med ArcGIS Online" button is visible and clickable
- [ ] Step 2 and Step 3 cards are visually grayed out
- [ ] Clicking login button navigates to `/auth/login` (which redirects to AGOL)
- [ ] After OAuth2 callback: page reloads, user name appears in header
- [ ] Step 2 becomes active (file inputs enabled)
- [ ] Selecting an IFC + XML file activates Step 3 and pre-fills service name
- [ ] Changing service name works
- [ ] Clicking "Kjør pipeline" with valid inputs POSTs to `/api/jobs`

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/src/main.js
git commit -m "feat: replace landing page with OAuth2 wizard (login → upload → run)"
```

---

### Task 2: Job status page (job.html + job.js)

**Files:**
- Create: `web/job.html`
- Create: `web/src/job.js`

- [ ] **Step 1: Create web/job.html**

```html
<!DOCTYPE html>
<html lang="nb">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SVV IFC Profiler — Jobbstatus</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #f0f2f5;
      min-height: 100vh;
    }
    header {
      background: #1a3a5c;
      color: white;
      padding: 0.75rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 { font-size: 1.1rem; font-weight: 600; }
    header a { color: rgba(255,255,255,0.8); font-size: 0.85rem; text-decoration: none; }
    header a:hover { color: white; }

    main {
      max-width: 640px;
      margin: 2rem auto;
      padding: 0 1rem;
    }

    .card {
      background: white;
      border-radius: 8px;
      padding: 1.25rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }

    .job-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }
    .job-title { font-size: 1.05rem; font-weight: 600; color: #1a3a5c; }
    .status-badge {
      font-size: 0.8rem;
      padding: 0.2rem 0.6rem;
      border-radius: 12px;
      font-weight: 500;
    }
    .status-queued  { background: #e3f2fd; color: #1565c0; }
    .status-running { background: #e8f5e9; color: #2e7d32; }
    .status-done    { background: #e8f5e9; color: #2e7d32; }
    .status-failed  { background: #ffebee; color: #c62828; }

    /* Progress bar */
    .progress-wrap {
      background: #e0e0e0;
      border-radius: 4px;
      height: 10px;
      margin-bottom: 0.6rem;
      overflow: hidden;
    }
    .progress-bar {
      height: 100%;
      background: #1565c0;
      border-radius: 4px;
      transition: width 0.4s ease;
      width: 0%;
    }
    .progress-bar.done { background: #2e7d32; }
    .progress-bar.failed { background: #c62828; }

    #current-message {
      font-size: 0.85rem;
      color: #555;
      margin-bottom: 0.5rem;
    }

    /* Log */
    .log-title { font-size: 0.8rem; font-weight: 600; color: #888; margin: 0.75rem 0 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; }
    #status-log { list-style: none; }
    #status-log li {
      font-size: 0.82rem;
      padding: 0.2rem 0;
      color: #444;
      display: flex;
      gap: 0.5rem;
    }
    #status-log li::before { content: "✅"; }
    #status-log li.current::before { content: "⟳"; color: #1565c0; }

    /* Error box */
    #error-box {
      display: none;
      background: #ffebee;
      border: 1px solid #ef9a9a;
      border-radius: 6px;
      padding: 0.75rem 1rem;
      color: #c62828;
      font-size: 0.85rem;
    }

    /* Result links */
    #result-links { display: none; }
    .result-link {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem;
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      text-decoration: none;
      color: #1a3a5c;
      font-size: 0.9rem;
      margin-bottom: 0.5rem;
      transition: background 0.15s;
    }
    .result-link:hover { background: #f5f5f5; }
    .result-link span { font-size: 1.1rem; }

    .back-link { text-align: center; margin-top: 1rem; }
    .back-link a { color: #1a3a5c; font-size: 0.85rem; }
  </style>
</head>
<body>
  <header>
    <h1>SVV IFC Profiler</h1>
    <a href="/">← Ny jobb</a>
  </header>

  <main>
    <div class="card">
      <div class="job-header">
        <span class="job-title" id="job-title">Laster jobb…</span>
        <span class="status-badge status-queued" id="status-badge">Venter</span>
      </div>

      <div class="progress-wrap">
        <div class="progress-bar" id="progress-bar"></div>
      </div>
      <div id="current-message">Starter…</div>

      <p class="log-title">Fullførte steg</p>
      <ul id="status-log"></ul>
    </div>

    <div id="error-box"></div>

    <div id="result-links" class="card">
      <p style="font-size:0.9rem;font-weight:600;color:#2e7d32;margin-bottom:0.75rem">
        ✅ Pipeline ferdig — åpne i ArcGIS Online:
      </p>
      <a href="#" class="result-link" id="link-centerline" target="_blank">
        <span>🗺</span> Senterlinje (3D PolylineZ)
      </a>
      <a href="#" class="result-link" id="link-sections" target="_blank">
        <span>📍</span> Tverrprofil-stasjoner (PointZ + SVG-vedlegg)
      </a>
    </div>

    <div class="back-link">
      <a href="/">← Start ny jobb</a>
    </div>
  </main>

  <script type="module" src="/src/job.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create web/src/job.js**

```javascript
// web/src/job.js
// Job status page: poll GET /api/jobs/{id} every 2s, update UI.

const API_BASE = "http://localhost:8000";

const jobTitle = document.getElementById("job-title");
const statusBadge = document.getElementById("status-badge");
const progressBar = document.getElementById("progress-bar");
const currentMessage = document.getElementById("current-message");
const statusLog = document.getElementById("status-log");
const errorBox = document.getElementById("error-box");
const resultLinks = document.getElementById("result-links");
const linkCenterline = document.getElementById("link-centerline");
const linkSections = document.getElementById("link-sections");

const params = new URLSearchParams(window.location.search);
const jobId = params.get("id");

if (!jobId) {
  currentMessage.textContent = "Ingen jobb-ID i URL — gå tilbake til forsiden.";
}

let prevMessage = "";
const logMessages = [];

function addLogEntry(msg, isCurrent = false) {
  if (logMessages.includes(msg)) return;
  logMessages.push(msg);
  const li = document.createElement("li");
  li.textContent = msg;
  if (isCurrent) li.classList.add("current");
  statusLog.appendChild(li);
}

function updateUI(data) {
  // Title (use job ID as title until we have a name)
  jobTitle.textContent = jobId.slice(0, 8) + "…";

  // Status badge
  statusBadge.textContent = {
    queued: "Venter", running: "Kjører", done: "Ferdig", failed: "Feilet",
  }[data.status] ?? data.status;
  statusBadge.className = `status-badge status-${data.status}`;

  // Progress bar
  progressBar.style.width = `${data.progress_pct}%`;
  if (data.status === "done") progressBar.classList.add("done");
  if (data.status === "failed") progressBar.classList.add("failed");

  // Current message
  currentMessage.textContent = data.message || "";

  // Log (accumulate completed steps)
  if (data.message && data.message !== prevMessage && data.status !== "failed") {
    if (prevMessage) addLogEntry(prevMessage);
    prevMessage = data.message;
  }

  // Done: show result links
  if (data.status === "done") {
    resultLinks.style.display = "block";
    if (data.centerline_url) {
      linkCenterline.href = data.centerline_url;
    } else {
      linkCenterline.style.display = "none";
    }
    if (data.sections_url) {
      linkSections.href = data.sections_url;
    } else {
      linkSections.style.display = "none";
    }
  }

  // Failed: show error
  if (data.status === "failed") {
    errorBox.style.display = "block";
    errorBox.textContent = `Feil: ${data.error || "Ukjent feil"}`;
  }
}

async function pollJob() {
  if (!jobId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
      credentials: "include",
    });
    if (!resp.ok) {
      currentMessage.textContent = `HTTP ${resp.status} — jobb ikke funnet`;
      clearInterval(pollHandle);
      return;
    }
    const data = await resp.json();
    updateUI(data);

    if (data.status === "done" || data.status === "failed") {
      clearInterval(pollHandle);
    }
  } catch (err) {
    currentMessage.textContent = `Tilkoblingsfeil: ${err.message}`;
  }
}

const pollHandle = setInterval(pollJob, 2000);
pollJob(); // immediate first poll
```

- [ ] **Step 3: Verify job.html in browser**

With backend running and a job in progress (or done):

1. Open `http://localhost:5173/job.html?id=<valid-job-id>`
   - [ ] Progress bar animates from 0% to current %
   - [ ] Status message updates every 2 seconds
   - [ ] Log entries accumulate as steps complete
   - [ ] Badge color matches status (blue=running, green=done, red=failed)

2. Test with a completed job:
   - [ ] Both AGOL links appear and are clickable
   - [ ] Polling stops after `status: "done"`

3. Test with a failed job:
   - [ ] Red error box appears with error message
   - [ ] Polling stops

4. Test with unknown job ID:
   - [ ] Shows "HTTP 404 — jobb ikke funnet"

5. Test the wizard end-to-end (requires running backend with ArcPy):
   - [ ] Login → upload files → run → redirected to job.html
   - [ ] Progress increments: 0% → 5% → 50% → 70% → 100%
   - [ ] Final AGOL links open correct feature services in browser

- [ ] **Step 4: Verify no regressions**

```bash
# In web/ directory
npm run build
```
Expected: Vite builds without errors or type warnings.

- [ ] **Step 5: Commit**

```bash
git add web/job.html web/src/job.js
git commit -m "feat: add job status page with live polling and AGOL result links"
```
