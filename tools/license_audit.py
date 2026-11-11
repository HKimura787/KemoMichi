"""Record dependency inventories and reject the named .NET libraries in source/bundles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib

from kemocore.runtime import tool_path

PATTERN = re.compile(r"\b(?:NReco(?:\.VideoConverter)?|SixLabors(?:\.ImageSharp)?|ImageSharp)\b", re.I)


def audit(root: Path, bundle: Path | None = None) -> dict:
    project = tomllib.loads((root / "pyproject.toml").read_text())
    lock = tomllib.loads((root / "uv.lock").read_text())
    npm = json.loads((root / "web/package-lock.json").read_text())
    inventory = {
        "declaredPython": project["project"]["dependencies"],
        "lockedPython": [{"name": item["name"], "version": item["version"]} for item in lock["package"]],
        "lockedWeb": [{"path": key, "version": value.get("version")} for key, value in npm["packages"].items()],
    }
    matches = []
    for folder, patterns in ((root / "src", ("*.py",)), (root / "web/src", ("*.ts", "*.tsx"))):
        for pattern in patterns:
            for file in folder.rglob(pattern):
                if PATTERN.search(file.read_text(encoding="utf-8")):
                    matches.append(str(file.relative_to(root)))
    if PATTERN.search(json.dumps(inventory)):
        matches.append("dependency inventory")
    if bundle:
        matches.extend(str(file.relative_to(bundle)) for file in bundle.rglob("*") if PATTERN.search(file.name))
    ffmpeg = tool_path("ffmpeg")
    config = subprocess.run([ffmpeg, "-version"], check=True, capture_output=True, text=True).stdout if ffmpeg else ""
    result = {"checkedLibraries": {"NReco.VideoConverter": "not found", "SixLabors.ImageSharp": "not found"},
              "matches": matches, "dependencies": inventory, "ffmpegBuild": config,
              "ffmpegGplEnabled": "--enable-gpl" in config,
              "ffmpegNonfreeEnabled": "--enable-nonfree" in config,
              "scope": "Source, dependency locks and bundle filenames; not a legal compliance certification."}
    if matches:
        raise RuntimeError(f"Restricted dependency references found: {matches}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(Path(__file__).resolve().parents[1], args.bundle)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("checkedLibraries", "ffmpegGplEnabled", "ffmpegNonfreeEnabled")}))
