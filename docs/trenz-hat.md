# Groundlark DAQHAT-01 — Pi-outline Trenz carrier

Four bare underside calibration pads TP90–TP93 provide ground, geophone VCM, AVDD and DRDY access. No Pi/FPGA pins or active injection circuitry are added. The 140 x 56 mm outline and R3 enclosure remain unchanged; see [calibration](calibration.md).

The front silkscreen carries a 7 mm monochrome Groundlark lark/waveform above
the model name. It is native KiCad polygon artwork, included in layout rebuilds
without adding BOM parts. See the [current 3D view](../hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/3d.png).

**DAQHAT-01 revision:** six internal QSPI-reserved wires, retained UART and
switched Pi-driven JTAG replace external expansion connectors and ribbons.
See the [host-link circuit and bring-up guide](fpga-host-link.md). Pi 4 initially
uses SPI6; native quad transfers are not supported by its controller.

An external Racotech vertical geophone uses an ADS122C04 input; MAX-M10S-00B GNSS adds a UTC reference through I2C1 and BCM24 PPS. See [GNSS hardware and antenna setup](gnss-hardware.md).

The Pi/GNSS bus uses ISO1640 side 2 for compatible low logic levels. Antenna
power includes a TPS2553 50–100 mA fault limiter and local RF bypassing. The Pi
supply is 5.115 V nominal, with temperature drift and a bench ripple/transient
allowance included in the [power envelope](power-supplies.md).
Its Phoenix 1803280 J90 header opens parallel to the PCB toward the geophone;
the 1803581 cable plug retains positive, negative and shield pin order.
See the [geophone circuit and acquisition](geophone-input.md).

DAQHAT-01 is a **140 × 56 mm, six-layer FR-4** Raspberry Pi acquisition HAT.
Electrical source: [`hw/groundlark-fpga-hat/elec/hat_trenz.ato`](../hw/groundlark-fpga-hat/elec/hat_trenz.ato).
CAD: [`groundlark-daqhat-01.kicad_pcb`](../hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb).
[Burrowlark (DAQUSB-01)](usb-sensor-head.md) and Skylark USB sensor heads
have separate builds.

## Stack and sensor placement

From bottom to top: Raspberry Pi, Groundlark DAQHAT-01, **TE0712-03-81I36-A**.
The FPGA stays on top for heatsink access. The HAT keeps the three LSM6DSO IMUs
and ADS122C04 geophone input; the dedicated inclinometer is removed. The fitted
Sensirion SDP32-125PA-TR-250PCS pressure sensor U23 is centered at (6,29) mm,
top side, orientation 0 degrees. Its 8.5 x 5.5 mm body and 4.4 mm height clear
the Trenz outline. C24 is its local 100 nF underside bypass at (7,31.85) mm.
Keep the pressure tubing clear of the IMUs and strain-relieve it to the enclosure.
The RM3100 magnetometer remains on Burrowlark.

U23 shares isolated sensor-side I2C1 at 0x21, with ADDR grounded. Sensirion's
SDP3x digital datasheet v1.1 defines GND on pins 1/2/3/6/10/11, SCL on 5,
VDD on 7, SDA on 8 and ADDR on 9. IRQn 4 and reserved 12-16 stay unconnected.
The split center pad connects to ground; its center vent and three locating
holes must remain clear. Existing pull-ups and Pi/FPGA signals are preserved.
Maximum continuous current is 5.5 mA; 14 mA reserve remains in the 50 mA
sensor-domain allocation. Differential pressure range is +/-125 Pa.

Live acquisition uses differential-pressure compensation with average-until-read,
checks product identity, scale and each word's CRC, and preserves signed raw
pressure and temperature counts. Read completion timestamps do not qualify
conversion timing. Legacy DLVR recordings remain readable. Pneumatic response,
noise, thermal drift, vibration and actual tubing/stack fit require measurement.
The thermal flow sensing principle requires a pneumatic system response check.

