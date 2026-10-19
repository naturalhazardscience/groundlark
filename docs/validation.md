# Hardware validation and release gates

## Current DAQHAT-01 pressure, GNSS, calibration and power revision

The 140 × 56 mm board includes MAX-M10S-00B GNSS on I2C1, BCM24 PPS and a
side-facing SMA with a 3.3 V active-antenna supply. BCM4 remains geophone DRDY;
BCM6/13 retain the TI power-supervisor handshake. FPGA interfaces and the
independent adapter supply remain unchanged. Native checks report zero ERC
findings, zero DRC findings and zero unconnected items. The complete
13,058-track/via SES reproduces identical copper. Independent pin/no-connect,
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

The full portable profile executes 26 stages. Its supplier placement acceptance
gate remains blocked: 52 of 188 placements lack verified numbered supplier pads.
All 71 catalog identities have dated stock observations; 136 placements fit frozen
supplier geometry. Review export tests preserve exceptions rather than clearing
the release gate. GNSS pin/layout checks include missing bypass and ground-stitch
faults. No physical
power, noise, thermal, battery or RF qualification is implied. See
[power operation](power-supplies.md#pi-supervisor-and-battery-input) and
[assembly status](jlcpcb-assembly.md).

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
