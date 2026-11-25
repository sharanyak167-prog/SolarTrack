/**
 * SolarTrack Frontend Application Logic
 * Pure vanilla JavaScript with Chart.js and REST API integration.
 */

const API_BASE = "";
let currentUser = null;
let currentConnectionId = 1;
let currentBills = [];
let currentRates = [];
let selectedBill = null;
let charts = {};

// ================= INITIALIZATION & AUTH =================

document.addEventListener("DOMContentLoaded", async () => {
  initAuth();
  if (currentUser) {
    await loadConnections();
    await loadDashboard();
  }
  setupDragAndDrop();
});

function getAuthHeader() {
  const token = localStorage.getItem("solartrack_token");
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

function initAuth() {
  const savedUser = localStorage.getItem("solartrack_user");
  const savedToken = localStorage.getItem("solartrack_token");
  if (savedUser && savedToken) {
    try {
      currentUser = JSON.parse(savedUser);
      updateUserUI();
    } catch (e) {
      logout();
    }
  } else {
    currentUser = null;
    updateUserUI();
    const modal = document.getElementById("authModal");
    if (modal) modal.style.display = "flex";
  }
}

function updateUserUI() {
  const badge = document.getElementById("userBadge");
  const btn = document.getElementById("authBtn");
  const adminElements = document.querySelectorAll(".admin-only");

  if (currentUser && currentUser.username) {
    badge.textContent = `${currentUser.full_name || currentUser.username} (${currentUser.role})`;
    btn.textContent = "Logout";
    btn.onclick = logout;

    if (currentUser.role === "admin") {
      adminElements.forEach(el => el.style.display = "");
    } else {
      adminElements.forEach(el => el.style.display = "none");
    }
  } else {
    badge.textContent = "Not logged in";
    btn.textContent = "Login";
    btn.onclick = toggleAuthModal;
    adminElements.forEach(el => el.style.display = "none");
  }
}

function toggleAuthModal() {
  const m = document.getElementById("authModal");
  m.style.display = m.style.display === "none" ? "flex" : "none";
}

function closeAuthModal() {
  document.getElementById("authModal").style.display = "none";
}

function fillCreds(u, p) {
  document.getElementById("loginUsername").value = u;
  document.getElementById("loginPassword").value = p;
}

async function submitLogin(e) {
  e.preventDefault();
  const u = document.getElementById("loginUsername").value.trim();
  const p = document.getElementById("loginPassword").value.trim();

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });

    if (!res.ok) {
      const err = await res.json();
      alert("Login failed: " + (err.detail || "Invalid credentials"));
      return;
    }

    const data = await res.json();
    currentUser = { username: data.username, role: data.role, full_name: data.full_name };
    localStorage.setItem("solartrack_token", data.access_token);
    localStorage.setItem("solartrack_user", JSON.stringify(currentUser));
    document.cookie = `access_token=${data.access_token}; path=/; max-age=43200; SameSite=Lax`;

    closeAuthModal();
    updateUserUI();
    loadConnections();
    loadDashboard();
    loadBills();
  } catch (err) {
    alert("Connection error during login: " + err.message);
  }
}

function logout() {
  localStorage.removeItem("solartrack_token");
  localStorage.removeItem("solartrack_user");
  document.cookie = "access_token=; path=/; max-age=0";
  currentUser = null;
  updateUserUI();
  location.reload();
}

// Navigation Tabs
function switchTab(tabId) {
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));

  const targetPane = document.getElementById(`tab-${tabId}`);
  if (targetPane) targetPane.classList.add("active");

  const clickedTab = Array.from(document.querySelectorAll(".nav-tab")).find(b => b.getAttribute("onclick")?.includes(tabId));
  if (clickedTab) clickedTab.classList.add("active");

  updateUserUI();

  if (tabId === "dashboard") loadDashboard();
  if (tabId === "bills") loadBills();
  if (tabId === "rates") loadRates();
  if (tabId === "reports") generateReportPreview();
  if (tabId === "users") loadUsers();
  if (tabId === "backup") loadBackupsAndAudit();
}

// Connections
async function loadConnections() {
  try {
    const res = await fetch(`${API_BASE}/connections`, { headers: getAuthHeader() });
    if (res.ok) {
      const list = await res.json();
      if (list.length > 0) {
        currentConnectionId = list[0].id;
        document.getElementById("connBadge").textContent = `RR: ${list[0].rr_number} (${list[0].tariff || 'HT'})`;
      }
    }
  } catch (e) {
    console.error("Failed to load connections:", e);
  }
}

// ================= TAB 1: DASHBOARD =================

async function loadDashboard() {
  const yearSelect = document.getElementById("dashYearSelect").value;
  let start = "2021-03-01";
  let end = "2026-09-30";

  if (yearSelect !== "all") {
    start = `${yearSelect}-01-01`;
    end = `${yearSelect}-12-31`;
  }

  try {
    // 1. Fetch Summary
    const sumRes = await fetch(`${API_BASE}/stats/summary?connection_id=${currentConnectionId}&start=${start}&end=${end}`, {
      headers: getAuthHeader()
    });
    if (sumRes.ok) {
      const s = await sumRes.json();
      renderDashboardSummary(s);
    }

    // 2. Fetch Monthly Rows for Charts
    const mRes = await fetch(`${API_BASE}/stats/monthly?connection_id=${currentConnectionId}&start=${start}&end=${end}`, {
      headers: getAuthHeader()
    });
    if (mRes.ok) {
      const rows = await mRes.json();
      renderDashboardCharts(rows);
    }
  } catch (e) {
    console.error("Failed to load dashboard data:", e);
  }
}

