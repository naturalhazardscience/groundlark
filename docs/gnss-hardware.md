# Groundlark GNSS and antenna

DAQHAT-01 fits **u-blox MAX-M10S-00B (U21)** on the underside. It uses Pi I²C1
at address **0x42**, powered from PI_3V3. TIMEPULSE connects directly to
**BCM24, header pin 18**. The geophone retains BCM4 DRDY; BCM6/13 retain the
power-supervisor handshake. FPGA connections and its separate supply remain
unchanged. GNSS needs no configured FPGA.

The Pi and GNSS face ISO1640 side 2 (pins 6–8). With an assumed 3.135 V minimum
host rail and a 0.2 × VCC input-low limit, a 0.4 V isolator output-low allocation
leaves about 0.227 V static margin. This is a datasheet scenario; confirm rail,
sink current and bus waveforms on hardware. The sensor bus faces side 1, whose
0.71 V maximum low output fits the sensors’ 3.3 V input thresholds. Keep the
C48 sensor-side and C49 Pi-side supply bypass assignments with this orientation.

## Antenna connection

J140 is a HenryTech **HL-SMA-KWE-02**, conventional female SMA, 50 ohms.
Use a matching male SMA plug, not RP-SMA. It faces native PCB -X, which becomes
physical enclosure +X after stack rotation. The R3 side slot admits a coupling
nut up to 10 mm diameter; the connector is recessed, so verify access with the
actual cable before printing a batch. Support the cable to avoid bending the PCB.

Use a GNSS antenna rated for **3.3 V bias and at most 20 mA**. U140 TPS70933
derives its supply from switched PI_5V, with local 4.7 µF input/output bypass.
U141 TPS2553 follows the LDO. ILIM and EN connect to its input, selecting a
50–100 mA sustained current limit (75 mA typical), below L140’s 280 mA rating.
C152 (100 nF) bypasses the limiter input. C151 (10 nF) bypasses the cold end of
L140 beside the SMA with a local ground-plane stitch. L140 (27 nH) feeds DC onto
the coax; C148 (47 pF C0G) blocks antenna DC at RF_IN.
D140 PESD5V0F1BL provides 0.4 pF nominal ESD protection. There is no antenna
open/short telemetry; the limiter’s unused open-drain FAULT output is NC.
Current-limit response, repeated shorts and thermal recovery require physical
fault testing. The 20 mA antenna allocation is separate from the fault limit.
Do not connect an externally powered coax source that supplies DC to J140.

U21 has 4.7 µF and 100 nF local bypass. EXTINT is grounded. Unused UART,
RESET_N, SAFEBOOT_N, VIO_SEL, VCC_RF, LNA_EN and V_BCKP remain unconnected per
the selected interface; no backup cell is fitted. Removing Pi power also removes
receiver and antenna power. Each start must reacquire satellites.

Allow 75 mA from PI_5V and 150 mA from PI_3V3 for the HAT, including the
receiver's 100 mA acquisition allocation and antenna. These allocations sit
inside the supervisor's **3 A combined Pi/HAT** limit; USB accessories and Pi
workload consume the same budget. Measure rail droop, startup and temperature.

## Placement and qualification

Place the antenna outside the enclosure with the widest practical sky view.
Mountains and foliage can block satellites; do not accept an indicated fix as
proof of timing quality. Record lock loss and PPS gaps during representative
terrain tests. Keep antenna cable away from the geophone lead and switching
power inputs. The vented R3 case has no outdoor ingress rating.

The PCB keeps the RF input on B.Cu beside the connector with a ground reference
on In4.Cu and through-hole SMA grounds. The short RF layout uses the existing
stock six-layer stack. Its two series traces are 0.17 mm wide over the recorded
0.0994 mm dielectric; the uncoated microstrip estimate is about 49.7 Ω.
The native check rejects the previous 0.3 mm width and missing reference copper.
The [simulation profile](simulation-validation.md#rf-network) now includes
mask/etch/dielectric sensitivity and a lumped pad/connector RF network. Its
nominal loss is about 0.42 dB, but the sampled corner envelope misses the
1 dB insertion-loss / 10 dB return-loss allocations. Coplanar metal and the
three-dimensional transitions remain outside that model.
It has **no controlled-impedance fabrication claim**;
measure insertion loss/return loss, satellite C/N0, ESD behavior and receiver
performance with the FPGA and power converters active before release.

Use [`live --fifo --utc`](utc-timing.md) to capture receiver configuration,
TIM-TP, NAV-TIMEUTC and kernel PPS events. The application owns BCM24; do not
also enable `pps-gpio`. UTC correlation requires a recording-bound policy with
measured bounds. GNSS does not remove ADC/filter delay or Linux acquisition
uncertainty. The present geophone polling path is not a verified 1 ms sample
timestamp source. Calibrate delays against a common physical stimulus/reference
across stations before claiming millisecond alignment.

## Parts and source drawings

| Part | Catalog identity | Manufacturer evidence |
| --- | --- | --- |
| MAX-M10S-00B | JLCPCB C4153167 | [u-blox integration manual](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf) |
| HL-SMA-KWE-02 | JLCPCB/LCSC C20617216 | [HenryTech drawing](https://datasheet.lcsc.com/datasheet/pdf/b2f602368ae573f1e0d7be688540576e.pdf?productCode=C20617216) |
| TPS2553DBVR | JLCPCB C55266, SOT-23-6 | [TI datasheet](https://www.ti.com/lit/ds/symlink/tps2553.pdf) |
| TPS70933DBVR | TI, 3.3 V antenna regulator | [TI datasheet](https://www.ti.com/lit/ds/symlink/tps709.pdf) |
| PESD5V0F1BL,315 | Nexperia, SOD882 | [Manufacturer specification](https://www.nexperia.com/product/PESD5V0F1BL) |

Confirm stock and assembly eligibility at order time. The SMA footprint follows
the drawing's 5.10 mm ground-pin pitch, four 1.50 mm ground drills and 1.20 mm
center drill. The authored STEP uses the same drawing and is an envelope, not
a supplier-certified mating solid. Supplier rotation/package approval remains
part of assembly release.
