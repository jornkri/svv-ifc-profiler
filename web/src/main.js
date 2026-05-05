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
    runBtn.textContent = "Kjør pipeline";
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
      loginBtn.textContent = "Innlogget";
      activateStep2();
    }
  } catch {
    // Not logged in — leave UI in initial state
  }
}

checkAuth();
