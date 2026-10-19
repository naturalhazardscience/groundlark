# Groundlark repository guidance

Current priority is [sensor acquisition](docs/sensor-software.md)
on the Pi/DAQHAT-01/Trenz stack. Keep sensor
software independent of a configured FPGA; preserve the existing FPGA interfaces.
The DAQHAT-01 revision follows docs/fpga-host-link.md: six internal
QSPI signals, retained UART and four shared pins for isolated Pi-driven JTAG.
External J84-J89 and their ribbons/guide are removed. This supersedes the
155-breakout requirement. Keep the circuit, routed CAD, model and validation evidence synchronized. Preserve vendor GPIO/ground
fixtures and audit all module contacts, including deliberate no-connects, when
implementing the revision. Keep three XYZ IMUs U11-U13, geophone input and the 140 x 56 mm outline with its dedicated FPGA power extension.
U14/C18/C19/R14 are removed; sensor IDs 4/5 are legacy-only. U20/C20-C23/R20 are removed. Pi BCM6/13 serve power management; BCM24 is GNSS PPS.
Unused U41.8/U41.9 and U42.17 inputs must be grounded; U41.15/U41.16/U42.7 outputs are NC.
DAQHAT-01 uses a conventional six-layer stock FR-4 stack with through-vias only and a complete native SES
routing snapshot. Fabrication approval is owned by the user. DAQHAT-01 has MAX-M10S-00B GNSS on Pi I2C1 (0x42), PPS on BCM24, a native -X SMA antenna exit, and one Racotech/ADS122C04 input. Preserve its
independent pin/axis checks, GPIO riser assembly, and explicit
power envelope in docs/trenz-hat.md. Geophone noise/response measurements, actual stack
fit and GPIO signal integrity still need qualification. Ethernet is not exposed.

Keep authored inputs separate from disposable build output. Preserve unrelated
work. Hardware changes belong under `hw/`, software under `sw/`, shared design
and interface documentation under `docs/`, and portable test tooling under
`environment/`. See [the project map](docs/project-layout.md).
Keep public docs focused on setup, current specifications, assembly and operating
instructions. Do not add internal plans, component shortlists or work-session
review narratives to `docs/`; keep disposable investigation output in `.local/`
and test-run evidence in the existing bounded lab storage.
Generated fabrication/assembly packages in `hw/releases/` stay local and ignored.
Do not commit or push these packages unless the user explicitly requests their
publication. Keep reusable export tooling and tests tracked separately.
Assembly procurement overrides belong in `hw/assembly/`; preserve exact MPN,
manufacturer, catalog identity, manufacturer evidence and dated stock observations.
Rotation corrections must fit frozen numbered supplier pads, including an explicit
bottom-side convention, rather than hardcoded reference offsets. Run the hardware
regressions after assembly exporter/registry changes; the integration test rebuilds
both full and overlay exports without depending on ignored release archives.
See `docs/jlcpcb-assembly.md`. Offline tests never establish current inventory.

Hardware products live in `hw/groundlark-fpga-hat/`,
`hw/burrowlark-usb/` and `hw/skylark-usb/`. Skylark Rev A
uses the `skylark` target: a vertical USB PCB with socketed SGX SO2/H2S cells,
an external PMS5003, SHT40 and BMP388. Preserve its direct USB route, sensor-finger
keepouts, socket pin-view checks and native SES snapshot. Prototype firmware and
the Rev G bell enclosure are implemented; physical qualification remains pending. Preserve the existing model identifiers.
Electrical connectivity is authored in each product's `elec/*.ato`; shared atomic
parts live in `hw/shared/elec/`. Placement metadata is in each product's
`layout/placement.json`. Routed boards and review schematics are in its `boards/`.
Shared libraries, models and references live in `hw/shared/`. Build targets remain
in `hw/ato.yaml`; run direct atopile commands from the repository root. Shared
tools/tests remain in `hw/tools/` and `hw/tests/`; use `project_paths.py` for product
paths. Group procurement overrides and ignored releases by product under
`hw/assembly/` and `hw/releases/` respectively. Firmware remains under `sw/`.
Keep custom model/library paths relative and preserve the existing 3D artifacts.
Do not invoke `pack_trenz.py` as validation: they overwrite
authoring inputs. Do not silently reroute or rewrite checked CAD during tests.

