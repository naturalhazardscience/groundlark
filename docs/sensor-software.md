# Sensor acquisition and recovery

For `calibration-observe`, `calibration-fit`, measured reference templates and instrument-bound calibration records, see [Calibrating Groundlark](calibration.md).

**New to the simulator?** Start with the [browser workbench walkthrough](sensor-workbench.md).
This page covers command-line development and real Linux acquisition.
The current HAT has three IMUs, a Racotech geophone input, infrasound and MAX-M10S GNSS. The fourth IMU and inclinometer remain legacy-only.
DLVR infrasound is covered by simulation and the six-sensor browser bench;
its Pi I2C hardware driver remains pending. The live factory currently supports
the IMUs, geophone ADC and GNSS receiver.

The runnable Pi application is in `sw/pi/groundlark/`; use
`sw/tools/sensor.py` as its repository entry point. It has no FPGA,
network service or database dependency. Simulation and Linux device adapters
use the same scheduler, calibration, session validation and recording path.
Physical acceptance follows the [bench procedure](bench-procedure.md).

## Run without hardware

Run `./lab.ps1 test -Profile software` (or `sh ./lab.sh test --profile software`).
The portable environment contains the pinned Python/Protobuf and Buf tools.
It builds the descriptor, runs tests, executes a two-second six-sensor fault
scenario and replays it. Retained outputs are under
`.lab/runs/<run-id>/results/sw/build/`: `demo.ssrec`, `demo-summary.json` and
`verification.json`. Five-run retention and existing cleanup cover these files.
No new environment or global package installation is needed for this workflow.

For direct development use Python 3.12+ with the Protobuf version in
`environment/requirements.lock`, and Buf 1.73.0. Generate the descriptor once:

```sh
mkdir -p sw/build
buf build sw/interfaces --exclude-source-info -o sw/build/schema.binpb
python sw/tools/sensor.py simulate --remote --seconds 2 \
  --faults sw/tests/fixtures/acquisition_faults.json --output sw/build/my-run.ssrec
python sw/tools/sensor.py replay sw/build/my-run.ssrec
```

Outputs use exclusive creation: choose a new filename for each direct run.
The lab manages its own copy and does not delete direct developer recordings.
`GROUNDLARK_DESCRIPTOR` can select a descriptor outside the default build
directory. Do not use the frozen compatibility baseline as the generated schema.

The scenario is deterministic for a given seed, configuration and fault file,
including recording bytes. It covers three IMUs, geophone,
magnetometer and pressure. Remote streams in this command are modeled MCU
producers, not firmware or USB emulation. Separate tests send framed messages
in fragments through a Linux pseudo-terminal. `--queue 1 --drain-every 100`
exercises a slow consumer. Simulated time starts at zero; Pi and remote clocks
retain distinct domains even when numerically equal.

Virtual sensors use controllable motion, magnetic, pressure and geophone
[stimulus models](stimulus-models.md). Pass `--scenario` for saved waveforms and
timed controls; `export-scenario` recovers controls from a recording. Without a
scenario, sensors start stationary and level, with a constant magnetic field,
zero differential pressure and zero geophone velocity.

## Linux device adapters

The live path uses Linux SPI/I²C ioctls, GPIO character-device line requests,
and a nonblocking USB CDC TTY. The initial profile is:

| Sensor | Configuration and reading |
| --- | --- |
| Three LSM6DSO | 26 Hz, ±2 g, ±250 dps; identity/reset/readback; BDU/address increment; signed temperature, gyro and acceleration. |
| MAX-M10S-00B | I²C 0x42, 1 Hz NAV-PVT; optional timing configuration/readback, TIM-TP, NAV-TIMEUTC and BCM24 PPS capture. |
| ADS122C04 geophone input | I²C 0x40; 330 SPS, PGA64, internal 2.048 V reference; signed 24-bit counts, conversion counter and inverted-data integrity checks. |
| Burrowlark DAQUSB-01 USB head | Receive v1 identity/configuration/batches/status over framed CDC; B1 prototype firmware publishes four raw magnetic lanes plus SHT45; physical USB qualification is pending. |

IMU filter registers are explicitly written, checked and included in effective
`register_config`. The default 26 Hz profile has 13 Hz accelerometer and 8.3 Hz
gyro bandwidth; sample rate is not flat signal bandwidth. See
[sensor bandwidth and timing](sensor-response.md) for both boards' response and
aliasing limits. Raw samples and existing timestamp uncertainty remain intact.

SCL3300 is retained for legacy recordings. MAX-M10S is active at I2C address 0x42; add `--fifo --utc` to capture timing evidence and BCM24 PPS.

Copy [the example profile](../sw/pi/profiles/daqhat-01.example.json) and verify paths
on the actual Pi. `gpiochip0` is an example, not an assertion about Pi 5 GPIO
numbering. `line` is the character-device offset corresponding to BCM26 on that
chip. The application owns active-low sensor output enable and disables it on
normal/error cleanup.

