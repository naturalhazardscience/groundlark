# Sensor contract v1

`Calibrated.geophone_input_v` (optional field 7) carries measured J90 differential volts from a static electronics calibration. It is not velocity. Raw ADC counts remain unchanged. Version 2 calibration artifacts bind to device identity and effective sensor configuration; see [calibration](calibration.md).

Status: implemented schema, Python reference checks and USB framing; Pi drivers and Skylark STM32 firmware implemented; Burrowlark prototype firmware implemented; physical qualification remains pending. This document owns semantic rules. The
[Protobuf schema](../sw/interfaces/proto/groundlark/sensor/v1/sensor.proto) owns
field numbers/types. Both apply. A configured FPGA is unnecessary.

## Identity and versioning

Every Envelope has version 1, a nonempty device_id of at most 32 ASCII characters
from letters, digits, underscore, dot, colon and hyphen, and a nonzero fixed64
boot_id. Device IDs are provisioned physical/logical producer identities, never
USB port paths. Pi software generates a fresh random boot_id at each acquisition
session; the MCU needs a persistent counter or host-provided session nonce before
streaming. Reusing boot_id after a reset is prohibited. Identity is advertised
before configuration or data and after reconnect.

One envelope contains identity, effective configuration, a sample batch, or
status. Unknown envelope versions/body kinds and enum values are rejected.
Unknown additive Protobuf fields are preserved by the reference parser and may
be ignored by consumers. Never reuse field numbers; reserve removed names and
numbers. Buf FILE rules compare against the checked-in initial descriptor
baseline. Changes to these semantic rules need review even if Buf accepts them.
Breaking meaning/units requires a new package and envelope version.

| Sensor ID | Board and model | Raw representation |
| --- | --- | --- |
| 1–3 | DAQHAT-01 LSM6DSO U11–U13 | Signed 16-bit XYZ acceleration/gyro counts; optional signed temperature |
| 5 | Legacy SCL3300 U20 (removed from current DAQHAT-01) | Signed 16-bit XYZ acceleration and/or angle counts, optional temperature, required 16-bit device status |
| 6 | Legacy DAQHAT-01 MAX-M10S U21 (absent on DAQHAT-01) | Complete 92-byte UBX NAV-PVT payload, excluding UBX header/checksum |
| 7 | USB head RM3100 U2 (B1 slot 0; legacy single sensor) | Signed 24-bit XYZ counts, sign-extended into sint32 |
| 8 | DAQHAT-01 DLVR U23; legacy USB head supported | Four original response bytes, preserving pressure, temperature and status bits |
| 9 | DAQHAT-01 ADS122C04 / Racotech vertical | Signed 24-bit ADC count in sint32; required uint8 conversion counter |
| 17 | Burrowlark SHT45 U6 | Six original temperature/humidity bytes, including both CRC bytes |
| 18 / 19 / 20 | Burrowlark B1 RM3100 U7 / U8 / U9, slots 1 / 2 / 3 | Signed 24-bit XYZ counts, separately retained |

Skylark uses board ID 3 and MCU clock domain 2:

| Sensor ID | Model/channel | Raw representation |
| --- | --- | --- |
| 10 / 11 | SGX-7SO2-AQ-20 working / auxiliary | Independent signed 24-bit ADC count and required uint8 conversion counter |
| 12 / 13 | SGX-7H2S-AQ-25 working / auxiliary | Independent signed 24-bit ADC count and required uint8 conversion counter |
| 14 | PMS5003 | Complete 32-byte frame, including header, length and checksum |
| 15 | SHT40 | Six original temperature/humidity bytes, including both CRC bytes |
| 16 | Bosch BMP3 (current BMP388; legacy BMP390) | Six pressure/temperature bytes, plus all 21 factory trim bytes |

Skylark's fixed profile uses external 2.5 V reference, gain 1, PGA bypass and
normal 20 SPS single-shot ADC conversions: AIN0/1/2/3 map to IDs 10/11/12/13.
Each channel's nominal publication period is 240,000,000 ns. IDs 14–16 use
1,000,000,000 ns. Other settings are rejected by this profile. Sensor 15 uses
high precision with no heater; sensor 16 uses pressure ×8 / temperature ×2
oversampling at 3.125 Hz with IIR off. A different profile needs explicit schema
and driver support before use. See [firmware operation](../sw/skylark/README.md).