function renderDashboardSummary(data) {
  const tot = data.total || {};
  document.getElementById("kpiSolar").innerHTML = `${fmt(tot.solar_generated)} <span class="unit">kWh</span>`;
  document.getElementById("kpiImport").innerHTML = `${fmt(tot.imported)} <span class="unit">kWh</span>`;
  document.getElementById("kpiExport").innerHTML = `${fmt(tot.exported)} <span class="unit">kWh</span>`;
  document.getElementById("kpiNet").innerHTML = `${fmt(tot.net_energy)} <span class="unit">kWh</span>`;
  document.getElementById("kpiConsumed").innerHTML = `${fmt(tot.total_consumed)} <span class="unit">kWh</span>`;
  document.getElementById("kpiSavings").innerHTML = tot.savings ? `₹ ${fmt(tot.savings)}` : `<span class="unit text-muted">Pending Rate</span>`;

  // Warnings
  const warnBox = document.getElementById("dashWarnings");
  let warningsHtml = "";
  if (data.missing_months && data.missing_months.length > 0) {
    warningsHtml += `<div>⚠️ <strong>Missing Verified Bills (${data.missing_months.length}):</strong> Months with no verified bill: ${data.missing_months.slice(0, 8).join(", ")}${data.missing_months.length > 8 ? "..." : ""}</div>`;
  }
  if (data.missing_rates && data.missing_rates.length > 0) {
    warningsHtml += `<div>⚠️ <strong>Missing Monthly Savings Rates (${data.missing_rates.length}):</strong> Staff savings rate not entered for: ${data.missing_rates.slice(0, 8).join(", ")}${data.missing_rates.length > 8 ? "..." : ""} <button class="btn btn-xs btn-outline" onclick="switchTab('rates')">Enter Rates Now</button></div>`;
  }

  if (warningsHtml) {
    warnBox.innerHTML = warningsHtml;
    warnBox.style.display = "block";
  } else {
    warnBox.style.display = "none";
  }
}

function renderDashboardCharts(rows) {
  // Sort rows chronologically
  rows.sort((a, b) => a.bill_month.localeCompare(b.bill_month));

  const labels = rows.map(r => r.bill_month.slice(0, 7));
  const solarData = rows.map(r => Number(r.energy.solar_generated));
  const importData = rows.map(r => Number(r.energy.imported));
  const exportData = rows.map(r => Number(r.energy.exported));
  const consumedData = rows.map(r => Number(r.energy.total_consumed));
  const savingsData = rows.map(r => r.energy.savings ? Number(r.energy.savings) : 0);

  // 1. Solar vs Consumed
  destroyChart("solarVsConsumed");
  const ctx1 = document.getElementById("chartSolarVsConsumed").getContext("2d");
  charts.solarVsConsumed = new Chart(ctx1, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Solar Generated (kWh)", data: solarData, backgroundColor: "#10b981", borderRadius: 4 },
        { label: "Total Consumed (kWh)", data: consumedData, backgroundColor: "#3b82f6", borderRadius: 4 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "top" } }
    }
  });

  // 2. Import vs Export
  destroyChart("importExport");
  const ctx2 = document.getElementById("chartImportExport").getContext("2d");
  charts.importExport = new Chart(ctx2, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Grid Import (kWh)", data: importData, borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,0.1)", fill: true, tension: 0.3 },
        { label: "Solar Export (kWh)", data: exportData, borderColor: "#f97316", backgroundColor: "rgba(249,115,22,0.1)", fill: true, tension: 0.3 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "top" } }
    }
  });

  // 3. Savings
  destroyChart("savings");
  const ctx3 = document.getElementById("chartSavings").getContext("2d");
  charts.savings = new Chart(ctx3, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Monthly Savings (₹)", data: savingsData, backgroundColor: "#f59e0b", borderRadius: 4 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: (ctx) => `Savings: ₹ ${Number(ctx.parsed.y).toLocaleString()}`
          }
        }
      }
    }
  });

  // 4. Year-over-Year (by month name Jan..Dec)
  destroyChart("yoy");
  const ctx4 = document.getElementById("chartYoY").getContext("2d");
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const byYear = {};

  rows.forEach(r => {
    const d = new Date(r.bill_month);
    const yr = d.getFullYear();
    const mo = d.getMonth();
    if (!byYear[yr]) byYear[yr] = Array(12).fill(null);
    byYear[yr][mo] = Number(r.energy.solar_generated);
  });

  const colors = ["#0284c7", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#14b8a6"];
  const yoyDatasets = Object.keys(byYear).map((yr, idx) => ({
    label: yr,
    data: byYear[yr],
    borderColor: colors[idx % colors.length],
    backgroundColor: "transparent",
    tension: 0.2,
    borderWidth: 2,
  }));

  charts.yoy = new Chart(ctx4, {
    type: "line",
    data: { labels: monthNames, datasets: yoyDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "top" } }
    }
  });
}

function destroyChart(name) {
  if (charts[name]) {
    charts[name].destroy();
    delete charts[name];
  }
}

// ================= TAB 2: BILLS & REVIEW =================

async function loadBills() {
  const status = document.getElementById("billStatusFilter").value;
  const year = document.getElementById("billYearFilter").value;

  let url = `${API_BASE}/bills?connection_id=${currentConnectionId}`;
  if (status !== "all") url += `&status=${status}`;
  if (year !== "all") url += `&year=${year}`;

  try {
    const res = await fetch(url, { headers: getAuthHeader() });
    if (res.ok) {
      currentBills = await res.json();
      renderBillsTable(currentBills);
    }
  } catch (e) {
    console.error("Failed to load bills:", e);
  }
}

