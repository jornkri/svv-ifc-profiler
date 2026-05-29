// web/src/main.js
// Wizard landing page: auth check, file upload, job submission.

const API_BASE = "";

// ── State ──
let currentStep = 1;
let userInfo = null;
let ifcFile = null;
let clFile = null;
const selectedProfiles = new Set(["tverrprofil", "lengdeprofil", "normalprofil"]);

// ── DOM refs ──
const userStatus   = document.getElementById("user-status");
const stateLogin   = document.getElementById("state-login");
const stateSigned  = document.getElementById("state-signed");
const signedName   = document.getElementById("signed-name");
const signedOrg    = document.getElementById("signed-org");
const loginBtn     = document.getElementById("login-btn");
const btnTo2       = document.getElementById("btn-to-2");
const btnBack1     = document.getElementById("btn-back-1");
const btnTo3       = document.getElementById("btn-to-3");
const btnBack2     = document.getElementById("btn-back-2");
const btnRun       = document.getElementById("btn-run");

const dzIfc        = document.getElementById("dz-ifc");
const ifcInput     = document.getElementById("ifc-input");
const dzIfcIcon    = document.getElementById("dz-ifc-icon");
const dzIfcTitle   = document.getElementById("dz-ifc-title");
const dzIfcMeta    = document.getElementById("dz-ifc-meta");
const dzIfcCta     = document.getElementById("dz-ifc-cta");
const dzIfcSwap    = document.getElementById("dz-ifc-swap");

const dzXml        = document.getElementById("dz-xml");
const xmlInput     = document.getElementById("xml-input");
const dzXmlIcon    = document.getElementById("dz-xml-icon");
const dzXmlTitle   = document.getElementById("dz-xml-title");
const dzXmlMeta    = document.getElementById("dz-xml-meta");
const dzXmlCta     = document.getElementById("dz-xml-cta");
const dzXmlSwap    = document.getElementById("dz-xml-swap");

const intervalInput   = document.getElementById("interval");
const serviceNameInput = document.getElementById("service-name");
const publishBimToggle = document.getElementById("publish-bim");
const bimCrsSection   = document.getElementById("bim-crs-section");
const bimInputWkid    = document.getElementById("bim-input-wkid");
const bimOutputWkid   = document.getElementById("bim-output-wkid");
const formError       = document.getElementById("form-error");
const profileTverrCount = document.getElementById("profile-tverr-count");

const CHECK_SVG = `<svg viewBox="0 0 24 24" fill="none" width="13" height="13" stroke-width="1.6"><path d="m4 12 5 5L20 6" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const CHECK_SVG_LARGE = `<svg viewBox="0 0 24 24" fill="none" width="18" height="18" stroke-width="2"><path d="m4 12 5 5L20 6" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// ── Helpers ──
function prettyBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " kB";
  return (n / (1024 * 1024)).toFixed(1) + " MB";
}

function sanitizeName(filename) {
  return filename.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_]/g, "_").slice(0, 60);
}

// ── Stepper ──
function goToStep(n) {
  // Hide all cards
  document.getElementById("card-1").style.display = "none";
  document.getElementById("card-2").style.display = "none";
  document.getElementById("card-3").style.display = "none";
  // Show target card
  document.getElementById(`card-${n}`).style.display = "";

  // Update stepper tabs
  for (let i = 1; i <= 3; i++) {
    const tab = document.getElementById(`step-tab-${i}`);
    const num = document.getElementById(`step-num-${i}`);
    tab.classList.remove("is-active", "is-done", "is-todo");
    if (i < n) {
      tab.classList.add("is-done");
      num.innerHTML = CHECK_SVG;
    } else if (i === n) {
      tab.classList.add("is-active");
      num.textContent = String(i);
    } else {
      tab.classList.add("is-todo");
      num.textContent = String(i);
    }
  }

  currentStep = n;
}

// Stepper tab click: navigate back to done steps
for (let i = 1; i <= 3; i++) {
  document.getElementById(`step-tab-${i}`).addEventListener("click", () => {
    const tab = document.getElementById(`step-tab-${i}`);
    if (tab.classList.contains("is-done")) {
      goToStep(i);
    }
  });
}

// ── Auth ──
function showSignedInState(user) {
  userInfo = user;
  stateLogin.style.display = "none";
  stateSigned.style.display = "";
  const name = user.full_name || user.username || "—";
  signedName.textContent = name;
  signedOrg.textContent = "Statens vegvesen · Publisher";

  // Topbar
  userStatus.innerHTML = `<span class="user-dot">${name}</span>`;
}

async function checkAuth() {
  try {
    const resp = await fetch(`${API_BASE}/auth/me`, { credentials: "include" });
    if (resp.ok) {
      const user = await resp.json();
      showSignedInState(user);
      goToStep(2);
    }
  } catch {
    // Not logged in — stay on step 1
  }
}

// ── Navigation buttons ──
loginBtn.addEventListener("click", () => {
  window.location = "/auth/login";
});

