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

function addLogEntry(msg) {
  if (logMessages.includes(msg)) return;
  logMessages.push(msg);
  const li = document.createElement("li");
  li.textContent = msg;
  statusLog.appendChild(li);
}

function updateUI(data) {
  jobTitle.textContent = jobId.slice(0, 8) + "…";

  statusBadge.textContent = {
    queued: "Venter", running: "Kjører", done: "Ferdig", failed: "Feilet",
  }[data.status] ?? data.status;
  statusBadge.className = `status-badge status-${data.status}`;

  progressBar.style.width = `${data.progress_pct}%`;
  if (data.status === "done") progressBar.classList.add("done");
  if (data.status === "failed") progressBar.classList.add("failed");

  currentMessage.textContent = data.message || "";

  if (data.message && data.message !== prevMessage && data.status !== "failed") {
    if (prevMessage) addLogEntry(prevMessage);
    prevMessage = data.message;
  }

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
pollJob();
