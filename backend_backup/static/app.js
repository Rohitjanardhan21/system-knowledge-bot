/* ============================================================
   UTILITIES
============================================================ */

function qs(id) {
  return document.getElementById(id);
}

/* ============================================================
   FORCE WIZARD CLOSED ON LOAD
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const overlay = qs("wizardOverlay");
  if (overlay) overlay.classList.add("hidden");
});

/* ============================================================
   THEME + ACCENT
============================================================ */

const themeToggle = qs("themeToggle");
const accentInput = qs("accentInput");

if (themeToggle) {
  if (localStorage.getItem("skb-theme") === "light") {
    document.body.classList.add("light");
    themeToggle.textContent = "☀";
  }

  themeToggle.onclick = () => {
    const light = document.body.classList.toggle("light");
    localStorage.setItem("skb-theme", light ? "light" : "dark");
    themeToggle.textContent = light ? "☀" : "🌙";
  };
}

if (accentInput) {
  const savedAccent = localStorage.getItem("skb-accent");
  if (savedAccent) {
    document.documentElement.style.setProperty("--accent", savedAccent);
    accentInput.value = savedAccent;
  }

  accentInput.oninput = e => {
    document.documentElement.style.setProperty("--accent", e.target.value);
    localStorage.setItem("skb-accent", e.target.value);
  };
}

/* ============================================================
   ALERT CENTER
============================================================ */

async function pollAlerts() {
  try {
    const r = await fetch("/alerts/active");
    renderAlerts(await r.json());
  } catch {}
}

setInterval(pollAlerts, 6000);
pollAlerts();

function renderAlerts(alerts) {
  const list = qs("alertList");
  const count = qs("alertCount");

  if (!list || !count) return;

  list.innerHTML = "";
  count.textContent = alerts.length;

  alerts.forEach(a => {
    const row = document.createElement("div");
    row.className = `alert-row ${a.severity}`;

    row.innerHTML = `
      <div><strong>${a.source}</strong> — ${a.message}</div>
      <small>${new Date(a.created_at).toLocaleTimeString()}</small>
    `;

    row.onclick = async () => {
      await fetch(`/alerts/ack/${a.id}`, { method: "POST" });
      pollAlerts();
    };

    list.appendChild(row);
  });
}

/* ============================================================
   GAUGES
============================================================ */

function createGauge(id) {
  const svg = qs(id);
  if (!svg) return null;

  const r = 55;
  const c = 2 * Math.PI * r;

  svg.setAttribute("viewBox", "0 0 140 140");
  svg.innerHTML = `
    <circle class="bg" cx="70" cy="70" r="${r}"/>
    <circle class="fg" cx="70" cy="70" r="${r}"
      stroke-dasharray="${c}"
      stroke-dashoffset="${c}"/>
    <text x="50%" y="50%">0%</text>
  `;

  return { fg: svg.querySelector(".fg"), txt: svg.querySelector("text"), c };
}

function updateGauge(g, v) {
  if (!g) return;

  const pct = Math.min(100, Math.max(0, v));
  const off = g.c * (1 - pct / 100);

  g.fg.style.strokeDashoffset = off;
  g.txt.textContent = pct + "%";

  g.fg.style.stroke =
    pct > 85 ? "var(--red)" :
    pct > 70 ? "var(--yellow)" :
    "var(--green)";
}

const cpuGauge = createGauge("cpuGauge");
const memGauge = createGauge("memGauge");
const diskGauge = createGauge("diskGauge");
const riskGauge = createGauge("riskGauge");
const workloadGauge = createGauge("workloadGauge");

/* ============================================================
   NETWORK CHART
============================================================ */

const NET_POINTS = 40;

const netData = {
  rx: Array(NET_POINTS).fill(0),
  tx: Array(NET_POINTS).fill(0)
};

const netCanvas = qs("netChart");
const netCtx = netCanvas ? netCanvas.getContext("2d") : null;

function pushNetSample(rx, tx) {
  netData.rx.push(rx);
  netData.tx.push(tx);

  if (netData.rx.length > NET_POINTS) {
    netData.rx.shift();
    netData.tx.shift();
  }
}

function drawNetworkChart() {
  if (!netCtx) return;

  const w = netCanvas.width;
  const h = netCanvas.height;

  netCtx.clearRect(0, 0, w, h);

  const maxVal = Math.max(...netData.rx, ...netData.tx, 10);

  drawNetLine(netData.rx, maxVal, "#3b82f6");
  drawNetLine(netData.tx, maxVal, "#22c55e");
}

