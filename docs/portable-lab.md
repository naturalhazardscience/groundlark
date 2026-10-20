# Portable test environment

**DAQHAT-01 GNSS revision:** MAX-M10S-00B uses Pi I2C1 and BCM24 PPS alongside the Racotech geophone. Portable tests exercise modeled timing; physical millisecond alignment remains unqualified.

The project now has one disposable Docker test environment. Keep authored files
in their existing locations and use the root `lab.ps1` or `lab.sh` launcher for
validation. Existing local virtual environments and historical reports are not
required by this runner and are not removed by cleanup.

## Start here

Prerequisites: Docker with Linux containers, Python 3.12 or newer, and enough
Docker memory for an 8 GiB container. Both are already available on the current
Windows machine. The toolchain is Linux/amd64; other host architectures require
Docker's amd64 emulation and have not been verified.

From the project folder in PowerShell:

```powershell
.\lab.ps1 build                 # Once; needs Internet
.\lab.ps1 doctor                # Show exact installed tool versions
.\lab.ps1 test                  # Full circuit + PCB + SPICE validation
.\lab.ps1 test -Profile quick   # Saved compiled circuit/PCB + SPICE checks
.\lab.ps1 test -Profile spice   # Only bounded SPICE cases
.\lab.ps1 test -Profile software # Sensor application, contracts and recovery
.\lab.ps1 test -Profile simulation # Fresh builds and models; procurement excluded
.\lab.ps1 unit                  # Cleanup/staging safeguards
```

On Linux/macOS, use `sh ./lab.sh build`, `sh ./lab.sh test`, and
`sh ./lab.sh test --profile quick`. Alternatively, run
`python environment/host.py test` on Windows or `python3 environment/host.py test`
elsewhere. Paths are relative to the launcher, not the current working directory.
No global Python packages or project virtual environments are installed.

The image's native KiCad interpreter includes hash-pinned NumPy, SciPy,
Pillow and sexpdata for read-only copper extraction and routing replay.
`environment/system-requirements.in` records direct versions and
`environment/system-requirements.txt` records wheel hashes. Rebuild the image
after changing either; these dependencies do not enter atopile's environment.

Windows Docker Desktop could not bind-mount this machine's `P:` drive. The
launcher therefore sends an allowlisted source snapshot through Docker's API,
runs against that copy, and copies reports back. This also works without Docker
drive-sharing configuration. No host directory is mounted into the container.

## What each profile proves

| Profile | Checks |
| --- | --- |
| `full` (default) | Fresh atopile builds for all three boards; numeric constraints and unsafe overvoltage rejection; independent hardware regressions including procurement; native KiCad ERC/DRC/connectivity; power/clearance review; routing replay; SPICE, electrostatic/RF/coupling and pneumatic models; the software profile (28 stages). |
| `simulation` | Same 28 stages as `full`, excluding exactly `test_supplier_placement_release_gate`. Native mating geometry, known supplier-pad fixtures, exporter regressions and all electrical/software checks still run. This is not procurement or fabrication approval. |
| `quick` | Same GPIO/component fault, circuit/PCB consistency, routing replay, SPICE and software checks using saved compiled layouts. Does **not** prove `.ato` changes were rebuilt. |
| `spice` | Bounded shared/USB, Trenz, geophone and host-link SPICE cases, signal/power review, plus electrostatic/RF/coupling and pneumatic models; includes expected fault detection. |
| `software` | RTL and Python-to-RTL co-simulation; recorded Vivado evidence/hash gate; Buf format/lint/build and compatibility; acquisition/replay, modeled driver and Linux TTY/worker fault tests; retained acquisition demo; Skylark native C fault tests and ARM firmware build. No physical hardware execution. |

The runner calls the existing project entrypoints. Routing reconstruction stays
in a temporary tree; it does not rewrite source CAD, render images, or release fabrication files. A full test
compares freshly compiled connectivity with the saved routed boards and should
fail if they disagree.

The runner records every check, including checks after a failure or timeout.
The simulation profile prints its one named procurement exclusion; it never
converts that exclusion into a pass or changes the full profile's release gate.
Model execution/test success and design acceptance are separate: for example,
`signal-integrity.json` retains `all_corners_meet_targets: false` when an RF
corner misses its design allocation. See [model assumptions and acceptance](simulation-validation.md).
Any failed check still fails the overall run; `run.json` lists `failed_steps`
and each check has its own log. In particular, an assembly-registry mismatch
does not suppress the later circuit, SPICE or software results. Checks with
missing build prerequisites can fail as well; inspect the earlier build logs.

These are bounded electrical models, RTL simulations and CAD checks. They do not
emulate sensor silicon, USB enumeration, a booted Raspberry Pi or FPGA execution.
They do not establish regulator stability, complete signal/power integrity,
thermal performance, physical mating, or fabrication readiness.

## Where files go

