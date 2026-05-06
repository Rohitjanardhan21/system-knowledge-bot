# -*- mode: python ; coding: utf-8 -*-
"""
CVIS Desktop App — PyInstaller Spec
Build: python -m PyInstaller build_app.spec --clean --noconfirm
Output: dist/CVIS.exe
"""

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all hidden imports needed by FastAPI + backend
hidden_imports = (
    collect_submodules('uvicorn')
    + collect_submodules('fastapi')
    + collect_submodules('starlette')
    + collect_submodules('aiosqlite')
    + collect_submodules('sklearn')
    + collect_submodules('torch')
    + collect_submodules('webview')
    + collect_submodules('pystray')
    + collect_submodules('PIL')
    + [
        'backend.main',
        'backend.core.ml.ml_engine',
        'backend.core.cognitive.failure_dna',
        'backend.core.cognitive.forecaster',
        'backend.core.cognitive.black_box',
        'backend.core.cognitive.postmortem_builder',
        'backend.core.cognitive.premortem',
        'backend.core.cognitive.notifier',
        'backend.core.actions.action_executor',
        'backend.core.actions.auto_remediation',
        'backend.core.alerts.alert_engine',
        'backend.core.auth.auth',
        'backend.core.storage.db',
        'backend.core.storage.redis_store',
        'backend.core.storage.model_registry',
        'backend.core.reports.weekly_report',
        'win10toast',
        'numpy',
        'psutil',
        'email.mime.text',
        'email.mime.multipart',
        'asyncio',
        'sqlite3',
    ]
)

datas = [
    ('frontend',    'frontend'),
    ('.env.example', '.'),
    ('backend',     'backend'),
]

a = Analysis(
    ['cvis_app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'PyQt5', 'wx'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CVIS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='docs/cvis.ico' if sys.platform == 'win32' else None,
    version_file=None,
    uac_admin=False,
)
