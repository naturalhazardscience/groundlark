# Software validation

The runnable contract suite (`test_contract.py`) uses an independently specified
binary producer fixture and covers semantics, corruption and bounded framing.
Run `./lab.ps1 test -Profile software` from the repository root.

The acquisition, driver and Linux I/O suites run the actual application against
independent expectations: recordings, bus errors, time jumps, malformed frames,
queue limits, disconnects, a real pseudo-terminal and a hung subprocess. The
portable runner retains a bounded demo recording and replay summary.
See [the runtime guide](../../docs/sensor-software.md) for limits and commands.
`test_stimulus.py` checks independent physical/raw-count expectations, control
boundaries, deterministic noise, GNSS movement, timed faults and scenario export
followed by byte-identical regeneration through the actual CLI.

`test_hat_signals.py` exercises a fixed eight-second capture through production
Pi sensor drivers on modeled register/packet buses. It measures frequency, gain,
phase, gravity, gyro/tilt consistency, inter-IMU agreement, GNSS motion and sample
timing. Negative controls prove that physically wrong but well-framed data fail.
The software profile retains `hat-signals.ssrec` and `hat-signals.json`; the UI's
**Test selected board** button runs the same analyzer and displays its exact capture.
These thresholds apply to ideal models, not unqualified physical hardware.

`test_pressure_response.py` measures 1/5/12.5/20 Hz pressure tones at
0.05/0.1/0.5 Pa through the SDP32 driver and modeled averaging bus at 200 Hz.
The 80 Hz tone stays out of the detection band; a 180 Hz negative control
exposes residual aliasing. Alternating 1 ms service delays preserve interval
bounds and agree with an independent integral reference. `test_sdp32.py` covers CRC, product
identity, read-interval bounds and unknown-window recovery; the acquisition
suite verifies `DataGap` transport through a real worker process without a reset.
The portable profile retains `pressure-response.json` alongside the signal bench.

`test_fifo.py` checks independent FIFO tag vectors, buffered sample preservation,
counter/timestamp wrap and concealed gaps, overrun rejection, recovery and the
driver-to-runtime-to-recording path. `test_deployment.py` compiles and merges the
Pi overlay with actual device-tree tools, checks five chip selects, refuses wrong
SPI bindings and exercises the GPIO event ABI. `test_measurements.py` checks
known moments, SI conversions and incompatible bench-comparison rejection.
None of these substitutes for live Pi/kernel/sensor qualification.

`test_utc.py` exercises GNSS timing configuration/readback, fragmented/corrupt
UBX, PPS association faults, leap/midnight guards and UTC-copy replay through the
real correlator. `test_bench.py` proves missing measurements/limits cannot pass,
fixed power limits reject violations, and changed evidence hashes are rejected.
See [UTC timing](../../docs/utc-timing.md) and [bench procedure](../../docs/bench-procedure.md).

Keep small deterministic input fixtures here. Put generated logs, traces and
coverage in the portable lab's disposable workspace. Reserve bounded waveform
capture for failures. Add runnable profiles when their implementations and
acceptance criteria exist; do not substitute placeholder passes for integration.

See the [simulation roadmap](../../docs/portable-lab.md#next-simulation-layers).

`test_geophone_timing.py` advances the ADC clock independently of the four-channel
polling loop, with I2C wire delays, clock tolerance and long scheduling stalls.
It checks raw-frame provenance, honest missing/timing fields and continuity
recovery without hardware reset storms. `acquisition-stress.json` retains the
six speed/clock cases; its throughput qualification remains false. The worker
tests also exercise the new conversion-gap exception over actual subprocess IPC.
These tests do not run on a Raspberry Pi or establish its maximum acquisition rate.

`test_drdy.py` exercises autonomous geophone capture, a paused IPC consumer,
bounded overflow with ordered unknown-loss markers, terminal faults after a
valid buffered prefix, falling-edge wire records and recording/recovery semantics.
It also rejects a stuck reader that would otherwise return empty healthy drains.
Physical ADC throughput and timing remain unqualified.

`test_fpga_link.py` checks independent framing/CRC, transfer failures at every
stage, late responses, stale results, dropped ACKs, readback faults, ownership
restoration and SIGTERM isolation. `test_fpga_evidence.py` injects timing and
report-coverage failures. The FPGA stage additionally runs the real Python client
against RTL pins, rather than relying only on a byte-level mock peer.
Physical qualification follows the [bench procedure](../../docs/bench-procedure.md).

`test_skylark.py` compiles the actual Skylark C drivers and encoder on Linux,
then validates their output with the independent Python protobuf/COBS receiver.
Fixtures cover startup missing data, checksums, ADC counter discontinuities,
absent devices, queue overflow, suspend/reconnect, and suspend during sensor
configuration. A two-page flash fixture interrupts each word erase and halfword
write around page rollover. The native stream also passes through standalone
USB capture and workbench replay. These checks do not emulate STM32 instructions
or establish physical USB timing. The profile additionally links an ARM image
and retains its ELF, binary, map and size/hash metadata.
