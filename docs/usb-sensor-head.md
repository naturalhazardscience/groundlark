# Burrowlark DAQUSB-01 — USB sensor head

**Burrowlark** (model **DAQUSB-01**, revision **B1**) is Groundlark's 96 × 70 mm remote USB-C
sensor board, carrying four aligned RM3100 modules and an SHT45 temperature/humidity sensor. The DLVR infrasound sensor and
its bypass capacitor have moved to Groundlark DAQHAT-01 as U23/C24. Its circuit source is [`hw/burrowlark-usb/elec/field_head.ato`](../hw/burrowlark-usb/elec/field_head.ato),
its native CAD is in [`hw/burrowlark-usb/boards/groundlark-field-head/`](../hw/burrowlark-usb/boards/groundlark-field-head),
and its firmware belongs in [`sw/field-head/`](../sw/field-head/README.md).

Prototype target firmware now implements the fixed RM3100/SHT45 profile, USB
framing and boot journal. Native fault fixtures and ARM linking are software
evidence; real enumeration, suspend current, sensors and timing remain unqualified.

Connect Burrowlark directly to an existing Raspberry Pi USB host port with a
USB data cable. The HAT communicates with the Pi over its 40-pin header. There is no USB connector, cable
power output or PCA9615 transceiver on the HAT.

## Circuit

- J1: GCT USB4105-GF-A USB 2.0 receptacle; both D+ contacts are joined, as are
  both D− contacts. CC1 and CC2 each have their own 5.1 kohm, 1% pull-down.
  SBU is unused. The shield joins board ground. No PD negotiation is required.
- D1/D2: USBLC6-2SC6 protection on D+/D− and CC1/CC2, referenced to VBUS/GND.
- F1: MF-MSMF050-2, 500 mA-hold resettable fuse, followed by AP2112K-3.3TRG1.
  The LDO has 2.2 uF input and 4.7 uF output capacitors; its enable follows input.
- U1: STM32F042K6T6, native full-speed USB with internal pull-up and HSI48/CRS.
  Each supply has local 100 nF bypass. NRST has 10 kohm/100 nF; BOOT0 has a
  10 kohm pull-down and a boot jumper. SWD provides debug/programming access.
- U5: TPS22919DCKR switches the sensor rail; PA0 enables it, a 100 kohm pull-down
  defaults it off. QOD joins output for discharge through the internal resistor.
- U2/U7/U8/U9: complete PNI 14190 RM3100 modules in SPI mode, all oriented alike.
  PA1/PA2/PA3 broadcast SCK/SI/SSN; PA4–PA7 receive four independent SO lanes.
  PB0/PB1/PB3/PB4 receive separate DRDY signals. C4/C11/C12/C13 each supply a
  local 100 nF bypass and ground-plane return. R9 pulls SSN high to V3_SENSOR.
  Module pin 10 I2CEN is grounded; pins 6/8/9/11 remain deliberate no-connects.
- PB6/PB7 read only SHT45 (0x44) over 100 kHz local I2C. Pull-ups connect to the
  switched rail. U3/C5 remain absent. This revision requires B1 SPI firmware;
  the former A2 I2C firmware cannot acquire the array.

- U6: Sensirion SHT45-AD1B-R2, DFN-4 1.5 x 1.5 mm. Pins 1/2 are SDA/SCL,
  pin 3 is switched V3_SENSOR, pin 4 is GND. C10 provides local 100 nF bypass.
  This shares the existing switched-rail pull-ups; its heater remains off.

J2 SWD pins: 1 = 3.3 V reference, 2 = SWDIO, 3 = GND, 4 = SWCLK, 5 = NRST.
Use its 3.3 V pin as a probe reference; do not power it externally while USB is
connected. J3 connects BOOT0 to 3.3 V when fitted. Keep it open for normal boot.

## Firmware contract

The PCB alone will not enumerate: the prototype USB firmware must be flashed.
Configure HSI48 and CRS according to ST's USB clock requirements. Implement a
full-speed USB CDC interface with a maximum 100 mA descriptor (bMaxPower = 50).
Use a properly assigned VID/PID before distribution. Do not invent an identity.

