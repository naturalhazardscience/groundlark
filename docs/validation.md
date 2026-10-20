# Hardware validation and release gates

## Current DAQHAT-01 pressure, GNSS, calibration and power revision

The 140 × 56 mm board includes MAX-M10S-00B GNSS on I2C1, BCM24 PPS and a
side-facing SMA with a 3.3 V active-antenna supply. BCM4 remains geophone DRDY;
BCM6/13 retain the TI power-supervisor handshake. FPGA interfaces and the
independent adapter supply remain unchanged. Native checks report zero ERC
findings, zero DRC findings and zero unconnected items. The complete
13,099-track/via SES reproduces identical copper. Independent pin/no-connect,
power, RF geometry, fabrication and analog-layout checks pass.
The antenna limiter and local bypasses are routed; ISO1640 side 2 faces GNSS.
Pi rail calculations include resistor temperature drift and an unmeasured
±20 mV ripple/transient allowance. Thermal, short-circuit and timing acceptance
still require physical measurements.

Four underside calibration pads expose ground, geophone bias, analog supply and
data-ready without adding GPIO. Static calibration fits measured gain/offset
with instrument/configuration binding and retains raw counts. Local miniSEED
export preserves timing gaps and requires valid UTC intervals. See the
[calibration guide](calibration.md) and [timing limits](utc-timing.md).

The portable software checks include device-tree checks, contract compatibility,
driver fault injection, firmware builds and FPGA loopback.
The workbench HTTP and scene checks pass; browser interaction for the pressure
revision remains unverified. Its Groundlark
signal bench passes 12/12 checks on 4,072 modeled samples from all six HAT sensors.
Pressure uses the production SDP32 driver on a modeled I2C bus, including
product identity, signed raw counts, CRC and scale validation. Native checks
cover the pin map, NCs, three pegs, split ground/paste lands and open center.
Actual pneumatic response, noise, mounting and thermal drift require measurement.
Antenna open/short, lock-loss and missing-PPS controls preserve independent
sensor acquisition. Fault/recovery, replay and rejection of invalid UTC references
are covered. Supply checks include Pi temperature corners, invalid envelope
inputs, antenna fault current and the added GNSS bypass charge.
Modeled UTC correlation and miniSEED round trips do not qualify physical 1 ms
sample alignment; receiver RF, acquisition latency and filter delay need measurement.

The 159 × 118 × 75 mm R3 enclosure adds a side SMA slot. Geometric/component
checks, 556 native PCB underside checks and 25 enclosure fault tests pass.
The README renders use current CAD. Physical first-print fit remains pending.
The supervisor battery policy stays disabled with unset thresholds; prototype
target firmware is built and tested with native fixtures. Hardware shutdown
integration remains unqualified.

The full portable profile executes 26 stages. All 314 software tests pass.
The final hardware regression run passes 235 of 236 tests; its sole error is
the supplier placement acceptance gate. It remains blocked because 52 of 189
placements lack verified numbered supplier pads.
All 71 catalog identities have dated stock observations; 137 placements fit frozen
supplier geometry. Review export tests preserve exceptions rather than clearing
the release gate. GNSS pin/layout checks include missing bypass and ground-stitch
faults. No physical
power, noise, thermal, battery or RF qualification is implied. See
[power operation](power-supplies.md#pi-supervisor-and-battery-input) and
[assembly status](jlcpcb-assembly.md).

The 100 Hz SDP32 profile uses average-until-read for a 1–20 Hz landslide
research target. Independent tests measure sub-pascal tones across that band,
reject unaveraged/corrupt data and exercise late-window recovery through real
worker IPC. The retained `pressure-response.json` models ideal conversion
averaging and explicitly shows residual aliases; it does not establish a
pneumatic filter or minimum detectable signal. Raw frames and optional timing
bounds retain backward compatibility with older SDP32 and DLVR recordings.

The carrier control audit now rejects loading MODE or confusing NOSEQ with EN1.
Its documented module baseline is Trenz CPLD REV03. Physical bench report v4
requires installed firmware evidence, pressure gain/phase/noise/alias checks,
shared-bus signal integrity and GNSS RF evidence. Missing limits or measurements
remain incomplete; software and geometry results cannot satisfy those checks.

## Native copper regression checks

`copper_resistance.py` extracts filled native copper and through-barrels with
an explicit stackup, conductor temperature and plating assumption. Analytical
series/parallel fixtures, disconnected networks, missing distribution pours
and missing vias exercise the model independently. Refinement from 0.1 to
0.05 mm checks the Pi distribution estimate; connector resistance, thermal
rise and regulator dynamics still require measurement. Model reserve is an
engineering allocation, not a statistical confidence bound.

The GNSS check reads the actual 0.0994 mm dielectric and 0.17 mm back-layer
series route, including reference-plane coverage. The uncoated microstrip
estimate is approximately 49.7 Ω; pads, soldermask and coplanar copper require
supplier field-solver review. A 0.3 mm route is a regression fault.

The adjacent In2/In3 screen reports parallel signal lengths within three
dielectric heights of edge separation. Its 5 mm aggregate pair limit is a
layout regression limit, not a crosstalk acceptance voltage. Perpendicular
crossings and distant controls are independent fixtures. The existing
0.1088 mm interlayer gap remains part of the stock stackup; physical signal
integrity is unqualified.

Hardware-tool checks raise explicit exceptions even under `python -O`.
Optimization-mode fault tests verify that checks cannot silently disappear.
The IMU driver disables both I2C and I3C while using SPI and validates those
registers after configuration. TCA9534 initialization writes a low latch
before enabling P0/P1 outputs; grounded P2–P7 remain inputs. R118 holds the
Pi UART receiver high while U51 is disabled.

## Reproducible checks and release limits

Run the [portable lab](portable-lab.md) for the three current hardware targets:
DAQHAT-01, Burrowlark and Skylark. It checks compiled circuits, independent
pin fixtures, native ERC/DRC, routing replay, supporting-circuit simulations
and the software profile. The shared sensor fixture is fixed independently of
current CAD and includes missing-pin and incorrect-supply fault tests.

See each product's guide for current electrical and mechanical limits.
[Shared SPICE models](../hw/shared/simulation/README.md) cover 18 sensor/USB
support-circuit cases; FPGA power and geophone checks are separate.
CAD and behavioral checks do not establish physical power, noise, timing,
USB, thermal, RF or assembly qualification. Fabrication approval remains
with the user. Follow the [bench procedure](bench-procedure.md) and preserve
missing measurements as unqualified results.