function drawNetLine(series, max, color) {
  const w = netCanvas.width;
  const h = netCanvas.height;

  netCtx.strokeStyle = color;
  netCtx.lineWidth = 2;
  netCtx.beginPath();

  series.forEach((v, i) => {
    const x = (w / (NET_POINTS - 1)) * i;
    const y = h - (v / max) * h;
    if (i === 0) netCtx.moveTo(x, y);
    else netCtx.lineTo(x, y);
  });

  netCtx.stroke();
}

/* ============================================================
   SUMMARY POLL
============================================================ */

async function pollSummary() {
  try {
    const r = await fetch("/system/summary");
    const d = await r.json();

    updateGauge(cpuGauge, d.cpu?.usage || 0);
    updateGauge(memGauge, d.memory?.used_pct || 0);
    updateGauge(diskGauge, d.disk?.fill_pct || 0);

    pushNetSample(d.network?.rx_kbps || 0, d.network?.tx_kbps || 0);
    drawNetworkChart();

    if (d.forecast && typeof d.forecast === "object") {

      updateGauge(riskGauge, d.forecast.risk_score || 0);
      updateGauge(workloadGauge, d.workload_score || 0);

      qs("forecastStrip") &&
        (qs("forecastStrip").textContent =
          `Primary risk: ${d.forecast.primary_risk || "unknown"}`);

      qs("timeEstimate") &&
        (qs("timeEstimate").textContent =
          d.forecast.time_to_constraint_min
            ? `~${d.forecast.time_to_constraint_min} minutes`
            : "N/A");

      qs("futurePosture") &&
        (qs("futurePosture").textContent =
          (d.forecast.likely_posture || "unknown").toUpperCase());
    }

  } catch (e) {
    console.warn("summary poll failed", e);
  }
}

setInterval(pollSummary, 4000);
pollSummary();

/* ============================================================
   FINAL WIZARD SYSTEM — GUARANTEED CLOSE
============================================================ */

document.addEventListener("DOMContentLoaded", () => {

  const overlay = qs("wizardOverlay");
  const nextBtn = qs("wizardNext");
  const prevBtn = qs("wizardPrev");

  if (!overlay || !nextBtn) return;

  overlay.classList.add("hidden");

  let step = 0;

  async function drawWizard() {

    const box = qs("wizardStep");
    if (!box) return;

    prevBtn.style.display = step === 0 ? "none" : "inline-block";

    if (step === 0) {
      const r = await fetch("/service/status");
      const d = await r.json();
      box.innerHTML = `
        <h3>System Detected</h3>
        <p>OS: ${d.os}</p>
        <p>Collector running: ${d.collector_running}</p>
      `;
      nextBtn.textContent = "Next";
    }

    if (step === 1) {
      box.innerHTML = `
        <h3>Autostart</h3>
        <button id="autoOn">Enable</button>
        <button id="autoOff">Disable</button>
      `;
      nextBtn.textContent = "Next";

      qs("autoOn").onclick = () => toggleAutostart(true);
      qs("autoOff").onclick = () => toggleAutostart(false);
    }

    if (step === 2) {
      box.innerHTML = `<h3>Tray</h3><p>Tray enabled.</p>`;
      nextBtn.textContent = "Next";
    }

    if (step === 3) {
      box.innerHTML = `
        <h3>Diagnostics</h3>
        <button id="restartBtn">Restart Collector</button>
      `;
      nextBtn.textContent = "Next";
      qs("restartBtn").onclick = restartCollector;
    }

    if (step === 4) {
      box.innerHTML = `<h3>Finish</h3><p>Setup complete.</p>`;
      nextBtn.textContent = "Close";
    }
  }

  nextBtn.onclick = () => {

    if (step >= 4) {
      closeWizard();
      step = 0;
      return;
    }

    step++;
    drawWizard();
  };

  prevBtn.onclick = () => {
    step = Math.max(0, step - 1);
    drawWizard();
  };

  window.openWizard = () => {
    step = 0;
    overlay.classList.remove("hidden");
    overlay.style.display = "flex";
    drawWizard();
  };

  window.closeWizard = () => {
    overlay.classList.add("hidden");
    overlay.style.display = "none";
  };
});

/* ============================================================
   SERVICE ACTIONS
============================================================ */

async function restartCollector() {
  await fetch("/service/collector/restart", { method: "POST" });
  alert("Restart issued.");
}

async function toggleAutostart(v) {
  await fetch(`/service/autostart/${v}`, { method: "POST" });
  alert("Autostart updated.");
}