Keep sensors off before USB configuration and during suspend; place SPI, SDA, SCL
and DRDY in high impedance without internal pull-ups while their power is off.
Push-pull SPI outputs remain high impedance through the 20 ms sensor-rail settle
interval; SSN follows the rising switched rail through R9 before SPI is enabled.
Disable USB clocks/peripherals as required to meet suspend current, then restore
clock synchronization, sensor power and acquisition on resume. Measure current
in every USB state; component budgets and a PTC are not compliance evidence.

Use the fixed single-shot 10 Hz array profile described below. Preserve signed 24-bit magnetic samples,
sequence numbers and MCU acquisition timestamps. Legacy recordings may retain
pressure status bits from the former optional DLVR population. Report
sensor identity, configuration, overruns and reset reasons. The Pi correlates
timestamps and calibrates/stores readings.
Use the [sensor v1 contract](sensor-contract.md) for Protobuf messages, explicit
timestamp domains, loss reporting and bounded COBS/CRC framing. Its reference
codec and prototype MCU implementation are tested in software; physical enumeration remains pending.
USB arrival time must not be represented as exact sensor acquisition time.

Engineering operating allowance: 25 mA controller plus 55 mA for all four modules,
SHT45 and sensor-rail loads = 80 mA, below the 100 mA USB descriptor. This is an
allocation, not a measured or manufacturer-guaranteed worst case; qualify every
USB state, temperature and module variant. Startup capacitance is
2.2 + 4.7 + 0.4 = 7.3 uF nominal on the unswitched rails, plus NRST charge and
parasitics. Sensor capacitors/module load are behind the initially off switch.
Capacitor tolerance, inrush and USB suspend behavior require measurement.

## CAD and previews

The routed PCB, compiled layout, review schematic and BOM contain four RM3100
modules and four bypass capacitors, plus SHT45 U6/C10, with no U3/C5 population.
The B1 outline is 96 × 70 mm. The USB interface and DAQUSB-01 identifier are
retained; the complete native SES snapshot reproduces the revised copper.
[PCB render](../hw/burrowlark-usb/boards/groundlark-field-head/3d.png) and
[schematic/assembly previews](../hw/burrowlark-usb/boards/groundlark-field-head/preview/)
show this population; [rebuild commands](build.md) regenerate them from native CAD.
The circuit and CAD checks reject removed pressure parts in both compiled and
routed boards, placement metadata and review schematics.

## Array arrangement and coherent acquisition

Viewed from the component side, with USB at the right, the centers are:

| Module | Sensor ID / slot | X, Y from PCB upper-left (mm) |
| --- | --- | --- |
| U2 | 7 / 0 | 20, 20 |
| U7 | 18 / 1 | 50, 20 |
| U8 | 19 / 2 | 20, 50 |
| U9 | 20 / 3 | 50, 50 |

All four use the same package orientation on a 30 mm square grid. The complete
25.4 mm modules have 4.6 mm between their board edges. Use nonmagnetic mounting
hardware and qualify the installed stack; the module models are dimensional
envelopes. The SHT45 sits between the modules, while the USB MCU and power
circuitry occupy the right side. SHT45 enclosure temperature is supporting
evidence, not four independent measurements of each module's temperature.