function renderBillsTable(bills) {
  const tbody = document.getElementById("billsTableBody");
  const isAdmin = currentUser && currentUser.role === "admin";
  if (!bills || bills.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted" style="padding: 30px;">No bills found for the selected filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = bills.map(b => {
    const e = b.energy || {};
    const hasFlags = b.validation_flags && b.validation_flags.length > 0;
    const errorCount = (b.validation_flags || []).filter(f => f.severity === "error").length;
    const warnCount = (b.validation_flags || []).filter(f => f.severity === "warning").length;

    let flagBadge = `<span class="badge" style="background:#f1f5f9; color:#64748b;">Clean</span>`;
    if (errorCount > 0) {
      flagBadge = `<span class="badge" style="background:#fee2e2; color:#b91c1c;">${errorCount} Error${errorCount>1?'s':''}</span>`;
    } else if (warnCount > 0) {
      flagBadge = `<span class="badge" style="background:#fef3c7; color:#b45309;">${warnCount} Warning${warnCount>1?'s':''}</span>`;
    }

    const rateStr = b.rate_per_unit ? `₹ ${b.rate_per_unit}` : `<span class="text-muted">—</span>`;
    const savingsStr = e.savings ? `₹ ${fmt(e.savings)}` : `<span class="text-muted">—</span>`;

    return `
      <tr>
        <td><strong>${b.bill_month_label || b.bill_month}</strong></td>
        <td class="text-sm">${b.period_start} to ${b.period_end}</td>
        <td><strong>${fmt(e.solar_generated)}</strong></td>
        <td>${fmt(e.imported)}</td>
        <td>${fmt(e.exported)}</td>
        <td>${fmt(e.net_energy)}</td>
        <td><strong>${fmt(e.total_consumed)}</strong></td>
        <td>${rateStr}</td>
        <td><strong>${savingsStr}</strong></td>
        <td><span class="badge badge-${b.status}">${b.status.replace('_', ' ')}</span></td>
        <td>${flagBadge}</td>
        <td>
          <button class="btn btn-xs btn-primary" onclick="openReviewModal(${b.id})">🔍 Review</button>
          ${b.extraction_model === 'historical_backfill' || !b.file_id 
            ? `<span class="badge" style="opacity: 0.6; font-size: 11px;">CSV Import</span>` 
            : `<a href="/bills/${b.id}/file" target="_blank" class="btn btn-xs btn-outline">Original</a>`}
          ${isAdmin ? `<button class="btn btn-xs btn-danger" onclick="deleteBill(${b.id})">🗑️</button>` : ''}
        </td>
      </tr>
    `;
  }).join("");
}

function filterBillsTable() {
  const query = document.getElementById("billSearch").value.toLowerCase();
  const filtered = currentBills.filter(b => 
    (b.bill_month_label && b.bill_month_label.toLowerCase().includes(query)) ||
    (b.bill_month && b.bill_month.includes(query))
  );
  renderBillsTable(filtered);
}

// Review Split-Screen Modal
async function openReviewModal(billId) {
  try {
    const res = await fetch(`${API_BASE}/bills/${billId}`, { headers: getAuthHeader() });
    if (!res.ok) return alert("Failed to fetch bill details");
    selectedBill = await res.json();

    document.getElementById("revModalTitle").textContent = `Review: ${selectedBill.bill_month_label || selectedBill.bill_month} (Version ${selectedBill.version})`;
    const statusBadge = document.getElementById("revStatusBadge");
    statusBadge.textContent = selectedBill.status.replace("_", " ");
    statusBadge.className = `badge badge-${selectedBill.status}`;

    // Pass token as query param so the iframe and download link work without Bearer header
    const _tok = localStorage.getItem("solartrack_token") || "";
    const _tokParam = _tok ? `?token=${encodeURIComponent(_tok)}` : "";

    // Document preview vs Historical Backfill placeholder
    const isBackfill = selectedBill.extraction_model === "historical_backfill" || !selectedBill.file_id;
    const iframe = document.getElementById("docViewerIframe");
    const placeholder = document.getElementById("docViewerPlaceholder");
    const openTabBtn = document.getElementById("revOriginalDownload");

    if (isBackfill) {
      if (iframe) { iframe.style.display = "none"; iframe.src = "about:blank"; }
      if (placeholder) placeholder.style.display = "block";
      if (openTabBtn) openTabBtn.style.display = "none";
    } else {
      if (placeholder) placeholder.style.display = "none";
      if (iframe) {
        iframe.style.display = "block";
        iframe.src = `/bills/${selectedBill.id}/file${_tokParam}`;
      }
      if (openTabBtn) {
        openTabBtn.style.display = "";
        openTabBtn.href = `/bills/${selectedBill.id}/file${_tokParam}`;
      }
    }

    // Role-based editing restrictions: viewers cannot edit inputs or verify
    const isAdmin = currentUser && currentUser.role === "admin";
    document.querySelectorAll("#reviewForm input").forEach(inp => {
      inp.readOnly = !isAdmin;
    });

    // Right: Populate Form
    document.getElementById("editBillId").value = selectedBill.id;
    document.getElementById("editBillMonth").value = selectedBill.bill_month;
    document.getElementById("editPeriodStart").value = selectedBill.period_start;
    document.getElementById("editPeriodEnd").value = selectedBill.period_end;
    document.getElementById("editSolarConst").value = selectedBill.solar_constant;
    document.getElementById("editMeterConst").value = selectedBill.meter_constant;
    document.getElementById("editSolarPrev").value = selectedBill.solar_prev;
    document.getElementById("editSolarPres").value = selectedBill.solar_present;
    document.getElementById("editSolarUnits").value = selectedBill.solar_units_printed;
    document.getElementById("editImportPrev").value = selectedBill.import_prev;
    document.getElementById("editImportPres").value = selectedBill.import_present;
    document.getElementById("editImportUnits").value = selectedBill.import_units_printed;
    document.getElementById("editExportPrev").value = selectedBill.export_prev;
    document.getElementById("editExportPres").value = selectedBill.export_present;
    document.getElementById("editExportUnits").value = selectedBill.export_units_printed;
    document.getElementById("editNetImport").value = selectedBill.net_import_printed || "";
    document.getElementById("editSubMeter").value = selectedBill.sub_meter_units || "";

    // Render Flags
    renderValidationFlags(selectedBill.validation_flags || []);

    // Live Math
    recalculateLiveMath();

    document.getElementById("reviewModal").style.display = "flex";
  } catch (err) {
    alert("Error opening bill: " + err.message);
  }
}

