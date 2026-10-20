# Groundlark FPGA HAT — DAQHAT-01

Underside TP90–TP93 provide passive calibration probe access; see the [bench calibration guide](../../docs/calibration.md). No additional GPIO or enclosure opening is required.

The active 140 × 56 mm, six-layer Trenz carrier combines three XYZ IMUs and
an ADS122C04 input for an external Racotech geophone, plus a fitted SDP32-125PA
infrasound pressure sensor on I2C1 (0x21), with a 200 Hz averaged acquisition
profile targeting the [1–20 Hz landslide research band](../../docs/sensor-response.md).
The stack is Raspberry Pi,
DAQHAT-01, then Trenz TE0712-03-81I36-A. Physical qualification remains pending.
J90 uses a horizontal Phoenix 1803280 header with the existing 1803581 cable
plug. Pin order remains positive, negative, shield.

MAX-M10S GNSS uses Pi I²C1 and BCM24 PPS, with a side-facing SMA and a
TPS2553 antenna fault limiter. ISO1640 side 2 faces the Pi/GNSS bus. J130 feeds
the separate MSPM0L1106 supervisor and 5.115 V Pi supply; battery policy and
physical qualification remain pending; prototype MCU firmware is implemented.
See [GNSS setup](../../docs/gnss-hardware.md) for the matched RF input and
[external pressure filter](../mechanical/daqhat-01-pressure/README.md) for the
simulation-defined pneumatic accessory; it is outside the PCB package.

J83 takes a Nexys Video-compatible 12 V, center-positive 5.5/2.1 mm adapter
rated at least 3 A. It faces the opposite edge from the geophone. U80 supplies
the FPGA independently of the Pi, with a 3 A output allocation; SW80 turns this
supply off/on. The first 25 mm of the extension contains FPGA input protection and conversion. Check the documented voltage, thermal and enclosure limits before
building; the supply remains an unqualified prototype.

- [Electrical source](elec/hat_trenz.ato)
- [Placement inputs](layout/placement.json)
- [Routed KiCad project](boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pro)
- [Native routing snapshot](boards/groundlark-daqhat-01/groundlark-daqhat-01.ses)
- [Hardware and power specifications](../../docs/trenz-hat.md)
- [Pi and external source budgets](../../docs/power-supplies.md)
- [Sensor bandwidth and timing](../../docs/sensor-response.md)
- [Assembly instructions](../../docs/stack-assembly.md)

Build target: `trenz_hat` in [hw/ato.yaml](../ato.yaml). Use the root portable lab
for validation. `simulation/` contains bounded supporting-circuit models;
`mechanical/` retains earlier mechanical artifacts with their recorded status.
FPGA sources remain under [sw/fpga/](../../sw/fpga/README.md).

Assembly uses an 8.5 mm JLCPCB socket, two external GPIO risers and measured
supports (28.06 mm nominal Pi gap). Sensor supply and bias returns have local
ground stitches. Only the two RF inductor stock observations were refreshed on 2026-10-20; see [JLCPCB assembly](../../docs/jlcpcb-assembly.md).

D90 uses TI **TPD2E2U06QDCKRQ1 / JLCPCB C915089** as the pin-compatible
replacement for TPD2E2U06DCKR. Its SC-70 footprint and routing are unchanged.
The 190 fitted placements have 72 exact-MPN BOM lines, all with catalog
mappings. L140/L141 use Murata LQW15AN56NG80D / C1330587 and
LQW15AN3N6G80D / C412276 as documented assembly substitutions. The RF model
uses these selected parts; the sensor-acquisition/UI simulator is unchanged.
U23 uses the redesigned SDP32-125PA circuit and driver. Supplier geometry remains
unverified for 53 placements, so the matching Gerber/BOM/CPL package remains a
review package; see the assembly guide before ordering.

The revised signal routing passes the expanded adjacent-layer coupling model: all
217 evaluated pairs meet the 0.20 V allocation; worst excursion is 0.188 V.
The full build retains the supplier-placement release gate.
L141 is a provisional 3.6 nH VNA tuning position; D130 junction-temperature
qualification remains open. See [simulation scope](../../docs/simulation-validation.md).

Use the [R3 enclosure](../mechanical/daqhat-01-case/README.md) for the 140 × 56 mm
board. It adds power-wing supports, a rear DC opening opposite the geophone and
switch access. First-print fit and thermal qualification remain pending.

## Pi power supervisor

J130 accepts **8–18 V DC** from an externally protected battery/controller.
U130 is TI MSPM0L1106TRHBR; U131 powers it continuously while U132/U133 supply
and disconnect the Pi through header pins 2/4. The combined Pi/HAT allocation
is 3 A at nominal 5.115 V, for the Pi 4 stack. Do not simultaneously power the
Pi through USB-C. Keep J83's separate 12 V FPGA input independent.

Battery thresholds and delays are configurable placeholders, shipped disabled
in [power-policy.example.json](../../sw/pi/deploy/power-policy.example.json).
Prototype MCU firmware is implemented; physical power qualification remains pending. An
unprogrammed MCU leaves the Pi off; fitting the JP130 shunt provides manual
bench operation. Remove it before automatic supervision. See the
[operating specification](../../docs/power-supplies.md#pi-supervisor-and-battery-input).

## GNSS timing

U21 is a MAX-M10S-00B on Pi I2C1 (0x42); BCM24/header 18 captures PPS.
J140 is a side-facing SMA for a 3.3 V active antenna drawing at most 20 mA.
The 140 x 56 mm outline and independent FPGA power remain unchanged. Use the
updated R3 enclosure with its +X antenna access slot. See [antenna setup](../../docs/gnss-hardware.md)
and [timing capture/correlation](../../docs/utc-timing.md). Browser tests cover
modeled lock/PPS loss and recording/replay; physical millisecond alignment remains unqualified.
