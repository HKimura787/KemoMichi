"""Build a native launcher with Python, the web UI and ffmpeg/ffprobe included."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw
from kemocore import __version__
from kemocore.runtime import tool_path

ROOT = Path(__file__).resolve().parents[1]


def prepare_resources(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 1008, 1008), radius=220, fill="#0066BE")
    draw.line([(300, 240), (300, 784)], fill="white", width=100)
    draw.line([(730, 240), (370, 500), (730, 784)], fill="white", width=100, joint="curve")
    draw.line([(770, 720), (860, 810), (770, 900)], fill="#F08A00", width=55, joint="curve")
    image.save(destination / "KemoMichi.ico", sizes=[(n, n) for n in (16, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        image.save(destination / "KemoMichi.icns")

    licenses = destination / "licenses"
    licenses.mkdir(exist_ok=True)
    packages = []
    # Include license files from installed runtime dependencies, without importing them.
    for name in ("fastapi", "starlette", "uvicorn", "pydantic", "pydantic-core", "pillow", "anyio",
                 "h11", "annotated-types", "annotated-doc", "typing-extensions", "typing-inspection",
                 "click", "idna", "opentelemetry-api", "pyinstaller"):
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        packages.append(f"{name} {dist.version}: {dist.metadata.get('License-Expression') or dist.metadata.get('License', '')}")
        for item in dist.files or []:
            if ".dist-info" in str(item) and any(word in item.name.lower() for word in ("license", "copying", "notice")):
                target = licenses / name / item.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(dist.locate_file(item), target)
    for folder in (Path(sys.base_prefix), Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"):
        for file in folder.glob("LICENSE*"):
            shutil.copy2(file, licenses / f"Python-{file.name}")
    npm = json.loads((ROOT / "web/package-lock.json").read_text())
    for package, metadata in npm["packages"].items():
        if not package or metadata.get("dev"):
            continue
        directory = ROOT / "web" / package
        for pattern in ("LICENSE*", "COPYING*", "NOTICE*"):
            for file in directory.glob(pattern):
                if file.is_file():
                    target = licenses / "web" / package.removeprefix("node_modules/") / file.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        path = tool_path(name)
        if not path:
            raise SystemExit(f"Install {name} on the build machine, or set KEMOMICHI_FFMPEG_DIR.")
        tools[name] = path
        output = subprocess.run([path, "-version"], check=True, capture_output=True, text=True)
        (licenses / f"{name}-build.txt").write_text(output.stdout, encoding="utf-8")
        prefix = Path(path).resolve().parent.parent
        for directory in (prefix, prefix / "doc"):
            for pattern in ("COPYING*", "LICENSE*"):
                for file in directory.glob(pattern):
                    if file.is_file():
                        target = licenses / "ffmpeg" / file.name
                        target.parent.mkdir(exist_ok=True)
                        shutil.copy2(file, target)
    # FFmpeg build configuration determines which redistribution terms apply.
    text = "\n".join(packages) + "\n\nFFmpeg / ffprobe: https://ffmpeg.org/legal.html\n"
    text += "Build versions and configuration: ffmpeg-build.txt and ffprobe-build.txt.\n"
    text += "Before public redistribution, supply matching FFmpeg and external-library license texts,\n"
    text += "corresponding sources and build instructions as required by the bundled build's licenses.\n"
    text += "KemoMichi source: https://github.com/HKimura787/KemoMichi\n"
    (licenses / "THIRD-PARTY-NOTICES.txt").write_text(text, encoding="utf-8")
    return tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-web-build", action="store_true")
    parser.add_argument("--bundle-only", action="store_true", help="skip DMG / Windows installer creation")
    args = parser.parse_args()
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit("Build on macOS for a Mac app, or Windows for a Windows app.")
    if not args.skip_web_build:
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "build"], cwd=ROOT / "web", check=True)
    if not (ROOT / "src/kemoserver/static/index.html").is_file():
        raise SystemExit("Build the web UI first.")
    prepared = ROOT / "build/desktop-resources"
    tools = prepare_resources(prepared)
    from license_audit import audit
    (prepared / "licenses/dependency-audit.json").write_text(json.dumps(audit(ROOT), indent=2), encoding="utf-8")
    tool_folder = prepared / "bin"
    tool_folder.mkdir(exist_ok=True)
    for name, path in tools.items():
        target = tool_folder / (name + (".exe" if os.name == "nt" else ""))
        target.unlink(missing_ok=True)
        shutil.copy2(path, target)
        target.chmod(0o755)
    env = {**os.environ, "KEMOMICHI_BUILD_TOOLS": str(tool_folder), "KEMOMICHI_BUILD_VERSION": __version__,
           "PYINSTALLER_CONFIG_DIR": str(ROOT / "build/pyinstaller-cache")}
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build/pyinstaller"),
                    str(ROOT / "desktop/KemoMichi.spec")], cwd=ROOT, env=env, check=True)
    if args.bundle_only:
        return
    installers = ROOT / "dist/installers"
    installers.mkdir(exist_ok=True)
    if sys.platform == "darwin":
        arch = platform.machine()
        staging = ROOT / "build/dmg"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
            if staging.exists():
                subprocess.run(["rm", "-rf", str(staging)])
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "dist/KemoMichi.app", staging / "KemoMichi.app", symlinks=True)
        (staging / "Applications").symlink_to("/Applications")
        target = installers / f"KemoMichi-macOS-{arch}.dmg"
        target.unlink(missing_ok=True)
        subprocess.run(["hdiutil", "create", "-volname", "KemoMichi", "-srcfolder", str(staging),
                        "-ov", "-format", "UDZO", str(target)], check=True)
    else:
        compiler = shutil.which("ISCC") or str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
                                                / "Inno Setup 6/ISCC.exe")
        subprocess.run([compiler, str(ROOT / "desktop/windows.iss")], cwd=ROOT, env=env, check=True)
        shutil.make_archive(str(installers / "KemoMichi-Windows-x86_64-portable"), "zip",
                            root_dir=ROOT / "dist", base_dir="KemoMichi")
    manifest = {"version": __version__, "system": platform.system(), "architecture": platform.machine(),
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in installers.iterdir() if p.suffix in (".dmg", ".exe", ".zip")}}
    (installers / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Built installers: {installers}")


if __name__ == "__main__":
    main()