btnTo2.addEventListener("click", () => goToStep(2));
btnBack1.addEventListener("click", () => goToStep(1));

btnTo3.addEventListener("click", () => {
  if (!ifcFile || !clFile) return;
  goToStep(3);
});

btnBack2.addEventListener("click", () => goToStep(2));

// ── Dropzone: IFC ──
dzIfc.addEventListener("click", (e) => {
  if (e.target === dzIfcSwap || dzIfcSwap.contains(e.target)) return;
  ifcInput.click();
});

ifcInput.addEventListener("change", () => {
  const file = ifcInput.files[0];
  if (!file) return;
  ifcFile = file;
  updateDropzone("ifc", file);
  // Auto-fill service name if empty
  if (!serviceNameInput.value) {
    serviceNameInput.value = sanitizeName(file.name);
  }
  checkBothFiles();
});

dzIfcSwap.addEventListener("click", (e) => {
  e.stopPropagation();
  ifcFile = null;
  ifcInput.value = "";
  resetDropzone("ifc");
  checkBothFiles();
});

// Drag & drop for IFC
dzIfc.addEventListener("dragover", (e) => { e.preventDefault(); dzIfc.style.borderColor = "var(--svv-navy-700)"; });
dzIfc.addEventListener("dragleave", () => { dzIfc.style.borderColor = ""; });
dzIfc.addEventListener("drop", (e) => {
  e.preventDefault();
  dzIfc.style.borderColor = "";
  const file = e.dataTransfer.files[0];
  if (file) {
    ifcFile = file;
    updateDropzone("ifc", file);
    if (!serviceNameInput.value) serviceNameInput.value = sanitizeName(file.name);
    checkBothFiles();
  }
});

// ── Dropzone: XML ──
dzXml.addEventListener("click", (e) => {
  if (e.target === dzXmlSwap || dzXmlSwap.contains(e.target)) return;
  xmlInput.click();
});

xmlInput.addEventListener("change", () => {
  const file = xmlInput.files[0];
  if (!file) return;
  clFile = file;
  updateDropzone("xml", file);
  checkBothFiles();
});

dzXmlSwap.addEventListener("click", (e) => {
  e.stopPropagation();
  clFile = null;
  xmlInput.value = "";
  resetDropzone("xml");
  checkBothFiles();
});

// Drag & drop for XML
dzXml.addEventListener("dragover", (e) => { e.preventDefault(); dzXml.style.borderColor = "var(--svv-navy-700)"; });
dzXml.addEventListener("dragleave", () => { dzXml.style.borderColor = ""; });
dzXml.addEventListener("drop", (e) => {
  e.preventDefault();
  dzXml.style.borderColor = "";
  const file = e.dataTransfer.files[0];
  if (file) {
    clFile = file;
    updateDropzone("xml", file);
    checkBothFiles();
  }
});

function updateDropzone(which, file) {
  const dz    = which === "ifc" ? dzIfc    : dzXml;
  const icon  = which === "ifc" ? dzIfcIcon : dzXmlIcon;
  const title = which === "ifc" ? dzIfcTitle : dzXmlTitle;
  const meta  = which === "ifc" ? dzIfcMeta  : dzXmlMeta;
  const cta   = which === "ifc" ? dzIfcCta   : dzXmlCta;
  const swap  = which === "ifc" ? dzIfcSwap  : dzXmlSwap;

  dz.classList.add("is-filled");
  icon.innerHTML = CHECK_SVG_LARGE;
  title.textContent = file.name;
  const lower = file.name.toLowerCase();
  const isIfcCl = which === "xml" && lower.endsWith(".ifc");
  const isLandXml = which === "xml" && lower.endsWith(".xml");
  const formatBadge = isIfcCl ? "IFC4X3 alignment" : isLandXml ? "LandXML 1.2" : "lest lokalt";
  meta.textContent = prettyBytes(file.size) + " · " + formatBadge;
  cta.style.display = "none";
  swap.style.display = "";
}

function resetDropzone(which) {
  const dz    = which === "ifc" ? dzIfc    : dzXml;
  const icon  = which === "ifc" ? dzIfcIcon : dzXmlIcon;
  const title = which === "ifc" ? dzIfcTitle : dzXmlTitle;
  const meta  = which === "ifc" ? dzIfcMeta  : dzXmlMeta;
  const cta   = which === "ifc" ? dzIfcCta   : dzXmlCta;
  const swap  = which === "ifc" ? dzIfcSwap  : dzXmlSwap;

  const defaultTitle = which === "ifc" ? "BIM-modell (.ifc, .rvt)" : "Senterlinje (.xml LandXML, .ifc 4X3)";
  const defaultMeta  = which === "ifc"
    ? "Maks 500 MB · IFC2x3 / IFC4 / Revit 2022+"
    : "LandXML 1.2 eller IFC4X3 · referansesystem hentes automatisk";
  const defaultIconHtml = which === "ifc"
    ? `<svg viewBox="0 0 24 24" fill="none" width="18" height="18" stroke-width="1.6"><path d="M12 3 3 7.5v9L12 21l9-4.5v-9L12 3Z" stroke="currentColor" stroke-linejoin="round"/><path d="M3 7.5 12 12l9-4.5M12 12v9" stroke="currentColor" stroke-linejoin="round"/></svg>`
    : `<svg viewBox="0 0 24 24" fill="none" width="20" height="20" stroke-width="1.6"><path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2V6Z" stroke="currentColor" stroke-linejoin="round"/><path d="M9 4v14M15 6v14" stroke="currentColor"/></svg>`;

  dz.classList.remove("is-filled");
  icon.innerHTML = defaultIconHtml;
  title.textContent = defaultTitle;
  meta.textContent = defaultMeta;
  cta.style.display = "";
  swap.style.display = "none";
}

