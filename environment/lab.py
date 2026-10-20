"""Disposable Linux test runner. Source is read-only; only /lab persists."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

if os.name == "nt":
    import msvcrt
else:
    import fcntl
    import resource

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hw/tools'))
from project_paths import board_dir, compiled_dir, placement_path, PRODUCTS

MARKER = "groundlark-lab-v1"
RUN_RE = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
BOARDS = ("groundlark-field-head", "groundlark-daqhat-01", "skylark-usb")
TARGETS = ("field_head", "trenz_hat", "skylark")
MiB = 1024 * 1024


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def no_links(path):
    """Fail closed on links, including any ancestor below the filesystem root."""
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise RuntimeError(f"Refusing symbolic link: {part}")


def tree_bytes(path):
    no_links(path)
    total = 0
    for item in path.rglob("*"):
        no_links(item)
        if item.is_file():
            total += item.stat().st_size
        elif not item.is_dir():
            raise RuntimeError(f"Unexpected file type: {item}")
    return total


@contextlib.contextmanager
def lab_lock(root):
    no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".groundlark-lab"
    no_links(marker)
    # O_EXCL avoids racing initialization. Never adopt a nonempty directory.
    if not marker.exists():
        if any(root.iterdir()):
            raise RuntimeError("Unmarked .lab is not empty; refusing to adopt it")
        with marker.open("x") as stream:
            stream.write(MARKER)
    if marker.read_text() != MARKER:
        raise RuntimeError("Invalid lab ownership marker")
    no_links(root / ".lock")
    with (root / ".lock").open("a") as lock:
        try:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another lab command is active; nothing was deleted")
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def managed_runs(root):
    base = root / "runs"
    no_links(base)
    if not base.exists():
        return []
    runs = []
    for path in base.iterdir():
        # Validate every candidate before deleting any of them.
        tree_bytes(path)
        if not path.is_dir() or not RUN_RE.fullmatch(path.name):
            raise RuntimeError(f"Unrecognized run directory: {path}")
        marker = path / "run.json"
        if not marker.is_file():
            raise RuntimeError(f"Missing run marker: {path}")
        data = json.loads(marker.read_text())
        if data.get("owner") != MARKER or data.get("id") != path.name:
            raise RuntimeError(f"Invalid run marker: {path}")
        runs.append(path)
    return sorted(runs, key=lambda p: p.name, reverse=True)


def clean(root, keep=5, apply=False):
    if keep < 0:
        raise ValueError("keep must be nonnegative")
    runs = managed_runs(root)
    active = [p for p in runs if json.loads((p/'run.json').read_text()).get('active_soak') is True]
    if len(active)>keep:
        raise RuntimeError('Active soak occupies retained lab storage; stop it before cleanup')
    paths = [p for p in runs if p not in active][keep-len(active):]
    for path in paths:
        # Resolve and check the final absolute target immediately before removal.
        no_links(path)
        if path.resolve().parent != (root / "runs").resolve():
            raise RuntimeError(f"Cleanup escaped the run directory: {path}")
        print(f"{'DELETE' if apply else 'WOULD DELETE'} {path.name} ({tree_bytes(path)/MiB:.1f} MiB)", flush=True)
        if apply:
            shutil.rmtree(path)
    if not paths:
        print("No old runs to remove.", flush=True)
    return paths


def source_files(source):
    files = [source / "hw/ato.yaml"] + [placement_path(b, source) for b in BOARDS]
    for folder, patterns in {
        "hw/shared/elec": ("*.ato", "*.kicad_mod", "*.kicad_sym"),
        **{f"hw/{product}/elec": ("*.ato",) for product in PRODUCTS.values()},
        "hw/tools": ("*.py",), "hw/tests": ("*.py",), "docs": ("*.csv",),
        "hw/assembly": ("*.json",),
        "hw/shared/libraries": ("*.kicad_mod", "*.kicad_sym"),
        "hw/skylark-usb/models": ("*.wrl", "*.json"),
        "sw/interfaces": ("*.proto", "*.yaml", "*.binpb", "*.py", "*.options"),
        "sw/tools": ("*.py",), "sw/tests": ("*.py", "*.json"),
        "sw/pi": ("*.py", "*.json", "*.dts", "*.cfg"),
        "sw/skylark/firmware": ("*.c", "*.h", "*.ld", "Makefile"),
        "sw/skylark/tests": ("*.c", "*.h"),
        "sw/field-head/firmware": ("*.c", "*.h", "*.ld", "Makefile"),
        "sw/field-head/tests": ("*.c", "*.h"),
        "sw/supervisor": ("*.c", "*.h", "*.ld", "*.py", "Makefile"),
        "sw/fpga": ("*.py", "*.sv", "*.xdc", "*.tcl", "*.rpt", "*.json"),
    }.items():
        for pattern in patterns:
            files.extend((source / folder).rglob(pattern))
    files.append(source / "hw/tests/overvoltage.ato")
    files.append(source / "hw/shared/reference/raspberrypi_hat.kicad_pcb")
    files.append(source / "hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.ses")
    files.append(source / "hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/verification.json")
    files.append(source / "hw/skylark-usb/boards/skylark-usb/skylark-usb.ses")
    files.append(source / "hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.ses")
    for target in TARGETS:
        folder = compiled_dir(target, source)
        files.append(folder / f"{target}.kicad_pcb")
        files.extend(folder.glob("*-lib-table"))
    for board in BOARDS:
        folder = board_dir(board, source)
        files.extend(folder.glob("*.kicad_sch"))
        files.extend(folder.glob("*.kicad_sym"))
        files.extend(folder.glob("*.kicad_dru"))
        files.extend(folder.glob("*-lib-table"))
        files.extend(folder / name for name in (
            f"{board}.kicad_pcb", f"{board}.kicad_pro", "electrical.json", "bom.csv"))
    return sorted(set(files))


def stage(source, workspace, report):
    manifest = {}
    for path in source_files(source):
        no_links(path)
        if not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            raise RuntimeError(f"Invalid source input: {path}")
        rel = path.relative_to(source)
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        manifest[str(rel)] = hashlib.sha256(target.read_bytes()).hexdigest()
    for path in sorted((source / "environment").glob("*")):
        no_links(path)
        if path.is_file():
            manifest[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("shared/simulation", "groundlark-fpga-hat/simulation", "logs"):
        (workspace / "hw" / name).mkdir(parents=True, exist_ok=True)
    write_json(report / "inputs.sha256.json", manifest)
    return manifest


def versions():
    def output(args):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    return {
        "image_id": os.environ.get("GROUNDLARK_IMAGE_ID", "unknown"),
        "kicad": output(["kicad-cli", "version"]),
        "ngspice": output(["ngspice", "--version"]),
        "system_python": sys.version,
        "system_sexpdata": output(["python3", "-c", "import importlib.metadata as m; print(m.version('sexpdata'))"]),
        "iverilog": output(["iverilog", "-V"]).splitlines()[0],
        "device_tree_compiler": output(["dtc", "--version"]),
        "atopile_python": output(["/opt/atopile/bin/python", "--version"]),
        "atopile": output(["/opt/atopile/bin/python", "-c", "import importlib.metadata as m; print(m.version('atopile'))"]),
        "buf": output(["buf", "--version"]),
        "gcc": output(["gcc", "-dumpfullversion"]),
        "arm_gcc": output(["arm-none-eabi-gcc", "-dumpfullversion"]),
        "libopencm3": Path('/opt/skylark/revision.txt').read_text().strip(),
        "protobuf": output(["/opt/atopile/bin/python", "-c", "import google.protobuf; print(google.protobuf.__version__)"]),
    }


def commands(profile):
    steps = []
    if profile in ("full", "simulation"):
        for target in TARGETS:
            steps += [(f"build-{target}", ["/opt/atopile/bin/python", "-m", "atopile", "build", "-b", target, "hw"]),
                      (f"constraints-{target}", ["/opt/atopile/bin/python", "hw/tools/solve_constraints.py", "--target", target])]
        steps.append(("reject-overvoltage", ["/opt/atopile/bin/python", "hw/tools/solve_constraints.py", "--negative"]))
    if profile in ("full", "quick", "simulation"):
        hardware=["python3", "/source/environment/hardware_regressions.py"] if profile=="simulation" else ["python3", "-m", "unittest", "discover", "-s", "hw/tests", "-p", "test_*.py"]
        steps += [("hardware-regressions", hardware)]
        steps += [(name, ["python3", f"hw/tools/{name}.py"]) for name in ("check_circuit", "check_design", "check_trenz", "daqhat_01_engineering", "prefab_review", "check_skylark")]
        steps.append(("routing-replay", ["python3", "hw/tools/replay_trenz.py"]))
        steps.append(("burrowlark-routing-replay", ["python3", "hw/tools/replay_burrowlark.py"]))
    if profile != "software":
        steps += [(name, ["python3", f"hw/tools/{name}.py"]) for name in ("simulate", "simulate_trenz", "simulate_geophone", "simulate_geophone_review", "simulate_host_link", "signal_response", "power_review")]
        steps += [(name, ["python3", f"hw/tools/{name}.py"]) for name in ("simulate_signal_integrity", "pressure_pneumatics")]
    if profile in ("full", "quick", "software", "simulation"):
        steps.append(("fpga-loopback-rtl", ["python3", "sw/fpga/test.py"]))
        steps.append(("fpga-implementation-evidence", ["python3", "sw/fpga/verify_reports.py"]))
        steps.append(("sensor-contracts", ["/opt/atopile/bin/python", "sw/tools/check_interfaces.py"]))
    return steps


def collect(workspace, report, profile):
    files = [workspace / "sw/build" / name for name in ("verification.json", "demo.ssrec", "demo-summary.json", "hat-signals.ssrec", "hat-signals.json", "pressure-response.json", "acquisition-stress.json")]
    files += [workspace/'sw/build/skylark-arm'/name for name in ('skylark.elf','skylark.bin','skylark.map','firmware.json')]
    files += [workspace/'sw/build/burrowlark-arm'/name for name in ('burrowlark.elf','burrowlark.bin','burrowlark.map','firmware.json')]
    files += [workspace/'sw/build/supervisor-arm'/name for name in ('supervisor.elf','supervisor.bin','supervisor.map')]
    files += [workspace/'sw/build/schema.binpb']
    for pattern in ("*.json", "*.cir", "*.log"):
        for folder in ("hw/shared/simulation", "hw/groundlark-fpga-hat/simulation"):
            files.extend((workspace / folder).rglob(pattern))
    for board in BOARDS:
        folder = board_dir(board, workspace)
        files.extend(folder / name for name in ("drc.json", "erc.json", "validation.json", "schematic-netlist.xml", "engineering.json", "prefab-review.json", "replay.json", "fabrication-audit.json"))
    if profile in ("full", "simulation"):
        for target in TARGETS:
            files.append(compiled_dir(target, workspace) / f"{target}.kicad_pcb")
    for path in files:
        if path.is_file():
            no_links(path)
            dest = report / "results" / path.relative_to(workspace)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)


def run_steps(steps, workspace, report, record):
    """Collect every check result; a failed gate still fails the whole run."""
    failed=[]
    for name, cmd in steps:
        print(f"RUN {name}", flush=True)
        tick=time.monotonic()
        error=None
        with (report / f"{name}.log").open("w") as log:
            try:
                code=subprocess.run(cmd,cwd=workspace,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
            except (subprocess.TimeoutExpired,OSError) as exc:
                code=1;error=str(exc);log.write('\n'+error+'\n')
        step={"name":name,"exit_code":code,"seconds":round(time.monotonic()-tick,2)}
        if error:step['error']=error
        record['steps'].append(step)
        write_json(report/'run.json',record)
        if code:
            failed.append(name)
            print((report/f"{name}.log").read_text(errors="replace")[-5000:],flush=True)
    return failed


def test(source, root, workspace, profile, ident=None):
    # Retain at most five runs, including the new one. No hidden unlimited history.
    clean(root, keep=4, apply=True)
    if tree_bytes(root) > 1024 * MiB:
        raise RuntimeError("Lab exceeds the 1 GiB start budget; review and clean old runs")
    ident = ident or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    if not RUN_RE.fullmatch(ident):
        raise RuntimeError("Invalid run ID")
    report = root / "runs" / ident
    report.mkdir(parents=True)
    record = {"owner": MARKER, "id": ident, "profile": profile, "status": "running", "steps": []}
    write_json(report / "run.json", record)
    print(f"Report: .lab/runs/{ident}", flush=True)
    started = time.monotonic()
    result = 1
    try:
        write_json(report / "toolchain.json", versions())
        manifest = stage(source, workspace, report)
        record['failed_steps']=run_steps(commands(profile),workspace,report,record)
        # Detect source edits during the run as well as accidental writes.
        for rel, digest in manifest.items():
            if hashlib.sha256((source / rel).read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Source changed during run: {rel}")
        if record['failed_steps']:
            raise RuntimeError('Failed checks: '+', '.join(record['failed_steps'])+' (see logs)')
        record["status"] = "passed"
        result = 0
    except Exception as error:
        record["status"] = "failed"
        record["error"] = str(error)
        print(f"FAIL: {error}", flush=True)
    finally:
        try:
            collect(workspace, report, profile)
        except Exception as error:
            record["collection_error"] = str(error)
            record["status"] = "failed"
            result = 1
        record["seconds"] = round(time.monotonic()-started, 2)
        write_json(report / "run.json", record)
    print(f"{record['status'].upper()}: {len(record['steps'])} steps; {tree_bytes(report)/MiB:.1f} MiB retained", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("test", "clean", "doctor", "unit"))
    parser.add_argument("--profile", choices=("full", "quick", "spice", "software", "simulation"), default="full")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--all", action="store_true", help="Clean every marked run, including latest evidence")
    args = parser.parse_args()
    # Bound individual output/log files. Scratch mounts have separate hard size limits.
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * MiB, 32 * MiB))
    Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
    if args.action == "unit":
        return subprocess.call(["python3", "-m", "unittest", "discover", "-s", "/source/environment", "-p", "test_*.py", "-v"])
    if args.action == "doctor":
        print(json.dumps(versions(), indent=2))
        return 0
    with lab_lock(Path("/lab")):
        if args.action == "clean":
            clean(Path("/lab"), keep=0 if args.all else 5, apply=args.apply)
            return 0
        return test(Path("/source"), Path("/lab"), Path("/work"), args.profile, args.run_id)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"LAB ERROR: {error}", file=sys.stderr)
        sys.exit(1)