| Signal | BCM GPIO | Physical header pin |
| --- | --- | --- |
| SPI0 MOSI / MISO / SCLK | 10 / 9 / 11 | 19 / 21 / 23 |
| IMU1 / IMU2 / IMU3 chip select | 8 / 7 / 5 | 24 / 26 / 29 |
| Supervisor shutdown request / halt acknowledgement | 6 / 13 | 31 / 33 |
| GNSS TIMEPULSE | 24 | 18 |
| Sensor buffer OE, active low | 26 | 37 |
| Geophone ADC I²C SDA / SCL | 2 / 3 | 3 / 5 |

The [Pi 4 deployment package](../sw/pi/deploy/README.md) now supplies the three-CS
overlay, 100 kHz I²C configuration and an identity-checked `driver_override`
binding tool. Its compiled overlay is merge-tested in the portable lab. The
selected physical Pi/kernel must still be boot-tested. No overlay is installed
automatically and no unrelated kernel device is detached.

```sh
python sw/tools/sensor.py live --profile sw/pi/profiles/daqhat-01.example.json \
  --seconds 60 --output sw/build/bench-001.ssrec
# Add --usb /dev/serial/by-id/<actual-head-id> when head firmware is ready.
```

Startup fails closed: every local sensor must identify and confirm settings
before effective-configuration advertisements. Live boot IDs are random per
acquisition process. The application never accesses FPGA UART, JTAG, reset or
GPIO expansion.

These drivers have modeled-bus verification, not bench qualification. Polling
timestamps represent read completion using `CLOCK_MONOTONIC_RAW`; conversion
uncertainty and physical overwritten-conversion counts are unknown. Live
batches omit `dropped_before`. Sequences count scheduled application slots;
overdue slots are skipped and unavailable scheduled samples are MISSING.
Do not infer lossless acquisition or synchronized devices from polling time.
The optional FIFO path below replaces these polling semantics for the IMUs.
Sensor self-test qualification and board-axis transforms remain follow-on work.
GNSS preserves NAV-PVT bytes and records timing evidence when requested. Legacy SCL3300
register reads are sequential, not an atomic six-axis snapshot.

## Buffered IMUs and PPS capture

Add `--fifo` to the live command with the updated DAQHAT-01 profile. Three rising-edge
GPIO requests use BCM27/22/23. FIFO watermark/overrun interrupts are hints;
a 20 ms periodic service interval also checks each FIFO. SPI transfer work is
limited to 96 seven-byte records (32 complete IMU slots) per call. A larger
backlog, hardware overrun, bad tag parity, unexpected sensor/configuration tag,
duplicate field or missing slot discards the drain, resets the FIFO and records
an overflow/error status and a MISSING marker. The existing finite restart policy
still applies. Normal scheduling delays do not discard buffered conversions.

Each sample pairs the acceleration, gyro and timestamp tags by their two-bit
slot counter. The 32-bit 25 μs device timestamp is mapped to a bracketed RAW-clock
read of the current device counter. Wrap is handled modulo 2^32; stale, future,
duplicate or backward timestamps are rejected. Unknown filter delay, oscillator
error and absolute mapping accuracy remain unqualified, so uncertainty is absent.
The raw six-axis counts are retained; no same-slot temperature is invented.
Use the polling path for temperature characterization. FIFO calibration artifacts
must therefore omit temperature and use the FIFO effective-configuration hash.

FIFO sequences enumerate delivered samples and explicit missing markers, not
all physical conversions. Physical losses remain unknown (`dropped_before`
absent), including after a FIFO flush; output queue losses remain accounted for.
No samples are emitted for a healthy empty FIFO. Acquisition shuts down rather
than continue using a failed GPIO event descriptor.

BCM24 PPS edges are recorded as events with the original kernel MONOTONIC time,
an estimated RAW time and the clock-mapping read bracket. A bracket is not total
timestamp uncertainty. No UTC value is assigned from receipt time or an assumed
NAV-PVT-to-pulse relationship. Add `--utc` to configure/read back the receiver's
timepulse and collect timing messages. [Offline UTC correlation](utc-timing.md)
creates a separate recording using explicit, recording-bound timing-error limits.
It preserves raw timestamps and omits UTC across ambiguous or unbounded intervals.

