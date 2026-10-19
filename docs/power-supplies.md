# Power supplies and operating limits

These are prototype design allocations. Measure startup, steady load, cable
drop, regulator temperature and suspend current before deployment. A passed
calculation is not a USB compliance or physical power qualification result.

## Groundlark FPGA HAT (DAQHAT-01)

| Input | Required allocation | Loads |
| --- | --- | --- |
| Switched Pi header 5 V, pins 2/4 | Reserve 75 mA within the combined 3 A budget | LDL1117, three IMUs, ADC, SDP32, interfaces and GNSS antenna LDO |
| Pi header 3.3 V, pins 1/17 | Reserve 150 mA including receiver acquisition/startup allocation | GNSS receiver and Pi-side interfaces, EEPROM, GPIO expander, logic and pull-ups |
| J83 external adapter | 12 V ±5%, center-positive, 5.5/2.1 mm plug, at least 3 A | Independent FPGA converter input |
| U80 converter output | 3.326 V nominal, 3 A design allocation | Trenz module and FPGA-side circuitry |

The Nexys Video 12 V adapter specification is compatible with J83. The FPGA
power path is independent of both Pi header rails. J83 is now a 12 V input;
the previous external regulated 3.35 V connection has been replaced. Never
apply 12 V directly to the Trenz module or Pi header.

SW80 controls FPGA power. The input includes a 2 A fuse, reverse-polarity diode
and transient suppressor; U80 provides soft start, current-limit/hiccup and
thermal shutdown. These protections need bench qualification. Its PGOOD output
holds module EN1 low outside the converter's coarse power-good window.