Sensor acquisition uses Pi drivers/runtime software. The separate TI MSPM0L1106
power supervisor has prototype target firmware in `sw/supervisor/`; its battery policy remains disabled and physical qualification pending. The SDP32-125PA infrasound sensor U23/C24 is on DAQHAT-01 I2C1 at 0x21;
BCM6 requests Pi shutdown and BCM13 acknowledges halt; BCM24 carries GNSS PPS. Burrowlark U3/C5 are removed.
The remote USB magnetometer sensor board is
named Burrowlark, model DAQUSB-01. B1 uses four aligned PNI 14190 modules
U2/U7/U8/U9 on a 30 mm square grid and a 96 x 70 mm outline. Preserve common
SPI SCK/SI/SSN, separate SO/DRDY lanes, switched-rail high impedance when off,
per-lane raw data and cohort timing; shared commands do not phase-lock the
internal conversion clocks. Keep complete-quartet loss and explicit calibrated
averaging/skew policy. Firmware belongs to that USB sensor head.
The Trenz variant needs an FPGA bitstream. Pi acquisition/simulation and bounded
recovery are implemented; Burrowlark prototype firmware is in `sw/field-head/` with native and ARM checks; physical qualification remains pending. Skylark STM32 firmware is implemented in `sw/skylark/`, with native C driver/journal tests and an ARM build in the shared software profile. A DAQHAT-01
SPI echo bitstream is implemented and simulated; accelerated models and native
quad remain future work. Do not claim emulation or
fabrication readiness from CAD/SPICE checks.

After moving paths or changing circuits, run `python environment/check_project.py`,
`./lab.ps1 unit`, and `./lab.ps1 test` (or the `lab.sh` equivalents). Update the
affected README and design/validation documents. Use the existing hardware
checks and independent fault fixtures rather than tests that mirror the design.

Generated runs belong in ignored `.lab/`, which retains five runs. Local tool
installations and legacy caches belong in ignored `.local/`. Never commit
virtualenvs, logs, credentials, downloaded tool binaries, or Docker image archives.
Use the lab cleanup commands; do not run global Docker prune for this project.
Keep vendor attribution and the existing MIT license.

Sensor v1 semantics live in `docs/sensor-contract.md`; field layouts are in
`sw/interfaces/proto/`. Run the portable software profile when changing either.
Preserve explicit zero/missing/unknown distinctions and raw sensor precision.
Conversion discontinuities use `DataGap`: preserve it across worker IPC and emit
unknown-loss/missing records without treating host service jitter as broken hardware.
Do not reset the ADC just because conversions were overwritten. Preserve the
independent-clock stress tests and open findings in docs/bench-procedure.md.
The Buf baseline is a compatibility fixture, not routine generated output.
Do not refresh it just to bypass a breaking change. Generated descriptors belong
in ignored `sw/build/` inside the lab. Follow `docs/sensor-software.md` for runtime,
loss and recovery rules. Linux drivers have modeled-bus tests; physical sensor
qualification remains pending. Preserve both USB heads' raw precision, USB power sequencing and boot-journal identity across updates, plus Skylark raw WE/AE channels and startup missing data.

The optional live FIFO path pairs IMU tags by slot counter, preserves buffered
samples and rejects overrun/parity/timestamp faults. Retain unknown loss and timing
uncertainty semantics. `live --fifo --utc` captures MAX-M10S timing and BCM24 PPS evidence; physical sample-time bounds remain unqualified. Recorded timing evidence supports offline correlation. Offline correlation requires a recording-bound timing policy, never
extrapolates across invalid intervals, and preserves raw data. See docs/utc-timing.md
and docs/bench-procedure.md; missing measurements/limits must never pass a bench
report. Pi deployment and measurement tooling live under sw/pi/deploy and sw/tools.

The local workbench is Python/NiceGUI in `sw/ui/`; its framework-independent
controller is `sw/pi/groundlark/workbench.py`. Preserve raw count/gap semantics,
per-tab sessions, bounded recording/display buffers and separation of camera
motion from stimulus controls. Keep `sw/ui/uv.lock` synchronized with its optional
project dependencies; do not add UI packages to atopile's environment. For UI
changes run its HTTP smoke check, controller tests and a browser interaction
check. The sensor software profile includes the controller tests. Update the
workbench guide and review model provenance after changing board display assets.

