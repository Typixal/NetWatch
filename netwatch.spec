# PyInstaller spec — single windowed exe, no installer.
#
#   uv run pyinstaller netwatch.spec
#
# Output lands in dist\NetWatch.exe. Build artefacts stay in this folder;
# nothing is written outside the project.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["src/netwatch/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=collect_submodules("netwatch"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt ships far more than this app uses; dropping the unused modules
    # roughly halves the exe.
    excludes=[
        "tkinter",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtDesigner",
        "PyQt6.QtHelp",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.Qt3DCore",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
    ],
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
    name="NetWatch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
    # Deliberately no uac_admin: NetWatch runs unelevated and asks for
    # administrator rights only when a firewall rule is actually written.
)