At a 3 A output allocation, 11.4 V input and an assumed 85% conversion efficiency,
the converter draws about 1.03 A before series-diode loss and startup allowance.
The output allocation is about 10 W, not the adapter's full 36 W. Output hot-loop
resistance must remain within the 15 mΩ design target. See the
[Trenz voltage, capacitance and protection limits](trenz-hat.md#power-and-interfaces).
Actual FPGA current depends on the bitstream and remains unmeasured.

The SDP32 at 3.3 V adds a 5.5 mA maximum load; the 5 V
allocation retains 14 mA of reserve. Its 100 nF bypass adds nominally 0.33 µC
of charge to the sensor rail. The current circuit does not switch sensor power:
BCM26 controls signal-buffer enable, not the LDL1117 supply. BCM6/13 provide the power-supervisor handshake; BCM24 carries GNSS PPS.
Switching off the Pi 5 V input also removes sensor power.

The 75/150 mA allowances include interface switching, GNSS acquisition and reserve; they are not
the GPIO signal-pin drive rating. The Pi's supply must also support its own
workload, cooling, USB devices and other accessories. Do not hot-plug the HAT.
The native-board power report calculates capacitor charging for 0.1, 1 and 10 ms ramps with 20% high capacitance, including GNSS and antenna bypass capacitors. Short ramps require substantially more current. This C·dV/dt calculation omits regulator current limiting and source
control loops; verify startup on the intended Pi and power supply.

The report also checks the antenna's sustained short-circuit envelope. U141's
50–100 mA limit is below L140's 280 mA rating. At the 100 mA corner, the direct
HAT 5 V allocation rises from 75 to 155 mA; reserve the extra 80 mA inside the
combined Pi+HAT 3 A limit. The limiter can dissipate about 337 mW during a short.
The antenna LDO scenario uses 200 °C/W and 85 °C ambient as explicit assumptions,
not measured thermal performance. Current overshoot, thermal cycling and recovery
still require measurement. No antenna fault or current telemetry is connected.

At 50 mA output, 5.25 V input and 85 °C ambient, the LDL1117 dissipates about
103 mW. Assuming 150 °C/W gives about 101 °C junction temperature. This is a
thermal sensitivity scenario; the actual copper, enclosure and FPGA heating
determine the operating temperature. C42 must retain at least 4.7 µF effective
capacitance for regulator stability.

## Pi supervisor and battery input

J130 is a two-pole Phoenix 1803277 header: **pin 1 positive, pin 2 ground**.
Supply **8–18 V DC, with at least 3 A available**, from a battery with external
protection/BMS and an appropriate solar charge controller. This circuit neither
charges batteries nor accepts an unregulated solar-panel input. Battery chemistry
is not fixed by the board; packs outside this voltage range need an external
converter. The FPGA's J83 adapter remains a separate input.

F130 (4 A, 1206), D130 and D131 provide input fusing, reverse-polarity protection and
transient suppression. U131 (TPS70933) supplies U130 (MSPM0L1106) continuously.
Its EN pin floats as specified by TI; it must not be tied to the battery. U130's
VCORE pin connects only to C143 (470 nF). J131 exposes 3.3 V reference, ground,
SWCLK, SWDIO and NRST in that pin order; the probe must not supply target power.

U132 (TPSM53603) supplies nominal **5.115 V, 3 A combined for Pi and HAT**.
U133 (TPS22953) switches that rail to both Pi header 5 V contacts and blocks
reverse current while disabled. Its 10 nF CT capacitor gives approximately
18 ms rise time. Its unused PG output (pin 7) is grounded as TI specifies.
A 2 kΩ output bleed supports discharge after shutdown. RUN has
an external pulldown, so reset or an unprogrammed MCU leaves Pi power **off**.
The JP130 shunt forces manual bench power; remove it for automatic control.
R141 limits GPIO current if the shunt is inadvertently left installed.

**Do not power the Pi through USB-C while J130 is connected.** Off-state reverse
blocking is not a power mux. This allocation targets the enclosed Pi 4 stack;
it does not provide the Pi 5's full 5 A peripheral power budget.

The 10 kΩ / 2.43 kΩ divider sets 5.115 V. Including the reference limit,
0.1% resistor tolerance, independent 25 ppm/K drift over −40…85 °C and an
allocated ±20 mV ripple/transient allowance gives about 5.00–5.234 V before
load-switch and distribution drop. A 25 mΩ switch allowance and **50 mΩ total
copper/contact loop target** leave approximately 4.772 V at 3 A. This target
includes the GPIO riser contacts and return path and must be measured. Parallel
2 mm back/In3 rails run along the extension; local clearance necks and the inner
left-side feed retain both 5 V contacts. At 8 V input, an assumed 0.5 V diode
drop and 85% conversion efficiency imply about 2.41 A input. Neither efficiency
nor transient/thermal performance is qualified by these calculations. The ±20 mV
allowance is a bench acceptance limit, not a measured result. At this low-input,
full-load scenario D130 dissipates about 1.2 W and the converter about 2.7 W at
85% efficiency. Qualify both in the closed enclosure. F130 is the 1206
Littelfuse 0466004.NRHF; its temperature/current derating and startup I²t must
be checked with the selected battery and load. Do not assume 3 A output is
available at every enclosure temperature.

BCM6 (header 31) is an active-low shutdown request through Q130, pulled up to
Pi 3.3 V. BCM13 (header 33) asserts high after halt and drives Q131; the MCU reads
an inverted acknowledgement. The MOSFET interfaces prevent supervisor pull-ups
from powering an off Pi. BCM24 carries GNSS PPS; FPGA interfaces are unchanged.

R135/R136 divide fused battery voltage by 7.6667 into PA27/A0. At 18 V the ADC
input is below 2.36 V including 0.1% resistor tolerance. Use the internal 2.5 V
reference, allow at least 10 ms settling and calibrate gain/offset. The divider
alone draws about 10.4 µA at 12 V. MCU standby, regulator leakage, TVS leakage and
ADC duty cycle must be included in measured idle consumption. Firmware must
disable unused GPIO and must not assume the MCU watchdog runs in standby.

### Configuration and implementation status

[power-policy.example.json](../sw/pi/deploy/power-policy.example.json) deliberately
ships with `enabled: false` and null battery description, voltage thresholds and
timers. [power_config.py](../sw/pi/groundlark/power_config.py) validates a completed
profile, including at least 0.5 V restart hysteresis, voltage limits and bounded
delays. Loading it performs no I/O and does not program the MCU.

Target MSPM0 firmware, configuration transfer/flash storage and the Pi shutdown
service are **placeholders for implementation**. The firmware must request an
orderly shutdown, wait for acknowledgement or a bounded timeout, cut RUN, wait
for recharge and a minimum off interval, then restart. Invalid configuration,
ADC faults and repeated failed boots must leave RUN off. Select thresholds with
the actual battery/BMS and reserve enough energy for shutdown. Voltage alone
is not a reliable state-of-charge measurement, especially for LiFePO₄.

Before automatic field use, test brownout, failed acknowledgement, reset during
shutdown, recovery hysteresis, output discharge, startup/inrush, standby current,
3 A load/drop, enclosure temperature and geophone noise with the Pi converter
running. Circuit/CAD tests do not establish those results.

Manufacturer references: [MSPM0L1106](https://www.ti.com/lit/ds/symlink/mspm0l1105.pdf),
[TPS709](https://www.ti.com/lit/ds/symlink/tps709.pdf),
[TPSM53603](https://www.ti.com/lit/ds/symlink/tpsm53603.pdf),
[TPS22953](https://www.ti.com/lit/ds/symlink/tps22953.pdf).

## Skylark USB

Use a USB data port that grants the board's **500 mA configuration**. The PMS
and gas analog rail remain off until configuration. A power-only charger does
not start acquisition. USB-C pull-down resistors alone do not authorize a
1.5 A or 3 A load; there is no USB-PD negotiation.

The TPS2553's 82 kΩ setting gives approximately 284–369 mA current-limit
bounds. A further 50 mA allocation covers the MCU/USB, gas analog rail,
temperature/pressure sensors, digital ADC supply, pull-ups and reserve.
The resulting configured envelope is **419 mA**, leaving about 81 mA below
the descriptor allocation. The SHT40 heater stays off. Current-limit response
and fan startup overshoot still require measurements.

Before configuration the 50 mA allocation is below USB 2.0's 100 mA unit load.
Estimated capacitor charging is about **38 µC**, including downstream digital
capacitors and 20% high capacitance, below the 50 µC screening limit. This
charge calculation does not predict peak inrush or establish compliance.

**The PMS5003 needs at least 4.5 V at J2.** Skylark has no boost converter.
A USB source/cable can satisfy the digital electronics while failing this
sensor requirement. Use a short, low-resistance cable and verify voltage under
fan startup and steady load. For example, 5.0 V at the source, 0.5 Ω total
source/cable/fuse loop resistance and a further 0.25 Ω switch/PM-lead allowance
give about 4.69 V at the 425 mA envelope. The same assumptions with 4.75 V at
the source give about 4.44 V and fail. These resistance values are scenarios,
not extracted PCB or measured cable resistances.

Firmware checks the post-fuse supply through the calibrated MCU ADC, using
a nominal 4.65 V threshold, and checks the switch fault input. A failed or
unavailable voltage measurement disables PM power and reports missing PM
samples; gas and climate acquisition can continue. The ADC monitors upstream
of the switch and lead, so it cannot certify J2 voltage. Divider/ADC error and
the downstream drop must be measured against that threshold.

AP2112 dissipation at a 50 mA output allocation is about 101 mW at 5.25 V input.
An assumed 250 °C/W and 85 °C ambient give about 110 °C junction temperature.
Verify the actual enclosure temperature and capacitor effective values.

During suspend/reset the firmware clamps the cells, holds the gas ADC in
reset, and cuts analog/PMS power. Suspend reduces the MCU/APB clock to 12 MHz
so the polled USB peripheral remains above its 10 MHz erratum limit; ADC,
UART and I²C are disabled. **Total suspend current is unmeasured and must meet
the applicable 2.5 mA USB limit.** The always-on regulator, MCU, digital sensors
and pull-ups remain loads. A compliant lower-power USB suspend/wakeup design
may require further firmware or hardware changes after measurement.

Pi downstream USB limits are shared by all attached devices. Raspberry Pi 4
allows 1.2 A total; Pi 5 normally limits this to 600 mA with a 3 A source,
or 1.6 A with a detected 5 A source. Reserve Skylark's full 500 mA allocation
when planning other peripherals. See [Raspberry Pi power documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply).

## Reproducible checks

`hw/tools/power_review.py` reads native PCB values and verifies source-domain
connections, the configured USB envelope, attached capacitance and reference
divider settling. Full lab runs retain `power-review/results.json` under the
shared simulation results. Fault fixtures reject an excessive current-limit
setting, added input bulk capacitance and an FPGA input tied to the Pi rail.

For bench qualification, record Pi-model/PSU/cable identities, both header
currents, J83 current, USB attach/configured/suspend currents, J2 minimum
voltage during startup, rail minima/maxima and regulator temperatures. Repeat
with FPGA inactive/active, fan starting/running, minimum source voltage and
the intended temperature range. Missing measurements do not pass a report.

Manufacturer references: [TPS2553](https://www.ti.com/lit/ds/symlink/tps2553.pdf),
[AP2112](https://www.diodes.com/datasheet/download/AP2112.pdf),
[LDL1117](https://www.st.com/resource/en/datasheet/ldl1117.pdf),
[STM32F072 errata ES0223](https://www.st.com/resource/en/errata_sheet/es0223-stm32f072x8xb-device-errata-stmicroelectronics.pdf).
