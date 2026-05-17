"""
Synapse Master Fix Script
Renames CVIS -> Synapse and fixes all demo issues in one shot.
Run from ~/system-knowledge-bot/
"""
import os, re

# ── 1. Fix frontend/index.html ────────────────────────────────────────────────
print("Fixing frontend/index.html...")
c = open('frontend/index.html').read()

# Rename CVIS -> Synapse in visible text
c = c.replace('CVIS <span>/ Cognitive</span>', 'Synapse <span>/ AI</span>')
c = c.replace('CVIS · Cognitive AIOps', 'Synapse · AI System Monitor')
c = c.replace('CVIS / Cognitive', 'Synapse / AI')
c = c.replace('CVIS / Simple', 'Synapse / Simple')
c = c.replace('CVIS v9 AIOps Backend', 'Synapse Backend')
c = c.replace('Cognitive AIOps', 'Synapse AI')
c = c.replace('Cognitive Assistant', 'ARIA — Synapse Intelligence')
c = c.replace('CVIS is', 'Synapse is')
c = c.replace('CVIS has', 'Synapse has')
c = c.replace('CVIS will', 'Synapse will')
c = c.replace('CVIS caught', 'Synapse caught')
c = c.replace('CVIS detected', 'Synapse detected')
c = c.replace('CVIS predicts', 'Synapse predicts')
c = c.replace('CVIS told', 'Synapse told')
c = c.replace('CVIS — ', 'Synapse — ')
c = c.replace('>CVIS<', '>Synapse<')
c = c.replace('"CVIS', '"Synapse')

# Fix page title
c = c.replace('<title>CVIS · Cognitive AIOps</title>', '<title>Synapse · AI System Monitor</title>')

# Fix Disk I/O always red — add context to simple mode disk reading
c = c.replace(
    'Storage is being read or written very heavily at 100%. This can slow the whole system.',
    'Storage activity is high — normal for this environment. CPU and memory are what matter most.'
)
c = c.replace(
    'Storage is being read or written very heavily at',
    'Storage is active at'
)

# Fix health score context below the score
c = c.replace(
    'id="sm-health-grade"></div>',
    'id="sm-health-grade"></div>\n      <div style="font-size:10px;color:var(--muted);margin-top:6px;line-height:1.5">Score improves as Synapse learns your machine\'s patterns · Full accuracy after 7 days</div>'
)

# Fix failures prevented zero message
c = c.replace(
    '<div class="sm-stat-sub" id="sm-prevented-sub">all time</div>',
    '<div class="sm-stat-sub" id="sm-prevented-sub">Synapse is learning — predictions improve daily</div>'
)

# Make ARIA proactive — better first message
c = c.replace(
    '''<div class="bubble">I know everything about your machine — its history, current state, and what's coming next.<br><br>Ask me anything in plain English.</div>
      <div class="mtime">ARIA</div>''',
    '''<div class="bubble">I\'m watching this machine right now and I\'ll warn you before anything goes wrong.<br><br>Ask me anything — "Will my computer crash?", "What\'s using all my memory?", "Should I be worried?"</div>
      <div class="mtime">ARIA · Synapse Intelligence</div>'''
)

# Also fix expert mode ARIA first message
c = c.replace(
    '''<div class="bubble">I know your machine\'s failure history, current trends, and what\'s predicted to happen next.<br><br>Ask me anything — I reason across past, present, and future.</div>
      <div class="mtime">System</div>''',
    '''<div class="bubble">I\'m monitoring this machine in real time. I know its failure history, current trends, and what\'s predicted next.<br><br>Ask me anything — I reason across past, present, and future.</div>
      <div class="mtime">Synapse · ARIA</div>'''
)

# Add welcome banner for new visitors (inject into simple mode body after hero)
welcome_banner = '''
    <!-- Welcome banner for new visitors -->
    <div id="welcome-banner" style="background:rgba(124,106,247,.07);border:1px solid rgba(124,106,247,.2);border-radius:10px;padding:14px 18px;display:flex;align-items:flex-start;gap:14px">
      <div style="font-size:22px;flex-shrink:0">👋</div>
      <div style="flex:1">
        <div style="font-size:13px;font-weight:600;color:var(--accent);margin-bottom:4px">Welcome to Synapse</div>
        <div style="font-size:12px;color:#aaa;line-height:1.6">You\'re looking at a live server being monitored in real time. Click <strong style="color:var(--text)">🧪 Demo</strong> to watch Synapse detect a failure on demand. Click <strong style="color:var(--text)">Ask ARIA</strong> to ask anything about the system state.</div>
      </div>
      <button onclick="document.getElementById(\'welcome-banner\').style.display=\'none\';localStorage.setItem(\'synapse_welcomed\',\'1\')" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;flex-shrink:0;padding:0">✕</button>
    </div>'''

# Inject welcome banner after sm-hero div
c = c.replace(
    '<div id="sm-onboarding"',
    welcome_banner + '\n    <div id="sm-onboarding"'
)

# Hide welcome banner if already seen (add to smInit)
c = c.replace(
    "  // Apply saved mode\n  if (_smMode === 'simple')",
    "  // Hide welcome if seen\n  if (localStorage.getItem('synapse_welcomed')) {\n    const wb = document.getElementById('welcome-banner');\n    if (wb) wb.style.display = 'none';\n  }\n  // Apply saved mode\n  if (_smMode === 'simple')"
)

# Fix demo stress test header
c = c.replace(
    '<h2>🧪 Demo stress test</h2>',
    '<h2>🧪 Synapse Demo</h2>'
)
c = c.replace(
    'Deliberately stress your machine to trigger real CVIS predictions.',
    'Deliberately stress the machine to trigger real Synapse predictions.'
)

open('frontend/index.html', 'w').write(c)
print(f"  frontend/index.html — done ({len(c.splitlines())} lines)")

# ── 2. Fix backend/main.py ────────────────────────────────────────────────────
print("Fixing backend/main.py...")
m = open('backend/main.py').read()
m = m.replace('CVIS v9 AIOps Backend', 'Synapse AI Backend')
m = m.replace('CVIS v9 Backend', 'Synapse Backend')
m = m.replace('"CVIS v9 started', '"Synapse started')
m = m.replace('CVIS v9 shutdown', 'Synapse shutdown')
m = m.replace('title="CVIS v9 AIOps Backend"', 'title="Synapse AI Backend"')
m = m.replace('version="9.0.0"', 'version="1.0.6"')
m = m.replace('description="PyTorch LSTM + beta-VAE + sklearn IF', 'description="Synapse — PyTorch LSTM + beta-VAE + sklearn IF')
m = m.replace('log.info("CVIS', 'log.info("Synapse')
open('backend/main.py', 'w').write(m)
print("  backend/main.py — done")

# ── 3. Fix docker-compose.yml if exists ──────────────────────────────────────
for fname in ['docker-compose.yml', 'docker-compose.yaml']:
    if os.path.exists(fname):
        print(f"Fixing {fname}...")
        d = open(fname).read()
        d = d.replace('cvis-backend', 'synapse-backend')
        d = d.replace('cvis-os', 'synapse')
        open(fname, 'w').write(d)
        print(f"  {fname} — done")

# ── 4. Fix README if exists ──────────────────────────────────────────────────
if os.path.exists('README.md'):
    print("Fixing README.md...")
    r = open('README.md').read()
    r = r.replace('CVIS', 'Synapse')
    open('README.md', 'w').write(r)
    print("  README.md — done")

print("\nAll fixes applied. Ready to rebuild.")
