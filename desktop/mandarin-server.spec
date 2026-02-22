# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Mandarin Flask server sidecar."""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(SPECPATH, 'entry.py')],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, 'data'), 'data'),
        (os.path.join(ROOT, 'mandarin', 'web', 'templates'), 'mandarin/web/templates'),
        (os.path.join(ROOT, 'mandarin', 'web', 'static'), 'mandarin/web/static'),
        (os.path.join(ROOT, 'schema.sql'), '.'),
        (os.path.join(ROOT, 'learner_profile.json'), '.'),
    ],
    hiddenimports=[
        'mandarin',
        'mandarin.db',
        'mandarin.db.content',
        'mandarin.db.core',
        'mandarin.db.curriculum',
        'mandarin.db.profile',
        'mandarin.db.progress',
        'mandarin.db.session',
        'mandarin.audio',
        'mandarin.tone_grading',
        'mandarin.scheduler',
        'mandarin.runner',
        'mandarin.config',
        'mandarin.context_notes',
        'mandarin.conversation',
        'mandarin.diagnostics',
        'mandarin.display',
        'mandarin.doctor',
        'mandarin.grammar_linker',
        'mandarin.grammar_seed',
        'mandarin.importer',
        'mandarin.improve',
        'mandarin.media',
        'mandarin.milestones',
        'mandarin.personalization',
        'mandarin.reports',
        'mandarin.retention',
        'mandarin.scenario_loader',
        'mandarin.seed_data',
        'mandarin.validator',
        'mandarin.web',
        'mandarin.web.bridge',
        'mandarin.web.routes',
        'mandarin.web.session_store',
        'flask_sock',
        'simple_websocket',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='mandarin-server',
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