Assembly must follow Sensirion's one-reflow rule: fit U23 in the last reflow
run, protect its ports, use no-clean paste, and do not wash the board. Maximum
peak is 260 C and time above 200 C is at most 150 seconds. See the
[manufacturer datasheet](https://sensirion.com/media/documents/4D045D69/6375F34F/DP_DS_SDP3x_digital_D1.pdf).

The Trenz outline occupies HAT coordinates x=30–80, y=8–48 mm, measured from
the upper-left corner. Its mounting holes are (33,11), (77,11), (33,45), (77,45)
mm. Two 100-contact connectors and one 60-contact connector mate underneath it.
The selected 4 mm carrier and module connectors give an **8 mm surface gap**.
Use four matching M3 spacers. Components under the module are low-profile;
the tall service connectors are outside its outline.

The selected bottom socket is **Megastar ZX-PM2.54-2-20PY / C7499354**, with
an 8.5 mm body. Use **two Samtec SSQ-120-02-G-D** self-nesting 1:1 GPIO risers,
each with an 8.51 mm body and 4.93 mm square tails. With the Pi header's 2.54 mm
base, this gives **28.06 mm nominal Pi-top to HAT-underside clearance**.
The model, support envelopes and assembly BOM use this stack. One riser with
this shorter J1 gives only 19.55 mm and is not the reviewed assembly.

The risers' female faces point toward the Pi. Their 4.93 mm tails fall inside
Samtec's 3.68–6.35 mm insertion range for the intermediate SSQ connection.
Megastar contact engagement, actual seating and retention must be measured on
the first assembly. Match four supports with measured spacers/shims; never force
the connectors to a nominal spacer height. The additional mating interface
requires the existing GPIO signal-integrity bench check. See [stack assembly](stack-assembly.md).

The sensor regulator assembly selection is **LDL1117S33R / C435835**;
D90 is **TPD2E2U06QDCKRQ1 / C915089**. The procurement registry binds these
compatible replacements to the source circuit and frozen supplier footprints.
All selected PCB parts require available JLCPCB stock and component MOQ 1.

C43 is beside the regulator output tab. `sensor_supply_layout.py` enforces a
4 mm maximum connected output-bypass path and 2 mm maximum local plane-return
paths for C40–C43, C93/C94 and translator ground pins 12/13. Retain the local
through-vias and filled/capped process. These limits supplement the IMU checks
below; they do not establish measured noise or regulator loop stability.

The three IMUs have matching XYZ axes and lie outside the FPGA outline:
U11 at (13,24), U12 at (24,24), and U13 at (13,36) mm. Their distance from the
FPGA outline is 17, 6 and 17 mm respectively. These planar distances do not
establish thermal or mechanical isolation. Local 100 nF bypass capacitors and
In1.Cu ground stitches are required. Connected-path limits checked by
`hw/tools/imu_layout.py` are 4 mm for VDDIO bypass, 2 mm for VDD bypass,
2 mm for capacitor ground and 2.5 mm for IMU ground-pin paths. These geometry
limits do not establish minimum noise; measure FPGA-off/idle/active coupling.

This compact stack increases thermal and electrical coupling compared with
placing the FPGA beside the Pi. Accelerometer/tilt drift and noise must be
measured with the FPGA idle and active, and cooling must avoid exciting the
motion sensors. Pi cooler compatibility needs a physical check.

## Power and interfaces

Reserve 75 mA from the Pi header 5 V rail and 150 mA from its 3.3 V rail for this HAT, including GNSS and a 20 mA active antenna. These are steady-state allocations; startup charging
and the Pi's other loads must also fit the source. See the [power supply guide](power-supplies.md)
for calculated charge, regulator dissipation and measurement requirements.

**J83 accepts 12 V DC ±5%, center-positive, through a 5.5/2.1 mm barrel plug.**
Use a supply rated at least 3 A, matching the Nexys Video adapter specification.
The jack faces board -Y; J90's geophone plug faces +Y. The board is now
140 × 56 mm, with the power section beyond the Trenz module's right edge.
The original Pi and Trenz mounting points remain unchanged. Enclosures made
for the earlier 85 mm board are superseded by the R3 enclosure with wider
clearance, a rear jack opening and power-wing supports; physical fit remains pending.

The independent FPGA power path is J83 → F80 (2 A input fuse) → D80
(reverse-polarity Schottky) → U80 (TPSM53603 buck converter) → FPGA_VIN.
D81 is a 15 V standoff transient suppressor; it is not a sustained overvoltage
disconnect. C86/C87 are 50 V ceramic input capacitors, C88 is the local bypass,
and C89 is 47 µF / 35 V input bulk. C110–C112 provide 66 µF nominal local output
capacitance; verify at least 43 µF effective after tolerance, bias and temperature.
The existing module-side decoupling remains fitted.

SW80 OFF grounds converter EN; ON enables its undervoltage divider. The nominal
turn-on threshold is 9.43 V at the protected input (approximately 9.04–9.83 V
including threshold and 1% divider corners, before the diode drop). U80 PGOOD
pulls Trenz EN1 low while the converter reports an out-of-window output. JP80
can still inhibit module sequencing. PGOOD is a coarse sequencing signal;
its thresholds do not certify the narrower Trenz supply limits.

R120/R121 set **3.326 V nominal**, with a **3 A continuous design allocation**
subject to thermal qualification. The 12 V adapter's 36 W rating does not raise
the converter's approximately 10 W output allocation. The reference, 0.1%
divider and FB-bias calculation gives 3.271–3.381 V at U80. A **15 mΩ total hot
output-loop target**, including both copper paths and module contacts, gives
3.226–3.381 V at up to 3 A. These are DC scenarios: load/line regulation,
ripple and startup/transient behavior still need measurement. Keep the actual
module management supply within **3.201–3.399 V** during operation.

The routed board uses broad rear FPGA_VIN copper, a local front output pour,
eight parallel output through-vias and nine ground/thermal through-vias under
U80. All nine carrier VIN/3.3VIN contacts are connected: J80 pads 2/4/6/14/16
and J81 pads 1/3/5/7. Ground return uses both internal reference planes.
Filled/capped processing applies to converter, MCU/load-switch thermal-pad vias
as well as the ADC supply-pad vias.
The native finite-difference copper extraction gives about 9.37 mΩ for the FPGA
loop at an assumed 85 °C, including its 20% modeling reserve; a separate 5 mΩ
contact allocation fits the 15 mΩ target. See [the extraction assumptions](power-supplies.md).
Measured current capacity, contact resistance and thermal signoff remain pending.

The Pi header does not supply FPGA_VIN or the module's sequenced FPGA_3V3 rail.
The switched Pi supply powers sensors and its side of the isolated interfaces; grounds remain
common. Sensor acquisition can run with SW80 OFF. BCM6/13 serve power management; BCM24 carries GNSS PPS.
Disarm the FPGA link before switching it off; software must treat a power cycle
as loss of FPGA state. Startup, shutdown and Pi-off/FPGA-on leakage remain bench
qualification items.

Manufacturer references: [Nexys Video power input](https://digilent.com/reference/_media/reference/programmable-logic/nexys-video/nexys-video_rm.pdf),
[TPSM53603](https://www.ti.com/lit/ds/symlink/tpsm53603.pdf),
[PJ-102AH](https://www.sameskydevices.com/product/resource/pj-102ah.pdf),
[B340A](https://www.diodes.com/part/view/B340A), and
[SMAJ15A](https://www.diodes.com/part/view/SMAJ15A).

The module's sequenced 3.3 V output powers the exposed FPGA banks and the B
side of the TXU0202 UART isolator. Pi GPIO25 enables that interface, with a
pull-down keeping it disabled at startup. GPIO17 asserts application reset
through an open-drain transistor; the supervisor also holds reset during a
low FPGA I/O supply. FPGA configuration reset is separate on JP81.

| Function | Module pin | Carrier pad |
| --- | --- | --- |
| Pi TX → FPGA UART RX | JM2-11, B14_L8_N | J81-12 |
| FPGA UART TX → Pi RX | JM2-13, B14_L8_P | J81-14 |
| Application reset, active low | JM2-14, B14_L10_N | J81-13 |
| Configuration reset | JM2-18 | J81-17 |
| JTAG TMS / TDI / TDO / TCK | JM2-93 / 95 / 97 / 99 | J81-94 / 96 / 98 / 100 |

Carrier/module connector numbering swaps odd and even pins. See the complete
[`trenz-pin-map.json`](trenz-pin-map.json). Dedicated JTAG now reaches the Pi
through U100. R80 keeps JTAGEN low for the Trenz CPLD's FPGA path. JP80 disables
module power sequencing when shunted; JP81 asserts configuration reset.
NOSEQ has a defined low bias; its behavior depends on the module CPLD firmware.

## Internal GPIO allocation

Nine of the 158 ordinary module I/Os are connected: six SPI/QSPI signals plus
UART RX/TX and application reset. The remaining 149 ordinary I/Os are deliberate
no-connects. J84-J89, their fanout and the four flex cables are removed. Ethernet,
GTP, dedicated connector clock inputs and unused management contacts remain
unconnected. The UART service header J4 is retained.

The [GPIO contract](trenz-gpio-breakout.csv) records every ordinary module I/O.
Independent [module](trenz-gpio-module.csv) and [ground](trenz-ground-module.csv)
fixtures retain their vendor schematic transcription. The audit checks all 260
module contacts, including no-connects; JM1.12 is Ethernet RD_N, not ground.
Bank supplies remain at 3.3 V. There are no externally exposed raw FPGA GPIOs.

## Fabrication stack

The cost-reduced revision uses conventional **six-layer FR-4**, nominal 1.6 mm,
with through-vias only. Ground references are In1.Cu and In4.Cu. Signal layers
are F.Cu, In2.Cu, In3.Cu and B.Cu. Minimum signal width/clearance is
0.125/0.10 mm; vias have 0.30/0.40 mm drills and at least 0.45 mm pads.
Native custom rules additionally enforce via copper, SMD pad and hole clearances.
All through-vias are epoxy filled and copper capped, including solder-pad sites.

The recorded stock reference is JLC06161H-3313: 1 oz outer / 0.5 oz inner copper.
Its published copper/dielectric sum is 1.5384 mm; 1.6 mm is the nominal ordering
and mechanical-model thickness (+/-10% supplier tolerance). CAD mask thickness
and dielectric electrical constants are illustrative. Do not request custom
lamination to force the stock values to sum to 1.600 mm. No controlled impedance
is claimed. See [JLCPCB assembly](jlcpcb-assembly.md) for upload and process requirements.

## Verification and release limits

Current results are recorded in [validation.json](../hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/validation.json),
[engineering.json](../hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/engineering.json), and
[prefab-review.json](../hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/prefab-review.json).
The portable lab checks circuit compilation, independent pin fixtures, ERC/DRC,
route connectivity, sensor regressions, power/geophone models and stack envelopes.
These checks do not establish physical power, timing, noise or thermal performance.
Follow the [bench procedure](bench-procedure.md) for first-article qualification.

The TI Pi supervisor, J130 input range, shutdown handshake, prototype firmware
and shared Pi/HAT budget are specified in [power supplies](power-supplies.md#pi-supervisor-and-battery-input).