function closeReviewModal() {
  document.getElementById("reviewModal").style.display = "none";
  const iframe = document.getElementById("docViewerIframe");
  if (iframe) iframe.src = "about:blank";
  const placeholder = document.getElementById("docViewerPlaceholder");
  if (placeholder) placeholder.style.display = "none";
  selectedBill = null;
}

function renderValidationFlags(flags) {
  const flagsList = document.getElementById("revFlagsList");
  const flagsBox = document.getElementById("revFlagsBox");
  const verifyBtn = document.getElementById("btnVerifyBill");

  // Remove existing highlight classes from inputs
  document.querySelectorAll("#reviewForm input").forEach(inp => {
    inp.classList.remove("has-flag-error", "has-flag-warning");
  });

  if (!flags || flags.length === 0) {
    flagsBox.style.display = "none";
    if (verifyBtn) verifyBtn.disabled = false;
    return;
  }

  flagsBox.style.display = "block";
  const hasErrors = flags.some(f => f.severity === "error");
  if (verifyBtn) verifyBtn.disabled = hasErrors;

  flagsList.innerHTML = flags.map(f => {
    // Highlight field if matching
    highlightField(f.field, f.severity);
    return `
      <div class="flag-item ${f.severity}">
        <strong>[${f.severity.toUpperCase()}] ${f.code}:</strong> ${f.message}
      </div>
    `;
  }).join("");
}

function highlightField(field, severity) {
  const map = {
    "solar_present": "editSolarPres", "solar_prev": "editSolarPrev", "solar_units_printed": "editSolarUnits",
    "import_present": "editImportPres", "import_prev": "editImportPrev", "import_units_printed": "editImportUnits",
    "export_present": "editExportPres", "export_prev": "editExportPrev", "export_units_printed": "editExportUnits",
    "net_import_printed": "editNetImport", "period_start": "editPeriodStart", "period_end": "editPeriodEnd",
  };
  const inputId = map[field];
  if (inputId) {
    const el = document.getElementById(inputId);
    if (el) el.classList.add(`has-flag-${severity}`);
  }
}

function recalculateLiveMath() {
  const s_prev = parseFloat(document.getElementById("editSolarPrev").value) || 0;
  const s_pres = parseFloat(document.getElementById("editSolarPres").value) || 0;
  const s_const = parseFloat(document.getElementById("editSolarConst").value) || 100;

  const i_prev = parseFloat(document.getElementById("editImportPrev").value) || 0;
  const i_pres = parseFloat(document.getElementById("editImportPres").value) || 0;
  const m_const = parseFloat(document.getElementById("editMeterConst").value) || 2000;

  const e_prev = parseFloat(document.getElementById("editExportPrev").value) || 0;
  const e_pres = parseFloat(document.getElementById("editExportPres").value) || 0;

  const a = (s_pres - s_prev) * s_const;
  const b = (i_pres - i_prev) * m_const;
  const c = (e_pres - e_prev) * m_const;
  const d = b - c;
  const total = a + d;

  const rate = selectedBill && selectedBill.rate_per_unit ? parseFloat(selectedBill.rate_per_unit) : null;
  const savings = rate !== null ? a * rate : null;

  document.getElementById("calcSolar").textContent = `${fmt(a)} kWh`;
  document.getElementById("calcImport").textContent = `${fmt(b)} kWh`;
  document.getElementById("calcExport").textContent = `${fmt(c)} kWh`;
  document.getElementById("calcNet").textContent = `${fmt(d)} kWh`;
  document.getElementById("calcTotal").textContent = `${fmt(total)} kWh`;
  document.getElementById("calcSavings").textContent = savings !== null ? `₹ ${fmt(savings)}` : "Pending Rate";
}