The DAQHAT-01 analog path targets are enforced by prefab_review.py. Preserve local
filter/protection routing and ground stitches. Four straight Pi supports replace the previous flex-cable assembly;
check the actual board in assembly_fit.py and prefab_review.py. ADC supply-pad through-vias need filled/capped
processing in the fabrication notes.

IMU bypass layout is checked read-only by `hw/tools/imu_layout.py` as part of
`prefab_review.py`. Keep six fitted 100 nF bypass capacitors, connected local
In1.Cu ground stitches, and the documented supply/return path limits. Update
placement metadata, electrical review metadata, the native SES snapshot and
UI/render provenance together after moving parts. Geometry checks are not
physical noise qualification; see `docs/trenz-hat.md`.

DAQHAT-01 J83 is a 12 V +/-5% center-positive barrel input compatible with the
Nexys Video adapter (5.5/2.1 mm, >=3 A). Preserve its -Y exit opposite J90 +Y.
F80/D80/D81 protect the input; U80 is TPSM53603 with a 3.326 V / 3 A output
allocation, independent of the Pi rails. SW80 controls converter EN; U80 PGOOD
gates module EN1. Keep the independent power pin/geometry and fault checks,
local switching loops, output/thermal via arrays and native SES synchronized.
The 15 milliohm output-loop target and thermal/startup behavior remain unmeasured.
Assembly registry/supplier-pad review is pending for U23/C24 and power additions.

The DAQHAT-01 R3 enclosure in `hw/mechanical/daqhat-01-case/` fits the 140 x 56 mm
HAT in a 159 x 118 x 75 mm body. Preserve its Pi-centered rotation, rear DC exit
opposite the geophone, switch access, power-wing saddles and board-edge stops.
After enclosure changes regenerate the local R3 STEP/STL package and run its
`check.py`, `check_components.py`, native `check_pcb.py` and independent
`test_case.py` fault fixtures.
Refresh render provenance; CAD checks do not establish first-print or thermal fit.

DAQHAT-01 U130 (MSPM0L1106TRHBR) supervises the Pi, independently of FPGA power.
ISO1640 U43 side 2 faces Pi/GNSS; side 1 faces sensors. Preserve C48/C49 supply
assignments and the independent GNSS pin fixture. U141 TPS2553DBVR limits
antenna faults to 50–100 mA with ILIM tied IN; pin 4 FAULT is NC. Keep C151's
local L140 bypass and connected ground stitch, and C152's input bypass.
F80/F130 use 466-series 1206 fuses (2 A/4 A); 467-series parts do not fit.
J130 accepts protected battery/controller DC output from 8 to 18 V; it is not a
charger or direct solar-panel input. U131 is the always-on TPS70933; U132 makes
5.115 V / 3 A total Pi+HAT power; U133 disconnects it with off-state reverse
blocking. BCM6 is active-low shutdown, BCM13 active-high halt acknowledgement
through Q130/Q131. Preserve default-OFF RUN, VCORE's sole 470 nF load, SWD and
all unused-pin checks. JP130 is a bench override; remove its shunt for automatic
operation. Battery policy fields remain null and disabled until selected and
qualified; prototype MCU firmware defaults to RUN off and does not establish automatic battery qualification. Keep
`pi_power_checks.py`, software configuration tests, 140 x 56 mm CAD, native SES
and the 159 x 118 x 75 mm R3 enclosure synchronized.

Continuous station acquisition lives in `sw/pi/groundlark/station.py`, independently
of NiceGUI browser sessions. Keep loopback API authentication, bounded source
recovery, per-segment session checkpoints and storage reserve tests. SD provisioning
requires a nominal 32 GB minimum. Local transport only; SensorThings and LoRa
remain deferred. Active software soaks count toward the lab's five retained runs;
never claim a 168-hour pass until the elapsed run finishes successfully.

The DAQHAT profile enables autonomous geophone DRDY capture on BCM4. Preserve
the 256-reading buffer, ordered overflow/DataGap markers, 32-reading IPC drains
and stuck-reader deadline. Timestamps remain RAW read completion; GPIO edges do
not qualify conversion timing. Keep the legacy independent-clock polling fixtures
and physical throughput findings. Exhausted continuous-source channel retries
enter station backoff with a new session; bounded CLI captures stay finite.
