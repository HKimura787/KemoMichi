"""Run through tools/package_desktop.py so video tools and notices are prepared first."""
import os
from pathlib import Path
import sys

root = Path(SPECPATH).parent
prepared = root / "build" / "desktop-resources"
tool_folder = Path(os.environ["KEMOMICHI_BUILD_TOOLS"])
suffix = ".exe" if sys.platform == "win32" else ""
icon = str(prepared / ("KemoMichi.icns" if sys.platform == "darwin" else "KemoMichi.ico"))

a = Analysis(
    [str(root / "desktop" / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[(str(tool_folder / (name + suffix)), "bin") for name in ("ffmpeg", "ffprobe")],
    datas=[(str(root / "src" / "kemoserver" / "static"), "kemoserver/static"),
           (str(root / "LICENSE"), "licenses"), (str(prepared / "licenses"), "licenses")],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"],
    hookspath=[], runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KemoMichi", console=False, debug=False,
          strip=False, upx=False, icon=icon, codesign_identity=os.environ.get("KEMOMICHI_CODESIGN_IDENTITY"))
collected = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="KemoMichi")
if sys.platform == "darwin":
    app = BUNDLE(collected, name="KemoMichi.app", icon=icon, bundle_identifier="jp.kemomichi.desktop",
                 info_plist={"CFBundleShortVersionString": os.environ["KEMOMICHI_BUILD_VERSION"],
                             "NSHighResolutionCapable": True})
