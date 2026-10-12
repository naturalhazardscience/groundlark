# DAQHAT-01 physical bench procedure and report

Burrowlark B1 has a separate [array timing, calibration and noise procedure](usb-sensor-head.md#calibrated-averaging-and-noise).
Its four-sensor timing, magnetic cross-talk, thermal behavior and noise floor remain
physically unqualified; passing HAT or native software tests does not qualify them.

Use the [calibration procedure](calibration.md) for PCB probe points, electrical injection, six-face IMU measurements and versioned calibration evidence. A static gain/offset fit does not satisfy the dynamic response or timing checks below.

**DAQHAT-01 GNSS revision:** MAX-M10S-00B uses Pi I2C1 at 0x42 and
BCM24 (header 18) for PPS. The Racotech/ADS122C04 geophone input remains on
I2C 0x40 with DRDY on BCM4. GNSS provides a clock reference; sample/filter
latency and multi-station millisecond alignment require physical measurement.
See [antenna setup and RF limits](gnss-hardware.md).

This procedure qualifies the assembled Pi/DAQHAT-01/Trenz stack. It is separate from
preparing a prototype fabrication submission. Physical tests run when an assembly
exists; missing physical evidence is recorded as incomplete, not fabricated by a
simulation. The user owns fabrication approval.

## Prepare the report and instruments

Create one report folder under ignored `sw/build/` or dedicated lab storage.
Keep authored procedures here and raw captures outside Git. Retain the completed
report and its attachments with the hardware revision when the bench run ends.

```sh
mkdir -p sw/build/bench-001
python sw/tools/bench.py init sw/build/bench-001/report.json
python sw/tools/bench.py check sw/build/bench-001/report.json
```

The initial check intentionally returns **incomplete**, exit code 2. Record the
operator, UTC date, board serial/revision, software commit, Pi/kernel, geophone serial and calibration,
FPGA bitstream or explicit unconfigured state, instruments/calibration references,
mounting, cooling, temperature range, sample/filter settings and power cases.
Enter application targets for geophone timing error and input noise, inter-IMU skew, acceleration noise,
thermal bias change and FPGA noise ratio before evaluating those tests.

Use a current-limited adjustable supply, DMM, oscilloscope with suitable differential
voltage/current measurements, electronic load, logic analyzer, temperature probes,
calipers and a low-noise differential signal source. Timing qualification needs a
shared instrument timebase of known accuracy. Motion tests also need known
orientations and a reference accelerometer/shaker for frequency/phase characterization.

Store scope exports, logic traces, `.ssrec` recordings, analyzer JSON and fit photos
inside the report folder. Generate each evidence entry with:

```sh
python sw/tools/bench.py evidence sw/build/bench-001/report.json sw/build/bench-001/trace.csv
```

Copy the returned relative path/hash into the relevant check's `evidence` list.
Every measured check needs evidence. The checker rejects missing/altered attachments,
outside-folder paths and wrong units. Files are capped at 64 MiB each. It checks
supplied measurements and evidence integrity; it cannot certify instrument setup
or infer physical truth from a filename.

## 1. Power and partial-power operation

1. Inspect assembly/polarity/shorts unpowered. Begin with Trenz unconfigured and
   external power current limited. J83 pin 1 is positive, pin 2 ground. Use the
   documented 12 V ±5% source. The onboard converter supplies the Trenz input;
   verify its 3.201–3.399 V operating limits at the module. The Pi sensor supply
   remains separate.
2. Capture cold startup at J83, the module management rail and the sequenced I/O
   rail, plus input current and reset/enable/PGOOD where accessible. Evaluate
   ramp/sequence/reset behavior against the installed Trenz revision and regulator
   documentation. The ordinary operating minimum is not a requirement at t=0.
3. Once operating, measure minimum/maximum module management voltage during idle,
   intended FPGA load, Pi stress and 0.1↔3 A characterized load steps. Record
   actual edge rates and ringing. The simulation's 100 µs ramp is not a substitute
   for faster measured switching behavior. Avoid double-counting FPGA plus dummy
   load: the total initial operating envelope is 3 A.
4. After thermal settling, measure the complete positive-and-ground loop drop
   differentially at a known current: R = ΔV/I. Include connectors, fuse, copper
   and return paths. Record probe locations and uncertainty.
5. Repeat Pi-only, FPGA-only, both-powered and both turn-on/off orders. Capture
   leakage/back-power, reset/OE levels and interface behavior against component
   limits. Summarize `power_sequence` and `partial_power_isolation` only after all
   cases are covered, with individual traces in the evidence.

Fixed report limits: operating module rail **3.201–3.399 V** and hot loop
**≤0.030 Ω**. If limits fail, correct supply/path/decoupling/protection and repeat
affected cases. Document measured inrush and component temperatures in the notes;
they are evaluated against the actual component ratings, not invented thresholds.

## 2. Mechanical fit

Assemble the intended Pi, two SSQ risers, DAQHAT-01, Trenz, cooler and four straight supports.
Check full socket engagement and pin orientation, spacer seating without board
bow, fastener clearance, geophone/power-plug withdrawal and cooling access. The
internal FPGA link needs no ribbon cables or external JTAG connector. Measure
closest gaps and record photos. The nominal Pi-to-HAT gap is 27.179 mm; fit depends
on actual socket seating/cooler/cables. A dimensioned mock-up can precede assembly.
Set `connector_cable_cooler_fit=true` only after the intended configuration fits.

## 2a. Internal FPGA programming and transport

1. Follow the [host-link bring-up](fpga-host-link.md#bring-up) on the selected Pi 4
   and kernel. Record JTAG IDCODE, actual TCK frequency and successful volatile
   programming of the recorded bitstream. Set `fpga_jtag_programming=true` only
   after the real scan/load passes; a simulated mailbox is insufficient.
2. Capture BCM25 arm, switch select/request/OE, SCLK/CS and JTAG at both sides
   during SPI-to-JTAG-to-SPI transitions, startup, normal termination and recovery
   from a control-bus failure. Confirm isolation before ownership/direction
   changes. Check Pi-only and FPGA-only power in section 1, including rail ramps.
   Record `fpga_mode_handoff` separately from `partial_power_isolation`. SIGKILL
   and loss of the host have no hardware watchdog; exercise the documented
   disarm/reboot recovery before manually changing ownership.
3. Measure the signals **at the FPGA-side pins**, including the switch and series
   resistors. Enter maximum SPI clock (initially 1 kHz–1 MHz), minimum SCLK high
   and low (each at least 500 ns), and minimum CS setup/hold/inactive (each at
   least 1000 ns). Include instrument uncertainty. The checker enforces these
   conservative bring-up limits; Linux overlay settings alone are not evidence.
   Inspect overshoot, ringing, logic levels and MISO output release against the
   actual devices' limits; retain scope traces and interpretation with the report.
4. Run a recorded loopback soak covering payload lengths 0–192, sequence wrap,
   repeated mode handoffs and concurrent sensor/CPU/storage load. Record duration,
   transaction count, payload seeds, voltage/temperature and all errors. Require
   `fpga_loopback_errors=0` for this valid-traffic soak; report deliberately injected
   faults and recovery separately. A numerical zero without captures and test
   conditions does not establish a bit-error-rate guarantee.

## 3. Geophone, IRQ and acquisition timing

1. Follow [Pi deployment](../sw/pi/deploy/README.md) and capture with `--fifo`.
   The GNSS revision accepts `--fifo --utc`; capture BCM24 PPS and retain measured timing bounds. Read back ADC configuration;
   retain raw counts, conversion counters and host monotonic timestamps.
2. Capture ADC DRDY, I²C transactions, IMU IRQ and SPI activity on a common
   logic-analyzer timebase. Measure conversion-to-read delay, delivered rate,
   latency variation, inter-IMU skew and drift under CPU/storage/network load,
   with the FPGA off, idle and active. The current profile uses a dedicated
   falling-edge DRDY reader with bounded delivery buffering; timestamps remain
   RAW read-completion times. It does not turn DRDY into a hardware timestamp.
   Compare against the legacy polling profile (omit `geophone_drdy`) and retain
   both results. Modeled polling-loss findings remain open until actual throughput,
   shared-I2C contention and timing bounds are measured on the assembly.
3. Stop/resume acquisition deliberately. Confirm IMU FIFO behavior and that
   ADC overwrites, integrity faults and ambiguous counter wraps produce faults
   with unknown physical loss. The ADC has no FIFO. Confirm recovery without
   relabeling invalid or saturated samples as valid.
4. Apply calibrated differential inputs within the ADC common-mode and input
   limits, including a 10 Hz sine and a frequency sweep. Measure polarity,
   gain, clipping and recovery. Independently move the vertical geophone with
   a known reference to establish its mechanical response and polarity. An
   electrical signal-generator test alone does not calibrate the geophone.
5. Populate `geophone_polarity_response`, measured maximum geophone timing
   error, inter-IMU skew and recovery checks with the retained traces. Choose
   timing limits from the research use case before evaluating acceptance.

Start with 10 minutes per load state and repeated cold starts, then extend
through thermal settling and the intended operating envelope. No absolute UTC
qualification is implied by this board or a passing relative timing test.

## 4. Noise, thermal drift and FPGA coupling

For the current assembly, measure SENS_3V3 at the LDL1117 output and GEO_AVDD
at the ADC with short probe returns, including startup and sensor/FPGA load
changes. Confirm the 3.18–3.42 V sensor rail envelope and absence of sustained
oscillation at the intended temperature/load corners. Record effective C42
capacitance or manufacturer bias/temperature evidence; require at least 4.7 µF.
Do not treat the regulator's broadband output noise as geophone input noise.

Measure geophone alias rejection by injecting a calibrated differential sweep
above Nyquist as well as in band, with the recorded ADC rate/filter settings.
Keep input common mode and amplitude within the ADS122C04 limits. Retain input
frequency/amplitude and output spectral levels so aliases can be distinguished
from harmonics and interference. Acceptance limits must be set before testing.

Use the [response budget](sensor-response.md) to choose injection points. For
Groundlark include 0.5/1/4.5/10/27/100 Hz, frequencies around the actual ADC
Nyquist limit, and above it (including 400 Hz, which aliases near 71.37 Hz at
the nominal internal clock). Measure IMU acceleration and gyro separately on
a reference shaker at every rate being used, including phase and stopband
response. Record the source/ADC clock estimates; do not assume exactly 330 Hz.

For Skylark, use a calibrated cell-current simulator to measure WE and AE gain,
phase and settling separately, then jointly. Include 0.01/0.1/1 Hz, frequencies
around 2.083 Hz and 4.167 Hz, 50/60 Hz and switching interference. Observe
individual raw channels before compensation. Repeat with USB and the PMS fan
active, including power disturbances. The nominal 60 ms WE/AE offset must not
be hidden by pairing rows by position. Define the allowed alias error in
input-referred current or calibrated gas units before accepting a filter.
If rejection is insufficient, revise bandwidth or acquire faster and filter
before reducing the rate; a smoother applied after aliasing is not a remedy.

With actual gas cells, use a controlled concentration step and an independent
reference monitor to measure the complete cell/hood delay and recovery at
representative airflow. Repeat with the hood removed to distinguish cell
response from enclosure exchange. A T90 limit does not qualify power-up
settling or potentiostat stability. Pressure, humidity, temperature and PM
require their own reference/step checks; their 1 Hz publication rate does not
prove 0.5 Hz physical bandwidth. Preserve raw data and predeclared limits;
missing phase, noise, alias or enclosure measurements cannot pass qualification.

Qualify connector handling transients separately with the selected D90, both
powered and unpowered. Use a defined ESD fixture and severity, retain pin/rail
waveforms, and compare leakage, offset, gain and recovery before/after stress.
The suppressor's clamp is not the ADC's rail limit; the series resistors and
filter must be included. Missing severity, limits or measurements cannot pass.
This does not qualify lightning exposure or sustained external overvoltage.

Record identical sensor settings and rigid mounting with FPGA off, idle and active;
repeat with cooling off/on where thermally permissible. Keep external vibrations
and temperature traces as controlled as practical. Retain thermal settling and
stable intervals separately. Record known orientations and a reference vibration
input for axis, gain and phase checks; package axes are not automatically board axes.

```sh
python sw/tools/measure_hat.py sw/build/bench-001/off.ssrec --output sw/build/bench-001/off.json
python sw/tools/measure_hat.py sw/build/bench-001/active.ssrec \
  --baseline sw/build/bench-001/off.ssrec --output sw/build/bench-001/comparison.json
```

The existing analyzer reports nominal-SI mean, standard deviation, trend, gravity,
sample periods and gaps. It does not yet calculate spectral density or Allan
deviation. For band-limited acceptance, use a documented filter/spectral analysis
and retain its script/settings/output as evidence. Enter worst-axis RMS over the
declared common band, worst thermal bias change and worst active/off noise ratio.
Do not compare runs with different sample/filter settings or use motion-contaminated
standard deviation as a stationary noise floor. Reference calibration and absolute
accuracy remain distinct from repeatability/noise.

## Evaluate and prepare the prototype release

```sh
python sw/tools/bench.py check sw/build/bench-001/report.json
```

Exit 0 means every supplied measurement/evidence item and application limit passes;
exit 2 means incomplete or failed checks; exit 1 means malformed input. Missing
measurements, targets, context or evidence never become a pass. Correct failed
items and repeat the affected tests with traceable revisions.

For the next **prototype fab submission**, freeze the intended DAQHAT-01 revision and
actual stack/copper/dielectric values; follow the current
[assembly requirements](jlcpcb-assembly.md) and [stack instructions](stack-assembly.md);
run the full CAD/build checks; review footprint pin numbering, BOM availability,
DNPs, drill/microvia instructions and mechanical fit; then export and independently
inspect Gerbers/drills, assembly drawings and placements from that same revision.
Retain hashes and a release manifest. Keep the physical bench report pending until
boards arrive, rather than requiring completed-board measurements before making
the first prototype.

For geophone noise, record both a shorted differential input and the connected,
stationary sensor. Convert counts to input volts using the recorded gain and
reference. Measure the defined bandwidth with FPGA off/idle/active and record
`max_geophone_input_noise_rms` against the application target. Separate ambient
ground motion from electronic noise; do not use the synthetic stimulus as evidence.

## HAT-mounted infrasound qualification

For U23, record pressure calibration and status bits, I2C rise times with the
ADC active, thermal drift with FPGA off/idle/active, and vibration/fan coupling.
Measure the inlet/reference-volume and tubing transfer function with a traceable
pressure stimulus; record tubing geometry and mounting strain. Missing response
or noise measurements do not establish an infrasound operating band.

### DAQHAT-01 12 V FPGA input

Record the adapter model, 12 V output tolerance, plug polarity and cable. Verify
J83 is isolated from both Pi positive rails. Measure Pi-off/FPGA-on and
Pi-on/FPGA-off leakage, SW80 operation, converter EN and module EN1 timing,
startup/inrush, output ripple and FPGA load steps. Measure both module supply
connector groups differentially: the operating limit is 3.201–3.399 V and the
hot output-loop resistance target is 15 mΩ at a 3 A allocation. Record input
diode, converter and module temperatures in the intended enclosure. Repeat
geophone/infrasound noise measurements with FPGA power off, idle and active.
PGOOD and offline calculations alone cannot pass these checks.

## TI Pi power supervisor

Keep the FPGA adapter disconnected for solar-field power measurements. Use a
current-limited 8–18 V bench source at J130 and an open JP130 shunt for supervised
operation. Target MCU firmware, Pi shutdown integration and a qualified battery
profile are required before running automatic shutdown/recovery tests. JP130 is
only a manual bench override while those remain pending.

Measure both Pi 5 V contacts under workload, including GPIO riser/contact loss,
at minimum/nominal/maximum input. Record startup and 3 A combined-load ripple,
current limiting and enclosure temperatures. Confirm Pi-off leakage with the
FPGA on/off and no USB-C source. Record idle battery current across temperature.
Inject a falling supply, ADC/configuration fault, absent halt acknowledgement,
reset during shutdown and repeated failed boots. Verify bounded shutdown, full
rail discharge, restart hysteresis and minimum off time. Test geophone noise
with the Pi converter running. Missing limits or measurements remain failures;
CAD, arithmetic and configuration validation are not hardware qualification.
