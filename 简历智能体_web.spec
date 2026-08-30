# -*- mode: python ; coding: utf-8 -*-
"""简历智能体 · 网页版 PyInstaller 打包配置（onedir + 内置 Chromium）。"""
from PyInstaller.utils.hooks import collect_all

datas = [
    ('webapp/static', 'webapp/static'),
    ('runtime-browsers', 'runtime-browsers'),
]
binaries = []
hiddenimports = [
    'workbench', 'webapp', 'webapp.server',
    'workbench.database', 'workbench.db_base', 'workbench.db_candidates',
    'workbench.db_delivery', 'workbench.db_jobs', 'workbench.db_page',
    'workbench.db_product', 'workbench.db_reporting', 'workbench.db_schema',
    'workbench.evaluation', 'workbench.jd_analyzer', 'workbench.resume_parser',
    'workbench.greeting', 'workbench.service', 'workbench.searcher',
    'workbench.license_mgr',
    'workbench.zhilian_browser', 'workbench.browser_worker',
    'workbench.browser_runtime', 'workbench.delivery_browser',
    'workbench.settings', 'workbench.models', 'workbench.demo',
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'searcher', 'bot', 'matcher', 'recruitment_engine',
]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cryptography')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['web_launcher.py'],
    pathex=['.', 'code'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'tkinter', 'qtpy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='简历智能体',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='简历智能体',
)