Reference: [ST AN5192, FIFO tags and timestamp correlation](https://www.st.com/resource/en/application_note/DM00517282-.pdf).

## Stationary bench analysis

`python sw/tools/measure_hat.py sw/build/bench-001.ssrec --output
sw/build/bench-001.json` streams a recording through contract/session validation
and reports per-axis mean, standard deviation, peak-to-peak, linear drift per
second, gravity magnitude, sample intervals, sequence gaps and quality counts.
PPS events produce interval statistics. Values use advertised nominal sensitivity
in package axes; no measured calibration or physical PASS is fabricated.

Repeat the same stationary acquisition with the FPGA off, idle and active.
Use `--baseline sw/build/off.ssrec` while analyzing idle/active recordings to
report mean changes and noise ratios. A zero-noise baseline yields an unknown
ratio, not infinity or a passing result. Configuration mismatches and incomplete
comparisons are rejected. These statistics require controlled test conditions;
standard deviation is not noise spectral density or an Allan-deviation analysis.

## Recovery and bounds

Each local device runs in one supervised process with one outstanding request.
A read deadline is 250 ms; configuration has four seconds. Termination and kill
each get a 100 ms reap window. An unreaped worker prevents replacement instead
of spawning more workers. Host deadlines cannot repair an uninterruptible
kernel or a physically stuck bus.

Three consecutive I/O failures or one timeout put a channel offline. It emits
MISSING samples, waits one second and attempts at most two reconfigurations in
that run. Data-not-ready is a polling miss, not a reset trigger. Recovered
settings must match the recorded configuration. Exhausted channels stay offline
until a new run. Status messages explain failures and recovery.

Geophone conversion discontinuities are separate from I/O failures: the bus can
be healthy while the host misses ADC conversions. `DataGap` survives worker IPC,
emits a discontinuity status and MISSING record with unknown loss, and clears the
consecutive I/O-failure count. It does not reset the ADC. Duplicate reads do not
extend the counter-wrap ambiguity timer. The legacy polling path does not preserve
every conversion under modeled load; those stress fixtures remain in the suite.
Exact sample timing and lossless capture are not qualified. Follow the
[bench procedure](bench-procedure.md) for physical measurements.

The current DAQHAT profile supplies `geophone_drdy` on BCM4. This starts an
autonomous reader inside the ADC worker: falling edges wake I2C reads, with a
20 ms readiness fallback if an edge is missed. Recording, other sensor workers
and parent IPC calls do not schedule these reads. Linux bus contention and
scheduling can still overwrite conversions because the ADC has no FIFO.
GPIO timestamps are not used as sample times; each sample retains its RAW
read-completion timestamp and unknown timing uncertainty/physical loss.

The worker buffers at most 256 readings and one overflow marker, delivering
at most 32 readings per IPC request. Overflow preserves the queued prefix and
then emits MISSING with unknown loss before accepting new samples. Conversion
gaps produce the same ordered marker without resetting the ADC. Actual bus faults
preserve the buffered prefix before entering bounded recovery. A reader that
makes no progress for 250 ms fails instead of returning empty drains forever.
Omit `geophone_drdy` only when deliberately testing the legacy polling path.

For continuous station capture, an exhausted channel retry budget ends that
source attempt and enters the station's 2–300 second restart backoff. A new
attempt has a new boot/session identity; discontinuities remain visible in the
recordings. Bounded command-line captures retain their finite recovery policy.
Continuous simulation retains the final scenario state beyond the one-hour
control schedule, with monotonic acquisition time and no automatic hourly reset.

The queue defaults to 64 batches (configurable 1–4096). It drops newest data on
overflow, carries known/unknown loss into the next accepted batch and retains
a final summary of losses without subsequent batches. Control messages drain
older data first and are never silently dropped. Recording retains arrival
order. A process/file failure may leave an incomplete recording.

USB chunks are at most 4096 bytes; framing has the
[contract's byte bounds](sensor-contract.md#usb-cdc-framing-and-bounds).
Partial frames expire after one second and discard through the next delimiter.
CRC, malformed Protobuf, semantic and session failures are counted and recorded.
USB permits eight open attempts per run, one second apart. Reconnect requires
identity/configuration again without erasing sequence history. USB only accepts
head identities and reserves the local Pi ID. CRC is not authentication.

Sessions retain at most four producers and 32 retired boot IDs per producer.
New boots may restart clocks/sequences. Retired boots, duplicates, backward
timestamps, contradictory known loss, stale configurations and decreasing loss
totals are rejected. Reaching a capacity requires a new recording.

## Calibration and recordings

Live HAT acquisition also writes a local `.mseed` file with raw geophone and
IMU counts. See [miniSEED capture and export](miniseed.md) for channel codes,
system-clock timing flags, simulation dates and storage limits. Keep the SSREC
companion for full configuration, diagnostics, missing data and replay.

`--calibrations` accepts a JSON list of at most 16 artifacts. Each has
`sensor_id`, `configuration_sha256`, `provenance` and `fields`. SHA-256 binds
the deterministic serialized `SensorConfiguration`, including read-back
register settings, to coefficients. Each field has explicit `scale` and `offset`
arrays (three values for vectors, one for scalars). The operation is
`SI = raw × scale + offset` in package axes; field names declare SI units.
Record the method, reference and date in `provenance`. Physical calibration
is supplied by the user, never invented by the application.

Inputs are acceleration, gyro, tilt angle, magnetic counts, IMU/tilt temperature
and DLVR 14-bit pressure counts. Finite results and sensor/field compatibility
are checked. GNSS and pressure-response temperature conversion are not
implemented. Raw values remain unchanged. The content hash becomes the
calibration ID; full artifacts are stored with recordings. Only VALID/SATURATED
samples receive calibrated values.

The streaming `.ssrec` format is `SSREC01\0`, a little-endian 32-bit JSON-header
length, header JSON, then CRC32 over magic/length/JSON. Each record contains a
little-endian `(uint8 kind, uint64 arrival_ns, uint16 length)` prefix, payload,
and CRC32 over prefix/payload. Kind 1 holds a complete delimited v1 frame;
kind 2 holds a JSON event. Metadata is bounded to 16 KiB, record payloads to
2048 bytes, and files to 64 MiB by default (up to 1 GiB). Budget exhaustion
stops acquisition with an error. There is no silent rollover or in-memory list
of a whole recording.

Replay streams records, validates CRC/order/contracts/sessions/calibration
references and computes a digest of message bytes. A final `acquisition_summary`
event marks normal completion. A complete prefix without that event is readable
but incomplete; partial/corrupt records fail. USB arrival time never replaces
remote acquisition time.

## Skylark USB

[Skylark firmware](../sw/skylark/README.md) supports the Rev A STM32F072 board.
It uses the existing framing, session checks and `.ssrec` format. The portable
software profile builds its ARM image and runs native C sensor/journal fault
fixtures. This is software verification; USB enumeration and physical sensor
qualification remain pending. [Burrowlark prototype firmware](../sw/field-head/README.md)
also has native C fault fixtures and an STM32F042 ARM build.

After generating the current descriptor, use the existing entry point:

```sh
python sw/tools/sensor.py simulate --board skylark --seconds 8 --output sw/build/air-sim.ssrec
python sw/tools/sensor.py usb --board skylark --usb /dev/ttyACM0 --seconds 120 --output sw/build/air-field.ssrec
python sw/tools/sensor.py replay sw/build/air-field.ssrec
```

The standalone `usb` command needs no HAT profile, GPIO, FPGA or Pi sensor
enable. It accepts an explicit Linux CDC path and uses the shared bounded
receiver with board identity filtering. Use a new output filename; 8 MiB is the
default capture limit. The workbench opens these captures and can switch between
board simulations/tests. Sensor IDs 10–16 retain separate gas working/auxiliary,
complete PMS/SHT responses and BMP raw/trim bytes. Gas concentration calibration
is not supplied. Native firmware's 60-second gas/30-second PM warmup is explicit
missing data; the ideal UI model intentionally has no physical warmup delay.

### Burrowlark magnetic array

B1 retains independent raw XYZ lanes and common-trigger/DRDY evidence in the
v1 recording. `groundlark.magnetic_array.average_cohort` accepts exactly four
valid members, the matching configuration envelope, an explicit device-bound
matrix/offset calibration for each lane, and an experiment-selected DRDY skew
limit. It returns a derived field estimate with lane fields and calibration ID;
it never edits raw envelopes. Missing, saturated, mismatched, uncalibrated or
late quartets are rejected. See [array operation and calibration](usb-sensor-head.md).

### Burrowlark SHT45

`groundlark.burrowlark.SHT45` provides the injected-bus, heater-off 1 Hz reference
acquisition profile. A separate write/STOP, conversion wait and six-byte read
preserve both original CRC-protected words. The Burrowlark simulation publishes
sensor 17 with RM3100 sensors 7/18/19/20 under one USB-head identity. Runtime validation,
bounded recording and replay preserve raw values, MCU clock identity and missing
readings. Target firmware implements this profile; physical qualification remains pending.

## Continuous stations

The [station deployment guide](../sw/pi/deploy/README.md) covers Pi OS Lite,
systemd supervision, Caddy LAN HTTPS, multiple acquisition sources and the shared
NiceGUI `/station` view. The persistent service uses capacity-based rolling
SSREC retention with validated session checkpoints. Interrupted recordings remain
incomplete; loss and raw precision survive segment boundaries.

Live HAT acquisition includes fitted DLVR-F50D pressure at I2C 0x28, using its
actual ±125 Pa nominal range and preserving all four response bytes. Busy data
is missing, and diagnostic/command states are faults. The sensor has no identity
or writable range register; its installed part must be checked during bring-up.

The [supervisor target](../sw/supervisor/README.md) defaults to RUN off. Its
state-machine tests and ARM link do not qualify battery operation. SensorThings,
LoRa radios and secure external forwarding remain deferred.