The 30 mm center spacing is a prototype geometry, not a qualified magnetic
isolation distance. It is not necessary to spread the modules over metres to
average local geomagnetic variations: the useful regional field is effectively
common over this array. Increasing pitch does not change the ideal factor-of-two
noise reduction from four independent sensors. The separation from each sensor
to current loops, USB circuitry and magnetic materials also matters; moving
modules toward those sources can worsen the result. Use the
[spacing qualification procedure](#spacing-qualification) before accepting the
array's noise performance.

The MCU writes the same cycle count (200 per axis) to all four sensors and checks
each readback separately. Every 100 ms it drains prior results, requires all
DRDY lines low, arms four interrupts, and broadcasts one XYZ POLL command.
The software SPI uses common clock/data/select edges with at least 2 microseconds
per half-cycle. Four separate SO inputs avoid output contention and are sampled
in one GPIO register read. There is no external analog output to amplify.

Shared commands coordinate the measurement windows; **the internal RM3100 clocks
are not phase-locked**. Each module also measures X/Y/Z sequentially. TIM2 at
1 MHz records broadcast completion and individual DRDY interrupt observations.
The original signed 24-bit XYZ words, a shared cohort number and those observations
are recorded for every lane. Read-completion time remains the primary acquisition
timestamp, with physical uncertainty unknown. USB timing is never substituted.

A 50 ms deadline bounds each quartet. A missing or inconsistent DRDY, stuck-high
input or SPI fault latches magnetic acquisition until a sensor power cycle;
following slots are missing. USB backpressure drops complete quartets. These
rules prevent a late result from being paired with the next conversion. Climate
I/O runs between magnetic integrations; its heater is disabled.

## Calibrated averaging and noise

`groundlark.magnetic_array.average_cohort` in the Pi software requires exactly four
valid samples from the same device, boot, configuration, cohort and trigger.
It also requires an explicit maximum DRDY skew and four individual calibrations.
The calibration record contains `id`, `device_id`, `configuration_sha256` (SHA-256
of the deterministic Configuration protobuf), `provenance`, and `lanes` keyed
by string sensor IDs. Each lane has a 3×3 `matrix_t_per_count` into common board
axes and three-element `offset_t`. The matrix handles gain and axis misalignment;
the offsets handle static bias. Fit these with known fields/rotations and retain
the calibration record with its evidence and valid temperature/time range.

The helper returns the equal-weight mean in tesla, all four lane fields,
observed skew and calibration identity. It does not modify raw data. Missing,
saturated, mismatched or excessive-skew groups are rejected; no subset average
is substituted. A 1 ms skew limit is a useful initial **bench policy**, not a
qualified sensor-time accuracy specification. The caller must choose and justify
the limit for the experiment. Generic ideal simulation and legacy A2 captures
lack array timing evidence and cannot qualify as coherent quartets.

For equal, independent noise, four sensors reduce RMS noise by approximately
sqrt(4) = 2 at the same bandwidth. They do not improve absolute accuracy without
calibration. Shared supply/USB interference, thermal drift and magnetic gradients
do not average away. Keep individual channels to measure covariance and detect
outliers. Do not subtract the common field: that would also remove the intended
geomagnetic signal. Generate any slower 1 Hz product with a documented low-pass
filter before decimation, retaining the 10 Hz raw record.

No nanotesla noise floor is certified by this design. Bench qualification must
measure per-axis spectra and cross-sensor covariance with one versus four active
modules (to detect excitation cross-talk), simultaneous POLL/DRDY timing, cold
and warm calibration, USB traffic and cable-current effects, and field gradients.
Use a quiet reference instrument and report bandwidth with RMS noise. The
[QuadMag research](https://gi.copernicus.org/articles/11/375/2022/) demonstrates
the multi-RM3100 method; its measured performance is not a specification for this PCB.

## Spacing qualification

Qualify the installed 30 mm grid with the intended enclosure, cable and mounting
hardware. Keep the sensor assembly rigid and its orientation fixed. Place the
Pi, FPGA, fans and power converters remotely and route supply/return conductors
together without loops around or underneath the sensor grid. Ordinary copper
shielding does not screen the quasi-static magnetic fields of interest; magnetic
shielding around the operating head would also alter the desired field.

Use a magnetically quiet chamber/reference and an adjustable nonmagnetic fixture
to compare 30, 40 and 50 mm center pitches if necessary. These are test positions,
not manufacturer minimum distances. Record actual sensing-coil locations and
orientations, since module-center spacing alone does not describe every coupling
path. Preserve the intended simultaneous trigger, cycle count, temperature,
bandwidth and electronics position when comparing pitches.

1. Keep a designated receiving module powered throughout each comparison. With
   an independently selectable bench interface, compare companions idle and
   measuring, then repeat for each receiving module. B1's shared CS broadcasts
   to all four, so this requires a separate fixture; the production firmware
   cannot select just one module. Also compare companion population/power states
   separately, since passive cores and power-cycle offsets can change the bias.
2. Compare per-axis spectra, trigger-correlated transients, mean shifts and the
   covariance matrix of noise with all modules active. Do not estimate noise
   correlation from an uncorrected outdoor record: real geomagnetic variation is
   correlated too. Preserve all raw lanes and report reference uncertainty.
3. Repeat with quiet versus busy USB, representative host loads, cable positions
   and thermal conditions. Move the whole head away from interfering equipment
   independently of changing the grid pitch, to distinguish the two mechanisms.
4. Record the filter, passband, integration time and confidence bounds with every
   result. For a prospective 1 nT RMS product, 0.2 nT RMS added interference and
   at least 1.8x noise improvement over the RMS-equivalent individual sensor are
   useful initial engineering acceptance targets, not measured specifications.
   Reject an inconclusive comparison rather than interpreting it as no coupling.

Retain 30 mm if it meets the experiment's explicit limits. If a wider pitch
reduces companion interference sufficiently, revise the PCB, native SES, model
and geometry fixtures together. If host/USB or thermal effects dominate, improve
those sources and installation first. No universal safe distance or sub-nanotesla
performance is established by the present CAD checks.

## Layout and validation limits

Keep the complete head away from the Pi, fan and FPGA. Its own USB MCU and
cable current can still contaminate magnetics; compare quiet and active USB
conditions, calibrate the installed orientation and use nonferrous hardware.
The 18 shared SPICE cases include bounded USB cable/PTC loss, ideal LDO headroom,
sensor-switch on resistance and CC pull-down corners. They do not simulate USB
enumeration, signal integrity, regulator stability, ESD or firmware behavior.

Select a fabrication stackup and review USB impedance/return paths before
manufacturing. Native KiCad checks establish geometry and connectivity only.

## Manufacturer references

- [STM32F042 family datasheet](https://www.st.com/resource/en/datasheet/stm32f042t6.pdf)
- [TPS22919 datasheet](https://www.ti.com/lit/ds/symlink/tps22919.pdf)
- [AP2112 datasheet](https://www.diodes.com/datasheet/download/AP2112.pdf)
- [USB4105 drawing](https://gct.co/files/drawings/usb4105.pdf)
- [PNI RM3100 board manual, local manufacturer reference](../hw/shared/reference/rm3100-board.txt)

## SHT45 acquisition and installation

Use high-precision command `0xFD` at address `0x44`, with a STOP followed by
at least 8.3 ms before reading six bytes (the reference driver waits 9 ms).
Check the CRC of each two-byte word: polynomial 0x31, initial value 0xFF.
Publish both original words and CRCs as sensor 17 `ClimateRaw`, once per second,
with MCU acquisition timing. A failed read produces missing data and bounded
recovery; it never becomes a zero-temperature or zero-humidity reading.
The fixed profile exposes no heater command. See the
[Sensirion SHT4x datasheet](https://sensirion.com/resource/datasheet/sht4x).

Temperature is `-45 + 175 * raw / 65535` degrees Celsius. Relative humidity is
`-6 + 125 * raw / 65535` percent; clip the display to 0-100% while retaining
unchanged raw bytes. Keep the sensing opening free of solder flux, coating and
potting. Inside a sealed buried enclosure, this measures enclosure air and
helps detect condensation/leaks; it does not measure soil water content.
Board heat and the enclosure's equilibration delay require characterization.

The browser workbench runs the command-aware reference driver against a modeled
bus, including both CRCs, independent magnetic/climate faults, recovery and raw
record/replay. It is not USB enumeration or STM32 firmware qualification.
The selected assembly identity is recorded under
[`hw/assembly/burrowlark-usb/`](../hw/assembly/burrowlark-usb/).