PMS frames require header `42 4d 00 1c`, sum of bytes 0–29 equal to the final
big-endian uint16, and error byte 29 zero for usable samples. Atmospheric
PM1/PM2.5/PM10 are the big-endian uint16 fields at offsets 10/12/14 (µg/m³).
SHT words each use CRC-8 polynomial 0x31, initial 0xFF. BMP raw values are
unsigned 24-bit little-endian pressure then temperature, with original trim.
Host display uses Bosch factory compensation and SHT's transfer equations;
recorded bytes are unchanged. No gas calibration or concentration is implicit.

Firmware identity lists the board's fitted inventory. Failed device probes
remain in configuration as disabled entries with period zero. Gas-cell presence
cannot be detected merely by successfully probing the shared ADC. Warmup,
invalid/stale frames and unavailable conversions produce missing samples with
no raw payload. Loss is unknown where acquisition history cannot establish it.
The firmware's MCU timestamps are scheduler timestamps with unknown acquisition
uncertainty; no host/MCU/UTC correlation is claimed.

ID 9 uses the Pi MONOTONIC_RAW clock, gain 64, reference 2.048 V and nominal
period 3,030,303 ns (330 SPS). ADC input volts = count × reference / (gain × 2²³).
Velocity requires frequency-response correction and calibration; none is implicit.
The current DAQHAT-01 inventory is 1–3, 8 and 9. IDs 4, 5 and 6 retain their
legacy IMU, inclinometer and GNSS semantics. None is advertised by current acquisition.

The model is fixed by v1 sensor ID. Another model requires explicit schema
evolution, not relabeling. Identity advertises only physically fitted sensors;
the DNP pressure sensor is absent by default. Identity.firmware_version is the
producer software build ID, including for the Pi. Raw axes are each package's
documented axes, without inferred board alignment. The three IMUs remain separate. Sensor ID 4 retains its IMU wire semantics for legacy recordings; the current HAT does not advertise it.
Legacy tilt angles retain the manufacturer's per-axis convention; they are not Euler
angles. The acquisition adapter must check SPI/UBX integrity before publishing.

## Configuration and interpretation

Configuration advertises an **effective** revision greater than zero. Revision
increases within a boot; it changes whenever sampling mode, range or configuration
changes. A batch names exactly that revision. Receivers must reject/quarantine
data until the matching identity and configuration have been received. No
unacknowledged control command is defined by this milestone.

Up to eight unique sensor entries are allowed. Enabled entries have a positive
nominal period_ns, at most 60 seconds. Disabled entries have period zero.
The period is a requested/effective nominal interval, not proof that a device
supports the rate; the real adapter must reject unsupported hardware settings.
It must report readback/effective settings before data, never silently round.

Enabled IMUs require acceleration_range_g (2, 4, 8 or 16) and
angular_rate_range_dps (125, 250, 500, 1000 or 2000). Legacy SCL3300 requires tilt_mode
1–4. RM3100 requires each XYZ cycle count in 1–65535; timing limits still apply.
Pressure requires the actual part number and finite pressure_min_pa <
pressure_max_pa from that part's transfer function. MAX-M10S uses the period
and the fixed NAV-PVT payload profile. Configuration fields belonging to another
sensor are invalid. Optional register_config contains at most 32 sorted, unique
8-bit address/value pairs for LSM6DSO or RM3100; it is empty for other models.
Driver-specific bus setup and filter controls must be captured by the eventual
adapter configuration/recording metadata before hardware acquisition is qualified.

## Burrowlark array timing

`Sample.magnetic_timing` (field 21) is optional evidence for magnetic IDs
7/18/19/20. `cohort` is required when the message is present and equals the
per-lane sequence. All four members of a B1 quartet share the same cohort and
`trigger_ns` (completion of the broadcast POLL command). `ready_observed_ns`
records each DRDY interrupt observation, in the same MCU_MONOTONIC domain.
Trigger must precede or equal DRDY, which must precede or equal read completion
in `time.acquisition_ns`. Missing slots can omit trigger/ready fields; absence
does not mean zero. Usable samples with array timing require both observations.

