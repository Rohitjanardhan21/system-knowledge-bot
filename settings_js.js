
// ════════════════════════════════════════════════════════════
//  CVIS Settings Panel JS
//  Paste into the <script> block in frontend/index.html
// ════════════════════════════════════════════════════════════

let _settingsData = {};
let _settingsDirty = {};

function openSettings() {
  document.getElementById('settings-overlay').classList.add('open');
  loadSettings();
  loadSystemInfo();
}

function closeSettings() {
  document.getElementById('settings-overlay').classList.remove('open');
  _settingsDirty = {};
  document.getElementById('settings-save-status').textContent = '';
}

function switchSettingsTab(name, btn) {
  document.querySelectorAll('.spanel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.stab').forEach(b => b.classList.remove('active'));
  document.getElementById('spanel-' + name).classList.add('active');
  btn.classList.add('active');
}

// ── Load settings from backend ──────────────────────────────
async function loadSettings() {
  try {
    const data = await fetch_(API + '/settings');
    _settingsData = data;

    // Text/number inputs
    const textKeys = [
      'alert_email','smtp_host','smtp_port','smtp_user','smtp_pass',
      'alert_cooldown_s','poll_interval_s','autosave_interval_s',
      'startup_grace_s','blackbox_retention_min','refresh_rate_ms',
    ];
    textKeys.forEach(k => {
      const el = document.getElementById('s-' + k);
      if (el && data[k] != null) el.value = data[k];
    });

    // Selects
    ['alert_min_severity','auto_remediation_mode'].forEach(k => {
      const el = document.getElementById('s-' + k);
      if (el && data[k] != null) el.value = data[k];
    });

    // Toggles
    const togKeys = [
      'email_alerts_enabled','desktop_notifications','weekly_report_enabled',
      'show_forecast','show_premortem','show_blackbox',
      'show_processes','show_correlations','show_ml_signals',
    ];
    togKeys.forEach(k => {
      const el = document.getElementById('tog-' + k);
      if (el) el.classList.toggle('on', !!data[k]);
    });

    // Sliders
    const sliderKeys = [
      ['threshold_cpu', '%'],
      ['threshold_memory', '%'],
      ['threshold_disk', '%'],
      ['threshold_anomaly', ''],
      ['threshold_health', ''],
    ];
    sliderKeys.forEach(([k, unit]) => {
      const sl = document.getElementById('sl-' + k);
      const vl = document.getElementById('slv-' + k);
      if (sl && data[k] != null) {
        sl.value = data[k];
        if (vl) vl.textContent = data[k] + unit;
      }
    });
  } catch(e) {
    showSettingsMsg('notifications', 'Could not load settings — backend offline.', false);
  }
}

// ── Collect current form values ─────────────────────────────
function collectSettings() {
  const out = {};

  // Text/number
  const textKeys = [
    'alert_email','smtp_host','smtp_user','smtp_pass',
    'alert_cooldown_s','poll_interval_s','autosave_interval_s',
    'startup_grace_s','blackbox_retention_min','refresh_rate_ms',
  ];
  textKeys.forEach(k => {
    const el = document.getElementById('s-' + k);
    if (el) out[k] = el.type === 'number' ? Number(el.value) : el.value;
  });
  // smtp_port separately
  const portEl = document.getElementById('s-smtp_port');
  if (portEl) out['smtp_port'] = Number(portEl.value);

  // Selects
  ['alert_min_severity','auto_remediation_mode'].forEach(k => {
    const el = document.getElementById('s-' + k);
    if (el) out[k] = el.value;
  });

  // Toggles
  const togKeys = [
    'email_alerts_enabled','desktop_notifications','weekly_report_enabled',
    'show_forecast','show_premortem','show_blackbox',
    'show_processes','show_correlations','show_ml_signals',
  ];
  togKeys.forEach(k => {
    const el = document.getElementById('tog-' + k);
    if (el) out[k] = el.classList.contains('on');
  });

  // Sliders
  ['threshold_cpu','threshold_memory','threshold_disk','threshold_anomaly','threshold_health'].forEach(k => {
    const el = document.getElementById('sl-' + k);
    if (el) out[k] = parseFloat(el.value);
  });

  return out;
}

// ── Save settings ────────────────────────────────────────────
async function saveSettings() {
  const payload = collectSettings();
  const statusEl = document.getElementById('settings-save-status');
  statusEl.textContent = 'Saving…';
  statusEl.style.color = 'var(--muted)';
  try {
    await fetch(API + '/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify(payload),
    });
    statusEl.textContent = '✓ Saved — changes applied immediately';
    statusEl.style.color = 'var(--green)';
    setTimeout(() => { statusEl.textContent = ''; }, 4000);
  } catch(e) {
    statusEl.textContent = '✗ Save failed — check backend';
    statusEl.style.color = 'var(--red)';
  }
}

