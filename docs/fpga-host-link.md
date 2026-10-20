# DAQHAT-01: internal Pi / Trenz transport

The 140 × 56 mm HAT now connects the Pi directly to the TE0712-03-81I36-A.
Six wires reserve SPI/QSPI, UART is retained, and a switch shares four wires
with dedicated FPGA JTAG. J84–J89, their expansion fanout, all four ribbons,
the guide and the offset spacer are removed from the active assembly.
The Pi stays below the HAT; the FPGA stays above it for cooling access.

## Wiring and power

| Function | Pi physical pin / BCM | Carrier / module contact | FPGA ball |
| --- | --- | --- | --- |
| SCLK / JTAG TCK | 40 / 21 | J81.21 / JM2.22 | W19 |
| CS_N | 12 / 18 | J81.23 / JM2.24 | W20 |
| DQ0 / MOSI / JTAG TDI | 38 / 20 | J81.22 / JM2.21 | V18 |
| DQ1 / MISO / JTAG TDO | 35 / 19 | J81.24 / JM2.23 | V19 |
| DQ2 / JTAG TMS | 36 / 16 | J81.26 / JM2.25 | Y18 |
| DQ3 | 32 / 12 | J81.28 / JM2.27 | Y19 |
| Pi TX / FPGA UART RX | 8 / 14 | J81.12 / JM2.11 | AA21 |
| Pi RX / FPGA UART TX | 10 / 15 | J81.14 / JM2.13 | AA20 |
| Application reset control | 11 / 17 | J81.13 / JM2.14, through existing transistor | AB22 |

In programming mode the switch selects dedicated JTAG contacts J81.94/96/98/100,
not the application balls in the table. R80 keeps the module CPLD's JTAGEN low.
The complete [contact map](trenz-pin-map.json) includes 149 unused ordinary I/Os;
the audit checks all 260 module contacts against independent vendor fixtures.
Sensors retain SPI0, I2C1 and their existing interrupts. SDP32 U23
uses I2C1 address 0x21, alongside the 0x20 link expander and 0x40 geophone ADC.
It consumes no additional Pi or FPGA pins; BCM6/13 serve power management; BCM24 carries GNSS PPS. Ethernet is not exposed.

U100/U101 are TMUX1574 bidirectional switches. U102 is a TCA9534 at I2C1 address
0x20: P0 selects JTAG; P1 requests enable. U103/U106 permit a connection only
with the request, BCM25 arm and both rail-good signals asserted. BCM25 also
retains its existing UART-enable role. The link tool owns BCM25 while running;
do not run a separate UART-enable controller concurrently.

R118 (10 kΩ) pulls PI_UART_RX to PI_3V3 while U51 is disabled. Initialize
the TCA9534 output latch low before configuring P0/P1 as outputs; grounded
P2–P7 must remain inputs (configuration register 0xFC). The driver reads back
the configuration before enabling the link.