Group by device, boot, configuration revision, cohort and trigger, never by USB
arrival or nearest timestamp. Legacy data and generic ideal simulation can omit
this evidence and cannot establish a coherent quartet. The MCU records evidence;
the experiment supplies a completion-skew limit and individual gain/offset/axis
calibration before averaging. No sample-time or UTC accuracy follows from the
1 microsecond timer resolution. Internal RM3100 conversion clocks are independent.

## Time, ordering and loss

Timestamp.domain is PI_MONOTONIC_RAW for IDs 1–6 and 9, and MCU_MONOTONIC for
IDs 7 and 10–20. Pressure ID 8 uses PI_MONOTONIC_RAW on DAQHAT-01 and retains MCU_MONOTONIC
for legacy USB-head recordings. Session validation binds the pressure clock to
the advertised board identity. The Buf compatibility baseline is retained; the B1 array adds IDs and optional timing without changing legacy raw semantics.
acquisition_ns is required with explicit presence: zero is a valid timestamp.
MCU ticks are extended through timer wraps before conversion to nanoseconds;
a reset begins a new boot/session. No timestamp wraps or decreases within a
session. MCU time and Pi monotonic time have unrelated origins and rates.
Report uncertainty_ns only when bounded; absent means unknown. Resolution is
not accuracy. For polled/FIFO devices, include readout/sample-age uncertainty.

UTC is an optional correlated estimate with an explicit utc_uncertainty_ns.
Neither UTC field may appear alone. POSIX UTC nanoseconds exclude leap seconds;
omit the estimate when the leap-second mapping/correlation is ambiguous.
The Pi must retain the original acquisition time and later record its correlation
and arrival time separately. USB arrival time cannot populate acquisition_ns.
For GNSS, the Pi acquisition timestamp describes capture of the NAV-PVT message;
the actual navigation epoch and fix flags remain in NAV-PVT. A VALID sample
does **not** mean that NAV-PVT reports a valid position or UTC fix.

Sequence is an explicit uint64 per sensor and boot, starting at zero; zero must
be encoded with presence. It advances for every accounted acquisition slot,
including known failed/dropped slots. A batch has 1–4 samples from one sensor,
one configuration and one clock. Within a batch sequences are consecutive and
acquisition times strictly increase. Split batches at a known loss, reset or
configuration change. Exhausting uint64 starts a new session, never wraps.

dropped_before is the number of known discarded slots before this batch since
the prior batch, including initial discard. Explicit zero means none; absence
means unknown. It cannot exceed the first sequence. A missing placeholder already
occupies a sequence slot and must not also be counted as discarded. Unknown FIFO
loss needs BUFFER_OVERFLOW status and absent loss count, never a fabricated zero.
Receivers must enforce cross-batch ordering, configuration and reset epochs in
the acquisition layer (step 2); the current validator is stateless.

Quality is required. VALID and SATURATED retain raw measurements. MISSING has
neither raw nor calibrated values; its timestamp is the scheduled/estimated slot
with honest uncertainty. FAULT retains a captured but suspect raw response and
has no calibrated values; a failed read without bytes is MISSING plus IO_ERROR.
Pressure responses with non-normal sensor status cannot be labeled VALID or
SATURATED. Status may target one sensor or zero for the producer. Status detail
is at most 96 UTF-8 bytes with no control characters. Optional dropped_total is
a cumulative known loss count for the current sensor/boot, not a reset counter.

## Calibrated values

Raw values are always retained. Calibrated doubles are optional, finite, in SI:
m/s², rad/s, rad, tesla, pascal and kelvin. Temperature cannot be below 0 K.
Vectors require all three axes, including explicit zeroes. Values remain in
sensor package axes; no implicit rotation into geographic or HAT axes occurs.
Calibration requires a nonempty calibration_id naming immutable coefficients,
units, method and provenance stored with recordings by the acquisition layer.
No anonymous/default calibration is permitted. Calibrated values are allowed
only for VALID/SATURATED samples and must match the sensor kind. GNSS is kept
losslessly as NAV-PVT in this revision; position/fix decoding is later work.

