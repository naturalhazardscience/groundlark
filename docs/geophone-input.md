# DAQHAT-01: one Racotech geophone

TP90–TP93 expose ground, VCM, AVDD and DRDY on the underside for external bench measurements. Use J90 for isolated differential stimuli; the [calibration procedure](calibration.md) covers floating shorts and measured DC gain.

The active 140 × 56 mm DAQHAT-01 carrier has one external passive vertical
geophone input, alongside MAX-M10S GNSS and its side-facing SMA antenna port.
Burrowlark is the separate remote USB magnetometer.
The current internal host link uses nine ordinary Trenz I/Os; all 260 module
contacts, including deliberate no-connects, are independently checked.

## Sensor and connector

Specify **Racotech RGI-4.5Hz, vertical, 395 Ω ±5%, 23.4 V/(m/s) ±10%,
4.5 Hz ±0.5 Hz, damping 0.70 ±10%**. Raspberry Shake documentation also calls
this its 4.5 Hz RGI-20DX; do not order another RGI-20DX frequency by name alone.
The bare element is 25.4 mm diameter × 33 mm high. Its ground-coupled external
mount must hold it vertically; HAT leveling does not establish the leveling of
a separately mounted geophone.

Racotech's [RGI-4.5Hz manufacturer listing](https://www.made-in-china.com/showroom/racotech/product-detailkNzJyDsCnQcA/China-Seismic-Geophone-Element-RGI-4-5Hz-.html)
specifies 0.70 ±10% as typical **open-circuit** damping. No damping shunt is
fitted. The datasheet specifies 23.4 V/(m/s) sensitivity without a shunt;
verify the received element and complete cable/input response by measurement.

J90 is horizontal Phoenix Contact **1803280**, MC 1,5/3-G-3,81. Use the matching
**1803581**, MC 1,5/3-ST-3,81 cable plug. Pin 1 is GEO+, pin 2 GEO−, pin 3 cable shield/GND.
The mouth faces native board +Y, parallel to the PCB. The original three holes
are retained; numbered pad polarity is preserved by the revised local routing.
The 7.25 mm installed header height excludes the mating plug. Reserve a 12 mm
horizontal withdrawal stroke and release the cable clamp before unplugging.
The two coil wires float relative to ground and require no external power.
Use a shielded twisted pair; terminate its shield at J90, not a coil terminal.
This connector is incompatible in purpose with J83's external FPGA supply.
The render shows the PCB header, not the cable plug or external geophone.

## Circuit

- U22: ADS122C04IPWR, 24-bit delta-sigma ADC with internal PGA and 2.048 V
  reference, AIN0−AIN1, I²C address 0x40. Initial software: gain 64, normal
  330 SPS. The 24-bit word is not a claim of 24 noise-free bits.
- D90: TI TPD2E2U06QDCKRQ1 / JLCPCB C915089 in the authored circuit and
  assembly BOM, replacing TPD2E2U06DCKR at the connector. The SC-70 pinout
  remains 1 = GEO_P, 2 = GEO_N, 3 = GND; no routing change is needed.
  R90/R91 are 1 kΩ series input resistors.
  Protection is intended for handling ESD, not outdoor lightning or arbitrary
  sustained applied voltage. Qualification of the protection remains physical.
- C90: 100 nF C0G across the differential input. Baseline CAD names TDK
  C3216C0G1H104J160AA; the reviewed assembly selection is Murata GRM31C5C1H104JA01L
  (C97946), retaining 50 V, +/-5% and 1206; see [assembly selections](jlcpcb-assembly.md);
  C91/C92: 1 nF C0G to ground.
  C0G avoids using piezoelectric high-k ceramics on the measurement input.
- R92/R93: 1 MΩ bias returns to filtered mid-supply. R94/R95: 10 kΩ divider;
  C93: 10 µF. This loads the coil lightly; no additional damping shunt is fitted.
- R96: 22 Ω analog supply filter; C94/C95: 10 µF + 100 nF at AVDD;
  C96: 100 nF at DVDD. RESET is tied high. Unused analog/reference pins float,
  following TI's unused-input guidance; excitation and burnout currents are off.
- R97: 10 kΩ DRDY pullup. U42 carries its active-low output to Pi BCM4,
  formerly PPS. Existing I²C isolation and pullups are retained.