```text
groundlark/
  hw/                circuits, routed CAD, models and hardware checks
  sw/                Pi software, USB firmware and FPGA integration scopes
  docs/              shared design and interface documentation
  environment/       small runner, Dockerfile, dependency lock and safety tests
  lab.ps1 / lab.sh   entrypoints
  .local/            ignored local tools and preserved legacy caches
  .lab/
    .groundlark-lab   ownership marker
    .lock            prevents simultaneous run/cleanup
    runs/<run-id>/   status, input hashes, tool versions, logs, result files
```

The source snapshot, build tree, package caches and tool temporary files live
inside memory-backed container filesystems and disappear when the container
exits. The test process runs without root privileges. Input files are owned by
root and read-only to that process; the container root filesystem is read-only.
There are no persistent Docker volumes, hardware passthroughs, host-network
access, or mounted Docker sockets.

Containment limits:

- Keep the **five newest runs**, including failures. Before a new run, older
  marked runs are removed automatically. Save evidence you need to keep outside
  `.lab` before the next run; do not treat `.lab` as an archive.
- Scratch workspace: 2 GiB; tool temporary files: 512 MiB; source snapshot:
  512 MiB; reports inside a run: 256 MiB. Individual logs/files: 32 MiB.
- Refuse to start if retained host data exceeds 1 GiB after retention cleanup.
  This is a start check, not a host filesystem quota.
- Container: 8 GiB RAM, four CPUs, 256 processes. Each test step times out after
  ten minutes. A container abandoned by a terminated launcher expires after one
  hour. Normal success/failure stops and removes it immediately.
- Test runs use no network. Dependencies are downloaded only during image build.

Each report identifies the exact image ID and tool versions, hashes the inputs,
records step outcomes, and includes generated SPICE decks and logs. The launcher
checks that the host inputs did not change during the run. Reports are copied
back after execution; forcibly terminating Docker can lose that run's in-memory
details. Its host status marker remains for diagnosis and later cleanup.

## Cleanup

```powershell
.\lab.ps1 clean                 # Preview old runs beyond the newest five
.\lab.ps1 clean -Apply          # Remove those old runs
.\lab.ps1 clean -All            # Preview removing every run
.\lab.ps1 clean -All -Apply     # Remove all disposable test evidence
```

Equivalent shell flags are `clean --apply` and `clean --all --apply`. Cleanup
works without Docker. It requires the lab ownership marker, validates every run
marker and final absolute path, refuses symlinks/junctions and unknown folders,
and acquires the same lock used by tests. It only removes recognized run folders.
It leaves authored files, CAD, existing virtual environments, and the old `C:`
project copy alone. An unexpected folder causes cleanup to stop for inspection.

The reusable Docker image and Docker build cache live in Docker Desktop's disk,
outside `.lab`. The installed image reports about 2.92 GB, including 2.25 GB
shared with its KiCad base. Normal test runs do not rebuild or grow this image.
Use `docker system df` to inspect storage. To remove this
project's image, use `docker image rm groundlark/lab:1` after tests have stopped.
Do not use global `docker system prune` or `docker volume prune` as project
cleanup: other projects share this Docker installation.

## Moving or updating it

Clone the Git repository, or copy the authored project and environment directory
(excluding `.lab/` and `.local/`) to another machine,
then run `build`. No absolute `C:` or `P:` paths are encoded in the runner. The
image pins the KiCad base and uv installer by digest; atopile 0.15.9 and its
transitive Python dependencies are pinned with package hashes. Python is 3.14.7.
Device-tree compiler 1.6.1-4+b1 supplies real overlay compile/merge tests.
The KiCad base supplies KiCad 9.0.9 and ngspice 39; previous WSL validation used
ngspice 42. The reports explicitly record this difference.

For an offline transfer, optionally save a **single image archive**:

```powershell
docker save -o groundlark-lab-image.tar groundlark/lab:1
# On the receiving machine:
docker load -i groundlark-lab-image.tar
```

Keep that archive on transfer storage, not in the source repository or `.lab`.
Source plus an exported image gives a stronger toolchain snapshot than rebuilding
from online registries. Container runtime/kernel versions still vary by host.
The checked-in `requirements.lock` is consumed directly; the old project venvs
are never copied. `installed-constraints.txt` records the versions used when
creating that lock. Update pins deliberately and rerun the complete suite.

An [inactive GitHub Actions template](../environment/ci/README.md) can run the
structure checks, cleanup tests, and full hardware profile on pushes and pull
requests, with report retention of seven days. It has not been installed because
the current GitHub login lacks workflow-management scope. The local suite is
fully usable. The software/full/quick profiles validate the sensor application,
contracts, framing, recording/replay and bounded recovery. Skylark’s production
C sensor/encoder and flash-journal code run against native fault fixtures, and
the STM32 ARM image is linked. Physical device behavior and USB enumeration
remain outside these checks.
Buf 1.73.0 is downloaded only during image build and SHA-256 checked; Protobuf
5.29.6 reuses the existing Python lock. Runtime tests remain offline.

The image also contains native GCC, ARM GCC 12.2.1, newlib headers and a pinned,
SHA-256 verified libopencm3 source/build. Rebuild with `lab.ps1 build` after this
toolchain change. Tool versions and the libopencm3 revision are recorded with
each run. No network access is needed during software tests.