## USB CDC framing and bounds

Protobuf does not define byte-stream boundaries. A frame is:

1. Serialize one Envelope, **1–1024 bytes**.
2. Append CRC-32/ISO-HDLC of that payload as four little-endian bytes.
   Parameters: reflected polynomial 0xEDB88320, initial/xorout 0xFFFFFFFF;
   the check value for ASCII `123456789` is 0xCBF43926.
3. COBS-encode payload plus CRC and append a zero delimiter.

Maximum decoded length is 1028, encoded length is 1033 and wire length including
delimiter is 1034 bytes. Send an initial zero when opening a stream. Ignore empty
delimiters. Check length, COBS and CRC **before** Protobuf decoding, then apply
semantic validation. A sample-count limit never overrides the payload-byte
limit; split batches as needed. These bounds apply equally to recordings.

On corruption, drop that frame, increment a visible error counter and resume at
the next delimiter. On overflow, discard without buffering until a delimiter.
Disconnect resets partial framing state and requires identity/configuration
again. A partial frame without a delimiter is bounded but needs a transport
timeout in the transport layer (implemented as one second). The decoder yields
frames rather than accumulating an
unbounded list. Its caller must exhaust each feed iterator and use a bounded
dispatch queue. CRC detects accidental corruption; it is not authentication.

## MCU feasibility and remaining gates

The STM32F042K6 has **6 KiB SRAM and 32 KiB flash**. Nanopb is the candidate C
codec because bounded fields can use static allocations; proposed bounds are in
[sensor.options](../sw/interfaces/proto/groundlark/sensor/v1/sensor.options).
One RX encoded buffer (1033 bytes), one TX buffer (1034 bytes), and a provisional
2048-byte cap for decoded messages total **4115 bytes**, leaving **2029 bytes**
for USB state, sensor queues, stack and other globals. This is a tight budget,
not a measured fit or a firmware selection. Prefer in-place RX decoding and
streamed TX/one message at a time; do not queue decoded Envelopes on the MCU.

Before selecting Nanopb, generate/compile the C codec, check ARM structure sizes,
link the actual USB stack, enforce RAM/flash limits and measure stack high-water
marks under reconnect/overflow. If it does not fit, stream batch elements or
reduce the head's batch cap; do not silently truncate data. The Python reference
implementation and options file do not prove C interoperability or MCU fit.

Implemented checks include a manually specified binary producer fixture,
signed-count boundaries, missing/zero distinction, all eight sensor payloads,
timestamp/sequence rules, corruption, arbitrary frame splits, resynchronization,
overflow, and a deliberate incompatible schema change rejected by Buf.
The [acquisition layer](sensor-software.md) implements cross-batch state,
bounded recovery, calibration artifacts, recording/replay and modeled/Linux
adapters. Polling leaves conversion uncertainty and physical loss unknown.
USB enumeration, MCU firmware and physical testing remain open.

References: [Protobuf presence](https://protobuf.dev/programming-guides/field_presence/),
[Buf breaking checks](https://buf.build/docs/reference/cli/buf/breaking/),
[Nanopb allocation bounds](https://jpa.kapsi.fi/nanopb/docs/concepts.html),
[STM32F042 datasheet](https://www.st.com/resource/en/datasheet/stm32f042t6.pdf),
[LSM6DSO](https://www.st.com/en/mems-and-sensors/lsm6dso.html),
[SCL3300](https://www.murata.com/-/media/webrenewal/products/sensor/pdf/datasheet/datasheet_scl3300-d01.ashx).

## Burrowlark enclosure climate

Sensor ID **17**, SHT45 U6, belongs only to the USB head (board kind 2), alongside
RM3100 ID 7. It uses the existing `ClimateRaw` message with six original response
bytes and both valid Sensirion CRCs. Acquisition timestamps use the MCU monotonic
domain. Its only supported enabled profile is high precision, heater off,
1,000,000,000 ns publication period with no additional configuration fields.
Temperature/humidity display conversion is the same as SHT40 ID 15. Keep raw
precision and explicit missing/unknown values. Existing magnetometer-only
recordings remain valid; absence of sensor 17 is not a zero climate reading.