async function saveBillEdits(e) {
  e.preventDefault();
  const id = document.getElementById("editBillId").value;
  const body = {
    bill_month: document.getElementById("editBillMonth").value,
    period_start: document.getElementById("editPeriodStart").value,
    period_end: document.getElementById("editPeriodEnd").value,
    solar_constant: document.getElementById("editSolarConst").value,
    meter_constant: document.getElementById("editMeterConst").value,
    solar_prev: document.getElementById("editSolarPrev").value,
    solar_present: document.getElementById("editSolarPres").value,
    solar_units_printed: document.getElementById("editSolarUnits").value,
    import_prev: document.getElementById("editImportPrev").value,
    import_present: document.getElementById("editImportPres").value,
    import_units_printed: document.getElementById("editImportUnits").value,
    export_prev: document.getElementById("editExportPrev").value,
    export_present: document.getElementById("editExportPres").value,
    export_units_printed: document.getElementById("editExportUnits").value,
    net_import_printed: document.getElementById("editNetImport").value || null,
    sub_meter_units: document.getElementById("editSubMeter").value || null,
  };

  try {
    const res = await fetch(`${API_BASE}/bills/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      return alert("Error saving edits: " + JSON.stringify(err.detail || err));
    }

    const updated = await res.json();
    selectedBill = updated;
    renderValidationFlags(updated.validation_flags || []);
    alert("Edits saved! Bill re-validated successfully.");
    loadBills();
    loadDashboard();
  } catch (err) {
    alert("Connection error: " + err.message);
  }
}

async function verifyCurrentBill() {
  if (!selectedBill) return;
  if (!confirm("Are you sure you want to approve and verify this bill? It will be included in official reports.")) return;

  try {
    const res = await fetch(`${API_BASE}/bills/${selectedBill.id}/verify`, {
      method: "POST",
      headers: getAuthHeader(),
    });

    if (!res.ok) {
      const err = await res.json();
      return alert("Verification blocked: " + (err.detail?.message || JSON.stringify(err.detail)));
    }

    alert("Bill verified successfully!");
    closeReviewModal();
    loadBills();
    loadDashboard();
  } catch (err) {
    alert("Error verifying: " + err.message);
  }
}

async function rejectCurrentBill() {
  if (!selectedBill) return;
  if (!confirm("Are you sure you want to reject this bill? Rejected bills are excluded from reports.")) return;

  try {
    const res = await fetch(`${API_BASE}/bills/${selectedBill.id}/reject`, {
      method: "POST",
      headers: getAuthHeader(),
    });

    if (res.ok) {
      alert("Bill rejected.");
      closeReviewModal();
      loadBills();
      loadDashboard();
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function deleteBill(billId) {
  if (!confirm("Are you sure you want to delete this bill record? This cannot be undone.")) return;
  try {
    const res = await fetch(`${API_BASE}/bills/${billId}`, {
      method: "DELETE",
      headers: getAuthHeader(),
    });
    if (res.ok) {
      alert("Bill deleted.");
      loadBills();
      loadDashboard();
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// Upload Modal
function openUploadModal() {
  document.getElementById("uploadModal").style.display = "flex";
  document.getElementById("uploadProgress").style.display = "none";
  document.getElementById("btnUploadSubmit").disabled = false;
}

function closeUploadModal() {
  document.getElementById("uploadModal").style.display = "none";
}

async function onBillFileSelected(file) {
  if (!file) return;
  const pageOption = document.getElementById("pdfPageOption");
  const pageSelect = document.getElementById("billPageSelect");

  if (file.name.toLowerCase().endsWith(".pdf")) {
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/bills/inspect-pages`, {
        method: "POST",
        headers: getAuthHeader(),
        body: formData,
      });

      if (res.ok) {
        const info = await res.json();
        if (info.page_count > 1) {
          pageSelect.innerHTML = Array.from({ length: info.page_count }, (_, i) => 
            `<option value="${i+1}">Page ${i+1}</option>`
          ).join("");
          pageOption.style.display = "block";
          return;
        }
      }
    } catch (e) {
      console.warn("PDF page inspection failed:", e);
    }
  }
  pageOption.style.display = "none";
}

async function submitBillUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById("billFileInput");
  if (!fileInput.files.length) return alert("Select a file");

  const file = fileInput.files[0];
  const replace = document.getElementById("uploadReplaceCheck").checked;
  const pageSelect = document.getElementById("billPageSelect");
  const page = document.getElementById("pdfPageOption").style.display !== "none" ? pageSelect.value : null;

  const formData = new FormData();
  formData.append("file", file);

  let url = `${API_BASE}/bills/upload?replace=${replace}`;
  if (page) url += `&page=${page}`;

  const progress = document.getElementById("uploadProgress");
  const submitBtn = document.getElementById("btnUploadSubmit");
  progress.style.display = "block";
  submitBtn.disabled = true;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: getAuthHeader(),
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      const msg = typeof err.detail === "string" ? err.detail : (err.detail?.message || JSON.stringify(err.detail));
      alert("Extraction failed: " + msg);
      progress.style.display = "none";
      submitBtn.disabled = false;
      return;
    }

    const bill = await res.json();
    closeUploadModal();
    alert(`Bill extracted successfully for month ${bill.bill_month_label || bill.bill_month}! Opening for staff review.`);
    loadBills();
    loadDashboard();
    openReviewModal(bill.id);
  } catch (err) {
    alert("Upload error: " + err.message);
    progress.style.display = "none";
    submitBtn.disabled = false;
  }
}

// ================= TAB 3: SAVINGS RATES =================

async function loadRates() {
  try {
    const res = await fetch(`${API_BASE}/rates?connection_id=${currentConnectionId}`, {
      headers: getAuthHeader()
    });
    if (res.ok) {
      currentRates = await res.json();
      renderRatesTable(currentRates);
    }
  } catch (e) {
    console.error("Failed to load rates:", e);
  }
}

function renderRatesTable(rates) {
  const tbody = document.getElementById("ratesTableBody");
  const isAdmin = currentUser && currentUser.role === "admin";

  // Hide or show Action column header based on admin role
  const actionTh = document.querySelectorAll("#ratesTable th.admin-only");
  actionTh.forEach(th => th.style.display = isAdmin ? "" : "none");

  if (!rates || rates.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${isAdmin ? 5 : 4}" class="text-center text-muted" style="padding: 24px;">No monthly rates entered yet.</td></tr>`;
    return;
  }

  // Sort descending
  rates.sort((a, b) => b.bill_month.localeCompare(a.bill_month));

  tbody.innerHTML = rates.map(r => `
    <tr>
      <td><strong>${r.bill_month.slice(0, 7)}</strong></td>
      <td><strong>₹ ${r.rate_per_unit}</strong></td>
      <td>${r.entered_by || 'staff'}</td>
      <td><span class="badge badge-verified">Active</span></td>
      ${isAdmin ? `<td><button class="btn btn-xs btn-outline" onclick="editRate('${r.bill_month}', '${r.rate_per_unit}')">Edit Rate</button></td>` : ''}
    </tr>
  `).join("");
}

function openRateModal(monthVal = "", rateVal = "") {
  if (!currentUser || currentUser.role !== "admin") {
    alert("Permission Denied: Only administrators can set or edit savings rates.");
    return;
  }
  document.getElementById("rateMonthInput").value = monthVal || new Date().toISOString().slice(0, 7);
  document.getElementById("rateValueInput").value = rateVal || "";
  document.getElementById("rateModal").style.display = "flex";
}

