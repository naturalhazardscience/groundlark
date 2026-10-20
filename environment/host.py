"""Portable host launcher: Python 3.12+ and Docker; no drive sharing required."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid
from lab import MARKER, MiB, clean, lab_lock, no_links, source_files, tree_bytes, write_json

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / ".lab"
IMAGE = "groundlark/lab:1"


def call(args, **kwargs):
    return subprocess.run(["docker", *args], check=True, **kwargs)


def package_inputs():
    # Build an allowlisted tar in memory. No host staging tree or virtualenv copy.
    files = source_files(ROOT) + list((ROOT / "environment").glob("*"))
    files += [ROOT / "ui.ps1", ROOT / "ui.sh"]  # Unit-test launcher boundaries without installing UI tools.
    bundle = io.BytesIO()
    hashes = {}
    with tarfile.open(fileobj=bundle, mode="w") as archive:
        for path in sorted(set(files)):
            no_links(path)
            if path.is_dir():
                continue
            if not path.resolve().is_relative_to(ROOT):
                raise RuntimeError(f"Input outside project: {path}")
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            hashes[rel] = hashlib.sha256(data).hexdigest()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mode = 0o444
            archive.addfile(info, io.BytesIO(data))
            if bundle.tell() > 256 * MiB:
                raise RuntimeError("Source snapshot exceeds 256 MiB")
    return bundle.getvalue(), hashes


def receive_reports(name, ident, report):
    # Docker cp cannot read these tmpfs mounts on every Docker Desktop version.
    blob = call(["exec", name, "tar", "-cf", "-", "-C", "/lab/runs/" + ident, "."], capture_output=True).stdout
    if len(blob) > 256 * MiB:
        raise RuntimeError("Report archive exceeds 256 MiB")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) > 10000 or sum(m.size for m in members) > 256 * MiB:
            raise RuntimeError("Report archive exceeds extraction budget")
        for member in members:
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("Report contains a link or special file")
            if "\\" in member.name or ":" in member.name:
                raise RuntimeError("Invalid report filename")
            target = report / member.name
            no_links(target)
            if not target.resolve().is_relative_to(report.resolve()):
                raise RuntimeError("Report path escapes its run directory")
        archive.extractall(report, filter="data")


def execute(action, profile):
    image_id = call(["image", "inspect", "--format", "{{.Id}}", IMAGE], capture_output=True, text=True).stdout.strip()
    ident = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    name = "groundlark-lab-" + ident.lower()
    report = LAB / "runs" / ident
    if action == "test":
        clean(LAB, keep=4, apply=True)
        if tree_bytes(LAB) > 1024 * MiB:
            raise RuntimeError("Lab exceeds 1 GiB; review and clean old runs")
        report.mkdir(parents=True)
        write_json(report / "run.json", {"owner": MARKER, "id": ident, "status": "starting", "profile": profile})
    running = False
    try:
        bundle, hashes = package_inputs()
        call(["run", "-d", "--rm", "--init", "--name", name,
              "--label", "org.groundlark.lab=1", "--platform", "linux/amd64",
              "--network", "none", "--read-only", "--cap-drop", "ALL",
              "--security-opt", "no-new-privileges", "--memory", "8g", "--cpus", "4",
              "--pids-limit", "256", "--log-driver", "none",
              "--tmpfs", "/source:rw,exec,nosuid,size=512m,mode=0755",
              "--tmpfs", "/work:rw,exec,nosuid,size=2g,mode=1777",
              "--tmpfs", "/lab:rw,nosuid,size=256m,mode=1777",
              "--tmpfs", "/tmp:rw,exec,nosuid,size=512m,mode=1777",
              "--env", f"GROUNDLARK_IMAGE_ID={image_id}",
              "--entrypoint", "python3", IMAGE, "-c", "import time; time.sleep(3600)"], stdout=subprocess.DEVNULL)
        running = True
        call(["exec", "-i", name, "tar", "--no-same-owner", "--no-same-permissions", "-xf", "-", "-C", "/source"], input=bundle)
        args = ["exec", "--user", "1000:1000", name, "python3", "/source/environment/lab.py", action, "--profile", profile]
        if action == "test":
            args += ["--run-id", ident]
        result = subprocess.run(["docker", *args]).returncode
        if action == "test":
            receive_reports(name, ident, report)
            changed = [rel for rel, digest in hashes.items() if hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != digest]
            if changed:
                raise RuntimeError(f"Host source changed during test: {changed}")
            print(f"Reports saved: {report}", flush=True)
        return result
    except BaseException as error:
        if action == "test":
            marker = report / "run.json"
            record = json.loads(marker.read_text())
            record.update(status="failed", launcher_error=str(error))
            write_json(marker, record)
        raise
    finally:
        if running:
            subprocess.run(["docker", "stop", "--time", "2", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "test", "clean", "doctor", "unit"), nargs="?", default="test")
    parser.add_argument("--profile", choices=("full", "quick", "spice", "software", "simulation"), default="full")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        return subprocess.call(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, str(ROOT / "environment")])
    with lab_lock(LAB):
        if args.action == "clean":
            clean(LAB, keep=0 if args.all else 5, apply=args.apply)
            return 0
        return execute(args.action, args.profile)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"LAB ERROR: {error}", file=sys.stderr)
        sys.exit(1)
