<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>System Knowledge Bot — UI Truth</title>

<style>
body {
  font-family: monospace;
  background: #05070b;
  color: #d1d5db;
  padding: 20px;
}

h1 {
  font-size: 18px;
  margin-bottom: 10px;
}

.section {
  margin-top: 18px;
}

.badge {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
}

.ok { background:#052e16; color:#22c55e; }
.warn { background:#422006; color:#eab308; }
.error { background:#450a0a; color:#ef4444; }

pre {
  background: #020617;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
}
</style>
</head>

<body>

<h1>System Knowledge Bot — UI Truth Page</h1>

<div id="statusLine"></div>

<div class="section">
  <h3>/system/health</h3>
  <pre id="out">Loading…</pre>
</div>

<script>

async function loadTruth() {

  try {

    const res = await fetch("/system/health");
    const data = await res.json();

    document.getElementById("out").textContent =
      JSON.stringify(data, null, 2);

    renderStatus(data);

  } catch (err) {

    document.getElementById("out").textContent =
      err.toString();

    document.getElementById("statusLine").innerHTML =
      `<span class="badge error">BACKEND OFFLINE</span>`;
  }
}

function renderStatus(data) {

  const el = document.getElementById("statusLine");

  let cls = "ok";
  if (data.overall_health === "stale") cls = "warn";
  if (data.overall_health === "degraded") cls = "warn";
  if (data.overall_health === "error") cls = "error";

  el.innerHTML = `
    Overall Health:
    <span class="badge ${cls}">
      ${data.overall_health}
    </span>
    | Facts age: ${data.facts_age_seconds}s
  `;
}

setInterval(loadTruth, 5000);
loadTruth();

</script>

</body>
</html>