function closeRateModal() {
  document.getElementById("rateModal").style.display = "none";
}

function editRate(m, r) {
  if (!currentUser || currentUser.role !== "admin") {
    alert("Permission Denied: Only administrators can edit savings rates.");
    return;
  }
  openRateModal(m.slice(0, 7), r);
}

async function submitRate(e) {
  e.preventDefault();
  if (!currentUser || currentUser.role !== "admin") {
    alert("Permission Denied: Only administrators can save savings rates.");
    return;
  }
  const m = document.getElementById("rateMonthInput").value;
  const r = document.getElementById("rateValueInput").value;

  try {
    const res = await fetch(`${API_BASE}/rates`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify({
        connection_id: currentConnectionId,
        bill_month: `${m}-01`,
        rate_per_unit: r,
      }),
    });

    if (res.ok) {
      closeRateModal();
      alert(`Savings rate saved for ${m}: ₹ ${r}/kWh`);
      loadRates();
      loadBills();
      loadDashboard();
    } else {
      const err = await res.json();
      alert("Error: " + JSON.stringify(err.detail));
    }
  } catch (err) {
    alert("Connection error: " + err.message);
  }
}

// ================= TAB 4: REPORTS =================

function adjustReportDates() {
  const freq = document.getElementById("repFrequency").value;
  const startInp = document.getElementById("repStart");
  const endInp = document.getElementById("repEnd");

  if (freq === "inception") {
    startInp.value = "2021-03";
    endInp.value = "2026-09";
  } else if (freq === "yearly") {
    startInp.value = "2025-01";
    endInp.value = "2025-12";
  } else if (freq === "six_monthly") {
    startInp.value = "2025-04";
    endInp.value = "2025-09";
  } else if (freq === "monthly") {
    startInp.value = "2025-03";
    endInp.value = "2025-03";
  }
  generateReportPreview();
}

function toggleAiControls() {
  const check = document.getElementById("repIncludeAI").checked;
  document.getElementById("aiSummaryBox").style.display = check ? "flex" : "none";
  document.getElementById("btnRegenAI").style.display = check ? "inline-flex" : "none";
}

async function generateReportPreview() {
  const sMo = document.getElementById("repStart").value;
  const eMo = document.getElementById("repEnd").value;
  const start = `${sMo}-01`;
  const end = `${eMo}-28`;

  const paper = document.getElementById("reportPaper");
  paper.innerHTML = `<div class="text-center" style="padding: 40px;"><div class="spinner"></div><p>Rendering report preview...</p></div>`;

  try {
    const [sumRes, mRes] = await Promise.all([
      fetch(`${API_BASE}/stats/summary?connection_id=${currentConnectionId}&start=${start}&end=${end}`, { headers: getAuthHeader() }),
      fetch(`${API_BASE}/stats/monthly?connection_id=${currentConnectionId}&start=${start}&end=${end}`, { headers: getAuthHeader() }),
    ]);

    if (!sumRes.ok || !mRes.ok) {
      paper.innerHTML = `<div class="text-center text-muted" style="padding: 40px;">No verified data available for this range. Ensure bills are verified.</div>`;
      return;
    }

    const summary = await sumRes.json();
    const months = await mRes.json();

    if (months.length === 0) {
      paper.innerHTML = `<div class="text-center text-muted" style="padding: 40px;">No verified bills in range.</div>`;
      return;
    }

    // Generate AI Summary if empty
    const aiTextEl = document.getElementById("aiSummaryText");
    if (!aiTextEl.value || aiTextEl.value.includes("Generating")) {
      generateAiSummaryOnly(summary);
    }

    // Render Paper Layout matching faculty format
    let html = `
      <div class="paper-title">
        Details of Energy Generated from Solar Roof Top System from ${sMo} to ${eMo}
      </div>
    `;

    // AI Summary in report
    const includeAi = document.getElementById("repIncludeAI").checked;
    if (includeAi && aiTextEl.value) {
      html += `
        <div style="background:#f8fafc; border:1px solid #94a3b8; padding:12px; margin-bottom:16px; border-radius:4px; font-size:11px; line-height:1.4;">
          <strong>Executive Summary & Performance Analysis:</strong><br/>
          ${aiTextEl.value.replace(/\n/g, '<br/>')}
        </div>
      `;
    }

    // Period Summary if multi-month
    if (months.length > 1) {
      const tot = summary.total;
      html += `
        <table class="paper-table" style="background:#f1f5f9; font-weight:bold; margin-bottom:20px;">
          <tr><td colspan="2" style="background:#e2e8f0;">Period Aggregated Total (${months.length} Months)</td></tr>
          <tr><td>(a) Total Solar Generation</td><td>${fmt(tot.solar_generated)} Units</td></tr>
          <tr><td>(b) Total Energy Imported from MESCOM</td><td>${fmt(tot.imported)} Units</td></tr>
          <tr><td>(c) Total Exported to MESCOM</td><td>${fmt(tot.exported)} Units</td></tr>
          <tr><td>(d) Net Energy Import from MESCOM [(b)-(c)]</td><td>${fmt(tot.net_energy)} Units</td></tr>
          <tr><td>Total Electrical Energy Consumption [(a)+(d)]</td><td>${fmt(tot.total_consumed)} Units</td></tr>
          <tr><td>Total Financial Savings</td><td>${tot.savings ? 'Rs ' + fmt(tot.savings) : 'Pending Rate'}</td></tr>
        </table>
      `;
    }

    // Monthly Tables
    months.forEach(m => {
      const d = new Date(m.bill_month);
      const mName = d.toLocaleString('default', { month: 'long', year: 'numeric' });
      const e = m.energy;
      const rate = m.rate_per_unit ? `Rs ${m.rate_per_unit}` : `pending`;

      html += `
        <div class="paper-month-title">${mName}:</div>
        <table class="paper-table">
          <tr><td>(a) Solar Generation</td><td>${fmt(e.solar_generated)} Units</td></tr>
          <tr><td>(b) Energy Imported from MESCOM</td><td>${fmt(e.imported)} Units</td></tr>
          <tr><td>(c) Exported to MESCOM</td><td>${fmt(e.exported)} Units</td></tr>
          <tr><td>(d) Net Energy Import from MESCOM [(b)-(c) ]</td><td>${fmt(e.net_energy)} Units</td></tr>
          <tr><td>Total Electrical Energy Consumption [(a)+(d)]</td><td>${fmt(e.total_consumed)} Units</td></tr>
          <tr><td>Savings (@ rate of ${rate} per unit of energy generated from solar unit)</td><td>${e.savings ? 'Rs ' + fmt(e.savings) : 'Pending Rate'}</td></tr>
        </table>
      `;
    });

    paper.innerHTML = html;
  } catch (err) {
    paper.innerHTML = `<div class="text-center text-muted" style="padding: 40px;">Error rendering report: ${err.message}</div>`;
  }
}