The Trenz system-controller MODE signal is firmware dependent. The
[CPLD v24 description](https://www.trenz-electronic.de/trenzdownloads/Trenz_Electronic/Modules_and_Module_Carriers/4x5/TE0712/REV02/Firmware/TE0712%20CPLD-v24-09_27_2023.pdf)
marks MODE unused but does not establish its pull setting. Record the fitted
module's CPLD firmware and verify its input behavior during bring-up; the
carrier does not rely on an unverified internal MODE pull.

U104/U105 monitor Pi/FPGA 3.3 V with TLV809EA30DBZR supervisors (3.0 V threshold,
nominal 200 ms release). Each new IC has local 100 nF decoupling. R100–R105 are
22 Ω series footprints; pulls define reset/idle states. The switch's unselected
CS/DQ3 parking contacts are open, so they cannot short Pi outputs to ground.
TMUX1574 provides powered-off signal isolation at VDD=0 and fail-safe controls.
Settled-state simulation does not characterize subthreshold power ramps.

J83 uses a separate Nexys-compatible 12 V adapter; see the [converter and operating envelope](trenz-hat.md#power-and-interfaces).
The [assembly guide](stack-assembly.md) specifies the existing GPIO riser and
four straight supports. Use the recorded six-layer stock stack and fill/cap all through-vias,
including the ADC supply vias and the through-via at U101.4.

## Initial transport and bitstream

Pi 4 uses **SPI6, mode 0, CE0 only, initially ≤1 MHz**. DQ2/DQ3 are reserved;
its Linux SPI controller does not perform native quad transfers. The reference
bitstream advertises no quad capability. JTAG runs at a requested 100 kHz;
measure the actual clock before changing the native GPIO adapter calibration.

The [reference RTL](../sw/fpga/rtl/daqhat_01_link.sv) is an echo/mailbox bring-up design.
It uses the module's default 50 MHz CLK50M2 at R4; the exact revision-03 schematic
shows its 1.5 V level translation and bank supply, so its XDC uses LVCMOS15.
Application bank 14 uses LVCMOS33. The bitstream does not configure DDR, Ethernet
or the Si5338. Verify the clock generator still has its factory settings.

At this conservative rate, SPI is oversampled in one 50 MHz domain through
three-stage synchronizers. A one-frame mailbox replaces the proposed asynchronous
FIFO: there is no second fabric clock domain to cross. CS setup/hold and the
interval between transactions must each be at least 1 µs; SCLK high/low at least
500 ns. The overlay requests 1 µs CS setup/hold/inactive delays through the Linux SPI
core; use a kernel supporting those properties (reviewed against Pi Linux 6.12).
The Pi tool checks the overlay and inserts a 1 ms transaction gap. MISO is undriven immediately
when CS is high. UART has electrical loopback for separate diagnostic testing.
Unused quad ports are optimized out; the bitstream leaves unused pins undriven.

Vivado 2025.2 built the XC7A200T-FBG484-1 bitstream. Recorded timing is +10.143 ns
setup / +0.109 ns hold slack at 50 MHz, zero internal unconstrained endpoints;
see [reports and source hashes](../sw/fpga/verification/result.json). Asynchronous
input exceptions and bounded output propagation are explicit in the XDC.
These reports do not qualify the Pi controller, switch or board timing.

## Wire contract

Every command is one CS-delimited transaction, MSB-first within each byte.
The first received byte is a dummy. Multi-byte integer fields are little-endian.

| Command | Bytes after command | Behavior |
| --- | --- | --- |
| 0, status | Clock 8 zero bytes | `SSFP`, version 1, capabilities 0, flags, error |
| 1, submit | Exact encoded frame | Commit only at CS release after length and CRC validation |
| 2, read | Clock 206 zero bytes | Result frame padded with zeroes; repeated reads do not consume it |
| 3, acknowledge | uint16 sequence | Free only the result with this sequence |

Flags: 0 busy, 1 empty, 2 result available. Frame: `SSFP`, version byte 1,
operation byte 1 (echo), uint16 sequence, uint16 payload length, 0–192 payload
bytes, CRC-32/IEEE over header and payload, stored little-endian. Maximum 206 bytes.
Status errors are sticky until application reset/reconfiguration: 1 overflow,
2 invalid frame, 3 CRC, 4 incomplete transaction, 5 busy write, 6 wrong ACK,
7 unknown command. Busy writes preserve the existing result. Invalid results
are never acknowledged by the Python client. A timed-out write has unknown
outcome; the client does not automatically repeat it.
The processing timeout is checked before and after each status transaction;
late ready responses are not consumed. ACK completion requires a subsequent empty
status. An interrupted reset discards the current transaction through CS release;
MISO is undriven during reset, and the next complete transaction starts cleanly.

## Bring-up

Install the sensor overlay first. Compile the optional
[`groundlark-fpga-overlay.dts`](../sw/pi/deploy/groundlark-fpga-overlay.dts)
with `dtc -@ -I dts -O dtb`, install it in the Pi's overlays directory and add
`dtoverlay=groundlark-fpga` to the active boot configuration. Enable I2C1.
Do not combine with other SPI1/SPI6 or GPIO18–21/12/16 consumers. CE1 remains
disabled because BCM27 belongs to IMU1. Ensure the `spidev` module is loaded.

The following commands run **on the Pi**, from the repository, after verifying
which gpiochip represents BCM2711. OpenOCD 0.12.0 with bcm2835gpio is required.

```sh
sudo python3 sw/tools/fpga.py scan --gpiochip /dev/gpiochip0
sudo python3 sw/tools/fpga.py program --gpiochip /dev/gpiochip0 --bitstream /path/to/daqhat-01-link.bit
sudo python3 sw/tools/fpga.py status --gpiochip /dev/gpiochip0
sudo python3 sw/tools/fpga.py loopback --gpiochip /dev/gpiochip0
```

The tool locks the link, disarms it, initializes the expander's output latch
before directions, and verifies register readback. For JTAG it unbinds SPI6's
controller, claims safe GPIO directions, then enables the switch. It isolates
before restoring SPI6. GPIO25 provides disarm even if I2C fails; I2C disable
is attempted even if the GPIO operation fails. A control-bus failure keeps
ownership faulted; restore power/control and reinitialize before reuse. Driver
restoration failure also latches this fault. SIGTERM and Ctrl-C unwind the
isolation path. Termination that bypasses cleanup (including SIGKILL) has no hardware watchdog: GPIO output
state may remain latched. Restart through this tool (which first drives BCM25
low), or power-cycle/reboot before manual driver changes. Reboot restores a
controller left unbound. Sensor acquisition remains independent.
Programming loads volatile FPGA configuration only; it does not write flash.

Build the bitstream from an ignored output directory using Vivado:

```text
vivado -mode batch -source /absolute/path/to/groundlark/sw/fpga/build.tcl
```

## Verification and remaining measurements

The portable lab includes RTL packet/fault simulation, production Python-to-RTL
co-simulation, host framing/ownership tests, 38 behavioral-switch/RC checks,
native CAD checks and sensor regressions. Full and quick profiles now run
`hw/tools/replay_trenz.py`, rebuilding the complete native routing in a
temporary directory and comparing every copper object. A separate parts fixture
checks all 32 link components against authored metadata, BOM and PCB fields.
Current rendered and
interactive models use the revised board; the Pi model remains conceptual.

Still measure first-article rail ramps/current, actual stack seating, SPI/JTAG
edges and switching, and sensor noise with the FPGA idle and active. Linux driver
handoff and JTAG programming have not been exercised on a physical Pi/Trenz stack.
Quad throughput and accelerated processing remain future work.
See [assembly requirements](jlcpcb-assembly.md) and the
[bench procedure](bench-procedure.md) for production preparation and physical qualification.

Sources: [exact module schematic](vendor/trenz/SCH-TE0712-03-81I36-A.PDF),
[TMUX1574](https://www.ti.com/lit/ds/symlink/tmux1574.pdf),
[TCA9534](https://www.ti.com/lit/ds/symlink/tca9534.pdf),
[SN74LVC1G10](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf),
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf),
[TLV809E family](https://www.ti.com/lit/ds/symlink/tlv803e.pdf).
