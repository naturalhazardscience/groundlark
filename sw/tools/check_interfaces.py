"""Offline schema checks and portable contract tests; output only in sw/build/."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
INTERFACES = ROOT / "sw/interfaces"
BUILD = ROOT / "sw/build"
BUF = os.environ.get("GROUNDLARK_BUF", "buf")


def run(*args, **kwargs):
    return subprocess.run(list(args), cwd=INTERFACES, check=True, **kwargs)


def main():
    BUILD.mkdir(exist_ok=True)
    run(BUF, "format", "--diff", "--exit-code")
    run(BUF, "lint")
    run(BUF, "build", "--exclude-source-info", "-o", str(BUILD / "schema.binpb"))
    baseline = INTERFACES / 'baseline.binpb'
    run(BUF, "breaking", "--against", str(baseline))
    # Prove that the compatibility gate catches a real incompatible wire change.
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        folder = Path(tmp)
        shutil.copytree(INTERFACES / "proto", folder / "proto")
        shutil.copy2(INTERFACES / "buf.yaml", folder / "buf.yaml")
        path = folder / "proto/groundlark/sensor/v1/sensor.proto"
        path.write_text(path.read_text().replace("fixed64 boot_id = 3;", "string boot_id = 3;"))
        rejected = subprocess.run([BUF, "breaking", str(folder), "--against", str(baseline)],
                                  capture_output=True, text=True)
        assert rejected.returncode != 0 and "boot_id" in rejected.stdout + rejected.stderr, rejected
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(INTERFACES / "python"), str(ROOT / "sw/pi")]),
               GROUNDLARK_DESCRIPTOR=str(BUILD / "schema.binpb"))
    run(sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "sw/tests"), "-p", "test_*.py", "-v", env=env)
    run('make', '-C', str(ROOT/'sw/skylark/firmware'), 'LIBOPENCM3=/opt/skylark/libopencm3',
        'EXTRA_CFLAGS=-isystem/usr/include/newlib', 'BUILD='+str(BUILD/'skylark-arm'))
    run('make', '-C', str(ROOT/'sw/field-head/firmware'), 'LIBOPENCM3=/opt/skylark/libopencm3',
        'EXTRA_CFLAGS=-isystem/usr/include/newlib', 'BUILD='+str(BUILD/'burrowlark-arm'))
    run('make', '-C', str(ROOT/'sw/supervisor/firmware'), 'BUILD='+str(BUILD/'supervisor-arm'))
    arm = BUILD/'skylark-arm'
    size = run('arm-none-eabi-size',str(arm/'skylark.elf'),capture_output=True,text=True).stdout.splitlines()[1].split()
    text_bytes,data_bytes,bss_bytes=map(int,size[:3])
    assert text_bytes+data_bytes <= 124*1024 and data_bytes+bss_bytes <= 12*1024
    (arm/'firmware.json').write_text(json.dumps(dict(
        target='STM32F072CBT6',flash_bytes=text_bytes+data_bytes,static_ram_bytes=data_bytes+bss_bytes,
        reserved_boot_journal_bytes=4096,minimum_stack_reserve_bytes=4096,
        sha256={name:hashlib.sha256((arm/name).read_bytes()).hexdigest() for name in ('skylark.elf','skylark.bin')},
        scope='ARM link and native C fault fixtures; physical USB/sensor/power qualification pending'),indent=2)+'\n')
    head = BUILD/'burrowlark-arm'
    size = run('arm-none-eabi-size',str(head/'burrowlark.elf'),capture_output=True,text=True).stdout.splitlines()[1].split()
    text_bytes,data_bytes,bss_bytes=map(int,size[:3])
    assert text_bytes+data_bytes <= 30*1024 and data_bytes+bss_bytes <= 4*1024
    (head/'firmware.json').write_text(json.dumps(dict(
        target='STM32F042K6',flash_bytes=text_bytes+data_bytes,static_ram_bytes=data_bytes+bss_bytes,
        reserved_boot_journal_bytes=2048,minimum_stack_reserve_bytes=2048,
        sha256={name:hashlib.sha256((head/name).read_bytes()).hexdigest() for name in ('burrowlark.elf','burrowlark.bin')},
        scope='ARM link and native C array fault fixtures; physical USB, timing and magnetic noise unqualified'),indent=2)+'\n')
    # Run the public application entry point and retain one bounded review artifact.
    demo = BUILD / "demo.ssrec"
    if demo.exists(): demo.unlink()
    cli = str(ROOT / "sw/tools/sensor.py")
    simulated = run(sys.executable, cli, "simulate", "--remote", "--seconds", "2",
                    "--faults", str(ROOT / "sw/tests/fixtures/acquisition_faults.json"),
                    "--scenario", str(ROOT / "sw/pi/profiles/stimulus-demo.json"),
                    "--output", str(demo), env=env, capture_output=True, text=True)
    replayed = run(sys.executable, cli, "replay", str(demo), env=env, capture_output=True, text=True)
    assert json.loads(simulated.stdout) == json.loads(replayed.stdout)
    (BUILD / "demo-summary.json").write_text(replayed.stdout)
    signal_capture = BUILD / "hat-signals.ssrec"
    signal_report = signal_capture.with_suffix(".json")
    for path in (signal_capture, signal_report):
        if path.exists(): path.unlink()
    run(sys.executable, str(ROOT / "sw/tools/check_hat_signals.py"), "--output", str(signal_capture),
        env=env, capture_output=True, text=True)
    pressure_response = run(sys.executable, str(ROOT / 'sw/tools/pressure_response.py'),
                            env=env, capture_output=True, text=True).stdout
    (BUILD / 'pressure-response.json').write_text(pressure_response)
    (BUILD / "verification.json").write_text(json.dumps({
        "status": "passed", "buf": run(BUF, "--version", capture_output=True, text=True).stdout.strip(),
        "breaking_baseline": "sw/interfaces/baseline.binpb", "incompatible_change_rejected": True,
        "application_demo": json.loads(replayed.stdout),
        "hat_signals": json.loads(signal_report.read_text()),
        "pressure_response": 'pressure-response.json; ideal averaging and alias model, not physical qualification',
        "skylark_firmware": "ARM image linked; production C drivers/encoder and flash journal tested with native fault fixtures",
        "burrowlark_firmware": "ARM image linked; four-lane timing, readback/status faults, saturation, encoder bounds and complete-quartet loss tested natively",
        "scope": "Schemas, software acquisition/replay, modeled sensor buses and injected faults; not physical buses, USB enumeration or MCU emulation"
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