async function generateAiSummaryOnly(summaryData = null) {
  const sMo = document.getElementById("repStart").value;
  const eMo = document.getElementById("repEnd").value;
  const aiStatus = document.getElementById("aiGuardrailStatus");
  const aiText = document.getElementById("aiSummaryText");

  aiStatus.textContent = "Validating numbers against calculated data...";
  aiStatus.className = "guardrail-status";

  if (!summaryData) {
    try {
      const res = await fetch(`${API_BASE}/stats/summary?connection_id=${currentConnectionId}&start=${sMo}-01&end=${eMo}-28`, {
        headers: getAuthHeader()
      });
      summaryData = await res.json();
    } catch (e) {
      return;
    }
  }

  const tot = summaryData.total || {};
  const payload = {
    start_str: `${sMo}-01`,
    end_str: `${eMo}-28`,
    solar_generated: tot.solar_generated,
    imported: tot.imported,
    exported: tot.exported,
    net_energy: tot.net_energy,
    total_consumed: tot.total_consumed,
    savings: tot.savings,
    months_included: summaryData.months_included,
  };

  try {
    const res = await fetch(`${API_BASE}/reports/ai-summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const out = await res.json();
      aiText.value = out.summary;
      if (out.guardrail_passed) {
        aiStatus.textContent = `✓ Guardrail Passed: All numbers verified against calculated energy facts (${out.source}).`;
        aiStatus.className = "guardrail-status pass";
      } else {
        aiStatus.textContent = `⚠️ Guardrail Alert: Strict fallback applied. Hallucinated figures prevented.`;
        aiStatus.className = "guardrail-status fail";
      }
    }
  } catch (err) {
    aiStatus.textContent = "Failed to generate AI summary.";
  }
}

function downloadReportPdf() {
  const sMo = document.getElementById("repStart").value;
  const eMo = document.getElementById("repEnd").value;
  const includeAi = document.getElementById("repIncludeAI").checked;
  const token = localStorage.getItem("solartrack_token") || "";

  const url = `${API_BASE}/reports/download?connection_id=${currentConnectionId}&start=${sMo}-01&end=${eMo}-28&include_ai=${includeAi}&token=${encodeURIComponent(token)}`;
  window.open(url, "_blank");
}

// ================= TAB 5: BACKFILL =================

function setupDragAndDrop() {
  const zone = document.getElementById("backfillDropZone");
  if (!zone) return;

  ["dragenter", "dragover"].forEach(evt => {
    zone.addEventListener(evt, e => { e.preventDefault(); zone.style.background = "#f1f5f9"; });
  });
  ["dragleave", "drop"].forEach(evt => {
    zone.addEventListener(evt, e => { e.preventDefault(); zone.style.background = "#f8fafc"; });
  });

  zone.addEventListener("drop", e => {
    const files = e.dataTransfer.files;
    if (files.length) handleBackfillFile(files[0]);
  });
}

function downloadBackfillTemplate() {
  window.open(`${API_BASE}/backfill/template`, "_blank");
}

async function handleBackfillFile(file) {
  if (!file) return;
  const statusBox = document.getElementById("customBackfillStatus");
  statusBox.style.display = "block";
  statusBox.className = "import-result-box";
  statusBox.textContent = `Importing ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`${API_BASE}/backfill/import`, {
      method: "POST",
      headers: getAuthHeader(),
      body: formData,
    });

    const data = await res.json();
    if (res.ok) {
      statusBox.innerHTML = `
        <strong>✓ Import Complete:</strong> ${data.created_or_updated_bills} bills created/updated, ${data.rates_updated} monthly rates stored.
        ${data.errors.length ? `<br/><span style="color:#b91c1c;">Errors in ${data.errors.length} rows</span>` : ''}
      `;
      loadDashboard();
      loadBills();
    } else {
      statusBox.innerHTML = `<strong>✕ Import Error:</strong> ${JSON.stringify(data.detail)}`;
    }
  } catch (err) {
    statusBox.textContent = `Error: ${err.message}`;
  }
}