Nominal input full scale is ±32 mV. Well above the mechanical corner this is
approximately ±1.37 mm/s before loading and filtering; it is not a flat
velocity range below 4.5 Hz. The nominal electrical pole including the coil
is approximately 662 Hz. The ADC's own digital filter also shapes the response.
See [sensor bandwidth and timing](sensor-response.md) for the combined response,
IMU bandwidths and sampling limits.
TI specifies typical 0.50 µV RMS ADC input noise at gain 64 / 330 SPS / 3.3 V;
this excludes the sensor, resistors, cable and board interference.

No analog hyper-damper or inverse-response compensation is implemented. Do not
claim Raspberry Shake's or AnyShake's sub-hertz system response for this board.
Preserve raw counts and characterize the assembled response before correction.

## Accelerometer axes

U11–U13 are three **three-axis** LSM6DSO IMUs, all on the front at rotation 0°.
Each measures X, Y and Z; rotating the chips is unnecessary to obtain three
axes. Three sensors provide three independent readings per axis. Raw values
retain the ST package-axis convention. No geographic orientation or automatic
averaging is implied. Hardware tests reject a rotated/flipped placement until
an explicit software axis mapping is provided. The external geophone adds a
single vertical velocity-sensitive channel.

## Acquisition and validation

Sensor ID **9** carries signed 24-bit ADC counts and the 8-bit conversion
counter. ID 6 remains reserved for legacy GNSS recordings. The active inventory
is 1–3 and 9 (IDs 4/5/6 are reserved for legacy recordings); remote IDs remain 7 and 8. Configuration carries gain and reference.
Nominal input volts = counts × 2.048 / (64 × 2²³); velocity requires the sensor
transfer function and calibration, not simple division across all frequencies.

The Pi driver resets and reads back all registers, enables inverted-data
integrity and the conversion counter, detects duplicates/gaps/wrap ambiguity,
and marks signed endpoints saturated. There is no ADC FIFO. The current driver
polls; BCM4 is routed for future falling-edge timestamp acquisition. Poll
completion timestamps have unknown absolute uncertainty, and overwritten
conversion loss is unknown. Scheduler/IPC throughput must be measured on the
target Pi; 330 SPS conversion rate does not guarantee 330 delivered samples/s.
ADC data validity does not prove coil continuity; automatic open-coil detection
is not implemented. The current DAQHAT-01 supports `live --fifo --utc` through MAX-M10S and BCM24 PPS.
Physical geophone sample-time bounds remain unqualified; see [UTC timing](utc-timing.md).

Duplicate reads do not extend the counter ambiguity window. Conversion gaps emit
missing records with unknown loss, without resetting an otherwise healthy ADC.
Actual communication faults retain bounded hardware recovery. The nominal
330-SPS setting has a 3.04296875 ms conversion period at nominal clock; do not
interpret the configured nominal period as a calibrated device timestamp.
The [bench procedure](bench-procedure.md) covers physical response, noise,
timing and fit. Modeled layout and transient checks do not replace these measurements.

Tests include independent pin maps, three-IMU orientation, ADC wire faults,
counter rollover, signed precision, saturation, contract clock/ID validation,
and a known 10 Hz / 100 µm/s waveform through the actual driver on a modeled bus.
SPICE checks cover 15 frequency/tolerance cases plus bias and PGA headroom.
The stimulus is a steady-state mechanical + passive RC model: no ADC digital
filter, settling, self-noise, magnetic pickup or physical mounting simulation.

Bench qualification must measure polarity/response, shorted-input and attached
sensor noise with FPGA off/on, clipping/recovery, delivery timing/loss, supply
sequence and physical cable/stack fit. Blank physical evidence never passes.

## Primary references

- [Racotech sensor datasheet](https://raspberryshake.org/wp-content/uploads/2020/05/racotech-geophone-datasheet.pdf).
- [TI ADS122C04 datasheet, SBAS751B](https://www.ti.com/lit/ds/symlink/ads122c04.pdf): PW pin map, PGA common-mode, noise table 1, registers and input filtering.
- [TI TPD2E2U06 datasheet](https://www.ti.com/lit/ds/symlink/tpd2e2u06.pdf): DCK pin map and ESD characteristics.
- [Phoenix Contact 1803280](https://www.phoenixcontact.com/en-us/products/pcb-header-mc-15-3-g-381-1803280).