// ── Toggle helper ────────────────────────────────────────────
function toggleSetting(key, el) {
  el.classList.toggle('on');
}

// ── Slider helper ────────────────────────────────────────────
function updateSlider(key, value, unit) {
  const vl = document.getElementById('slv-' + key);
  if (vl) vl.textContent = value + unit;
}

// ── Test email ───────────────────────────────────────────────
async function testEmail() {
  showSettingsMsg('notifications', 'Sending test…', true, true);
  try {
    const r = await fetch(API + '/settings/test-email', {
      method: 'POST', headers: { 'X-API-Key': apiKey }
    });
    const d = await r.json();
    showSettingsMsg('notifications', d.message, d.success);
  } catch {
    showSettingsMsg('notifications', 'Request failed — backend offline.', false);
  }
}

// ── Weekly report ────────────────────────────────────────────
async function sendWeeklyReport() {
  // Save current SMTP settings first
  await saveSettings();
  showSettingsMsg('notifications', 'Sending report…', true, true);
  try {
    const r = await fetch(API + '/settings/send-report', {
      method: 'POST', headers: { 'X-API-Key': apiKey }
    });
    const d = await r.json();
    showSettingsMsg('notifications', d.message, d.success);
  } catch {
    showSettingsMsg('notifications', 'Request failed — backend offline.', false);
  }
}

// ── Reset thresholds ─────────────────────────────────────────
function resetThresholds() {
  const defaults = { threshold_cpu:80, threshold_memory:80, threshold_disk:85, threshold_anomaly:0.70, threshold_health:400 };
  const units    = { threshold_cpu:'%', threshold_memory:'%', threshold_disk:'%', threshold_anomaly:'', threshold_health:'' };
  Object.entries(defaults).forEach(([k, v]) => {
    const sl = document.getElementById('sl-' + k);
    const vl = document.getElementById('slv-' + k);
    if (sl) { sl.value = v; if (vl) vl.textContent = v + (units[k]||''); }
  });
  showSettingsMsg('thresholds', 'Thresholds reset to defaults — click Save to apply.', true);
}

// ── Reset ALL settings ───────────────────────────────────────
async function resetAllSettings() {
  if (!confirm('Reset ALL settings to defaults? This cannot be undone.')) return;
  try {
    await fetch(API + '/settings/reset', { method: 'POST', headers: { 'X-API-Key': apiKey } });
    await loadSettings();
    showSettingsMsg('sysinfo', '✓ All settings reset to defaults.', true);
  } catch {
    showSettingsMsg('sysinfo', 'Reset failed — backend offline.', false);
  }
}

// ── Export incidents ─────────────────────────────────────────
async function exportIncidents() {
  try {
    const incidents = await fetch_(API + '/cognitive/incidents');
    const blob = new Blob([JSON.stringify(incidents, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `cvis-incidents-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
    showSettingsMsg('sysinfo', `Exported ${incidents.length} incidents.`, true);
  } catch {
    showSettingsMsg('sysinfo', 'Export failed — backend offline.', false);
  }
}

// ── Load system info tab ─────────────────────────────────────
async function loadSystemInfo() {
  try {
    const [h, dna] = await Promise.all([
      fetch_(API + '/health'),
      fetch_(API + '/cognitive/dna').catch(() => null),
    ]);
    const siRedis = document.getElementById('si-redis');
    const siDb    = document.getElementById('si-db');
    const siSteps = document.getElementById('si-steps');
    const siAlerts= document.getElementById('si-alerts');
    const siPatt  = document.getElementById('si-patterns');
    if (siRedis) { siRedis.textContent = h.redis?.available ? 'UP' : 'IN-MEM'; siRedis.style.color = h.redis?.available ? 'var(--green)' : 'var(--muted)'; }
    if (siDb)    { siDb.textContent    = h.db?.available    ? 'UP' : '—';       siDb.style.color    = h.db?.available    ? 'var(--green)' : 'var(--muted)'; }
    if (siSteps) siSteps.textContent   = (h.steps_lstm||0) + (h.steps_vae||0);
    if (siAlerts) siAlerts.textContent = h.db?.alerts || '—';
    if (siPatt && dna)  siPatt.textContent  = dna.patterns || 0;
  } catch {}
}

// ── Msg helper ───────────────────────────────────────────────
function showSettingsMsg(panel, text, ok, spinner) {
  const el = document.getElementById('smsg-' + panel);
  if (!el) return;
  el.textContent = (spinner ? '◌ ' : '') + text;
  el.className   = 'smsg ' + (ok ? 'ok' : 'err');
  el.style.display = 'block';
  if (!spinner) setTimeout(() => { el.style.display = 'none'; }, 5000);
}