async function importBundledHistoricalData() {
  const resultBox = document.getElementById("bundledImportResult");
  resultBox.style.display = "block";
  resultBox.className = "import-result-box";
  resultBox.textContent = "Loading bundled 67-month verified faculty dataset...";

  try {
    // Fetch bundled CSV
    const csvRes = await fetch("/static/../data/historical_records_2021_2026.csv");
    let blob;
    if (csvRes.ok) {
      blob = await csvRes.blob();
    } else {
      // Direct sample import if static fetch path differs
      resultBox.textContent = "Requesting server to backfill bundled records...";
    }

    const file = new File([blob], "faculty_records_2021_2026.csv", { type: "text/csv" });
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/backfill/import`, {
      method: "POST",
      headers: getAuthHeader(),
      body: formData,
    });

    const data = await res.json();
    if (res.ok) {
      resultBox.innerHTML = `
        <strong>✓ 67 Months Successfully Backfilled:</strong> All records from March 2021 to September 2026 have been verified and loaded with approved rates!
      `;
      resultBox.style.background = "#dcfce7";
      resultBox.style.color = "#15803d";
      loadDashboard();
      loadBills();
      loadRates();
    } else {
      resultBox.textContent = "Error: " + JSON.stringify(data.detail);
    }
  } catch (err) {
    resultBox.textContent = "Failed to import bundled dataset: " + err.message;
  }
}

// ================= TAB 6: USER MANAGEMENT =================

async function loadUsers() {
  try {
    const res = await fetch(`${API_BASE}/users`, { headers: getAuthHeader() });
    if (res.ok) {
      const users = await res.json();
      const tbody = document.getElementById("usersTableBody");
      tbody.innerHTML = users.map(u => `
        <tr>
          <td>${u.id}</td>
          <td><strong>${u.username}</strong></td>
          <td>${u.full_name || '—'}</td>
          <td><span class="badge ${u.role === 'admin' ? 'badge-verified' : 'badge-extracted'}">${u.role}</span></td>
          <td><span class="badge ${u.is_active ? 'badge-verified' : 'badge-rejected'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
          <td class="text-sm">${u.created_at ? u.created_at.slice(0, 10) : '—'}</td>
          <td>
            <button class="btn btn-xs btn-outline" onclick="toggleUserActive(${u.id}, ${!u.is_active})">
              ${u.is_active ? 'Deactivate' : 'Activate'}
            </button>
            <button class="btn btn-xs btn-danger" onclick="deleteUser(${u.id})">Delete</button>
          </td>
        </tr>
      `).join("");
    }
  } catch (e) {
    console.error("Failed to load users:", e);
  }
}

function openCreateUserModal() {
  document.getElementById("userModal").style.display = "flex";
}

function closeUserModal() {
  document.getElementById("userModal").style.display = "none";
}

async function submitCreateUser(e) {
  e.preventDefault();
  const body = {
    username: document.getElementById("newUsername").value.trim(),
    full_name: document.getElementById("newFullName").value.trim(),
    password: document.getElementById("newPassword").value,
    role: document.getElementById("newRole").value,
  };

  try {
    const res = await fetch(`${API_BASE}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      closeUserModal();
      alert(`User '${body.username}' created!`);
      loadUsers();
    } else {
      const err = await res.json();
      alert("Error: " + (err.detail || JSON.stringify(err)));
    }
  } catch (err) {
    alert("Connection error: " + err.message);
  }
}

async function toggleUserActive(userId, activeState) {
  try {
    const res = await fetch(`${API_BASE}/users/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify({ is_active: activeState }),
    });
    if (res.ok) loadUsers();
    else {
      const err = await res.json();
      alert(err.detail || "Error");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function deleteUser(userId) {
  if (!confirm("Are you sure you want to delete this user?")) return;
  try {
    const res = await fetch(`${API_BASE}/users/${userId}`, {
      method: "DELETE",
      headers: getAuthHeader(),
    });
    if (res.ok) loadUsers();
    else {
      const err = await res.json();
      alert(err.detail || "Error");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// ================= TAB 7: BACKUPS & AUDIT =================

async function loadBackupsAndAudit() {
  loadBackupsList();
  loadAuditLog();
}

async function loadBackupsList() {
  try {
    const res = await fetch(`${API_BASE}/backup/list`, { headers: getAuthHeader() });
    if (res.ok) {
      const backups = await res.json();
      const list = document.getElementById("backupsList");
      if (!backups.length) {
        list.innerHTML = `<li class="text-muted">No backups created yet.</li>`;
        return;
      }
      list.innerHTML = backups.map(b => `
        <li>
          <div>
            <strong>${b.filename}</strong><br/>
            <small class="text-muted">${b.created_at.slice(0, 19).replace('T', ' ')} (${(b.size_bytes / 1024).toFixed(1)} KB)</small>
          </div>
          <a href="/backup/download?filename=${encodeURIComponent(b.filename)}" class="btn btn-xs btn-outline">Download Zip</a>
        </li>
      `).join("");
    }
  } catch (e) {
    console.error("Failed to load backups:", e);
  }
}

async function createBackup() {
  try {
    const res = await fetch(`${API_BASE}/backup/create`, {
      method: "POST",
      headers: getAuthHeader(),
    });
    if (res.ok) {
      const d = await res.json();
      alert(`Backup created successfully: ${d.backup_file}`);
      loadBackupsList();
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function loadAuditLog() {
  try {
    const res = await fetch(`${API_BASE}/audit-log?limit=50`, { headers: getAuthHeader() });
    if (res.ok) {
      const logs = await res.json();
      const tbody = document.getElementById("auditTableBody");
      tbody.innerHTML = logs.map(l => `
        <tr>
          <td>${l.created_at.slice(0, 19).replace('T', ' ')}</td>
          <td><strong>${l.user}</strong></td>
          <td><span class="badge badge-extracted">${l.action}</span></td>
          <td>${l.bill_id || '—'}</td>
          <td>${l.field_name || ''} ${l.old_value ? `(${l.old_value} → ${l.new_value})` : (l.new_value || '')}</td>
        </tr>
      `).join("");
    }
  } catch (e) {
    console.error("Failed to load audit log:", e);
  }
}

// Helpers
function fmt(num) {
  if (num === null || num === undefined) return "—";
  const n = parseFloat(num);
  if (isNaN(n)) return num;
  return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