function checkBothFiles() {
  btnTo3.disabled = !(ifcFile && clFile);
}

// ── BIM toggle ──
publishBimToggle.addEventListener("change", () => {
  bimCrsSection.style.display = publishBimToggle.checked ? "" : "none";
  // Animate switch thumb
  const track = publishBimToggle.nextElementSibling;
  if (publishBimToggle.checked) {
    track.classList.add("checked");
  } else {
    track.classList.remove("checked");
  }
});

// ── Profile type selection ──
["tverrprofil", "lengdeprofil", "normalprofil"].forEach(id => {
  const card = document.getElementById(`profile-${id}`);
  if (!card) return;

  function toggle() {
    if (selectedProfiles.has(id)) {
      if (selectedProfiles.size <= 1) return;
      selectedProfiles.delete(id);
      card.classList.remove("is-selected");
      card.setAttribute("aria-checked", "false");
    } else {
      selectedProfiles.add(id);
      card.classList.add("is-selected");
      card.setAttribute("aria-checked", "true");
    }
  }

  card.addEventListener("click", toggle);
  card.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(); }
  });
});

// ── Interval → update profile count hint ──
intervalInput.addEventListener("input", () => {
  const n = parseInt(intervalInput.value, 10);
  if (n >= 1) {
    profileTverrCount.textContent = `Tverrsnitt ca. hvert ${n}. meter`;
  }
});

// ── Submit ──
btnRun.addEventListener("click", async () => {
  formError.textContent = "";
  const name = serviceNameInput.value.trim();
  const interval = parseFloat(intervalInput.value);

  if (!name) {
    formError.textContent = "Tjenestenavn er påkrevd";
    return;
  }
  if (isNaN(interval) || interval < 1 || interval > 200) {
    formError.textContent = "Tverrprofilintervall må være mellom 1 og 200";
    return;
  }
  if (!ifcFile || !clFile) {
    formError.textContent = "Begge filer er påkrevd";
    return;
  }
  if (selectedProfiles.size === 0) {
    formError.textContent = "Velg minst én profiltype";
    return;
  }

  btnRun.disabled = true;
  btnRun.innerHTML = `<svg viewBox="0 0 24 24" fill="none" width="16" height="16" stroke-width="1.6" style="animation:spin 1s linear infinite"><path d="M12 3a9 9 0 1 1-9 9" stroke="currentColor" stroke-linecap="round"/></svg> Laster opp…`;

  const fd = new FormData();
  fd.append("ifc_file", ifcFile);
  fd.append("cl_file", clFile);
  fd.append("name", name);
  fd.append("interval", String(interval));
  fd.append("include_tverrprofil", selectedProfiles.has("tverrprofil") ? "true" : "false");
  fd.append("include_normalprofil", selectedProfiles.has("normalprofil") ? "true" : "false");
  fd.append("include_lengdeprofil", selectedProfiles.has("lengdeprofil") ? "true" : "false");
  fd.append("publish_bim", publishBimToggle.checked ? "true" : "false");
  if (publishBimToggle.checked) {
    const inputWkid = bimInputWkid.value.trim();
    const outputWkid = bimOutputWkid.value.trim() || "25833";
    if (inputWkid) fd.append("bim_input_wkid", inputWkid);
    fd.append("bim_output_wkid", outputWkid);
  }

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
    const tp  = selectedProfiles.has("tverrprofil")  ? "1" : "0";
    const np  = selectedProfiles.has("normalprofil") ? "1" : "0";
    const lp  = selectedProfiles.has("lengdeprofil") ? "1" : "0";
    const bim = publishBimToggle.checked ? "1" : "0";
    window.location = `/job.html?id=${data.job_id}&tp=${tp}&np=${np}&lp=${lp}&bim=${bim}`;
  } catch (err) {
    formError.textContent = `Feil: ${err.message}`;
    btnRun.disabled = false;
    btnRun.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M7 5v14l12-7L7 5Z"/></svg> Kjør pipeline`;
  }
});

// ── Init ──
checkAuth();
