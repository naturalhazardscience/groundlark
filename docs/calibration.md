# Calibrating Groundlark DAQHAT-01

Groundlark supports **measured static gain and offset** for the three IMUs and
the geophone electronics. Raw SSREC and miniSEED counts are retained. Calibration
does not establish geophone velocity response, absolute timing, alignment or a
noise specification. No physical calibration coefficients ship with the board.

## Equipment and identification

Give each assembled HAT a permanent serial label and use that identifier as
`device_id` in its Pi acquisition profile. Keep it with the HAT if the Pi is
replaced. The identifier is operator assigned; software cannot detect a swapped
unlabelled HAT. Record the geophone serial, cable, mounting, board revision,
software revision, reference instrument/certificate, date, temperature and
uncertainties. Recalibrate after sensor or analog component replacement.

Use an isolated precision millivolt source and calibrated differential meter
for electronics; a rigid six-face fixture for accelerometers; and a calibrated
rate table for gyro scale. Reserve a shaker/reference seismometer and a common
time reference for dynamic response testing. Characterize warm-up by watching
offset and temperature stabilize; a fixed delay is not proof of stability.

## PCB probe access

TP90–TP93 are bare **1.5 mm underside copper pads**, with no fitted parts or
additional GPIO. The 140 × 56 mm outline and R3 enclosure dimensions are retained.
Access requires removing the HAT from its stack; there are no live probe holes
through the enclosure. Use an insulated fixture, inspect polarity before power,
and keep probes away from adjacent supply contacts.

Coordinates below use the native PCB outline origin, before mirroring the board
for an underside view. References are also visible on the KiCad fabrication layer.

| Pad | Signal | Native X, Y (mm) | Measurement |
| --- | --- | --- | --- |
| TP90 | GND | 6.60, 47.00 | Meter/logic reference |
| TP91 | GEO_VCM | 4.05, 47.00 | Filtered bias, approximately half AVDD |
| TP92 | GEO_AVDD | 7.30, 40.65 | ADC analog supply, approximately 3.3 V |
| TP93 | GEO_DRDY_N | 9.175, 38.50 | Active-low ADC data-ready, 3.3 V logic |

Use high-impedance probes and account for their loading. Remove them before
low-noise measurements. TP93 permits an external logic analyzer to measure ADC
cadence; it does not by itself associate samples with UTC or remove ADC delay.
The driver still uses polling. The pads add no DAC, analog switch or permanent
stimulus load to the sensitive differential input.

## 1. Geophone electronics: zero and DC gain

1. Disconnect the geophone at J90. Verify AVDD and VCM. Record the exact gain,
   reference, sample profile and supply conditions used for the calibration.
2. Fit a **floating differential short between J90 pins 1 and 2**. Leave pin 3
   as shield/ground. Do not connect either signal pin to ground: the PGA inputs
   need their mid-supply bias. Record settled offset/noise with the same
   acquisition path used in deployment. A short test measures electronics,
   not sensor sensitivity or cable continuity.
3. Replace the short with an isolated differential millivolt source. Preserve
   the board's common-mode bias, and measure the actual differential voltage
   at J90 while connected. A grounded bench generator is not automatically
   suitable. Include the source impedance, meter loading and common-mode
   uncertainty in the bench record.
4. Measure negative, near-zero and positive levels well inside the configured
   range. Gain 64 / 2.048 V reference has nominal **±32 mV** full scale. Start
   with levels near ±10 mV; verify actual voltage and common-mode compliance
   before capture. Use additional levels and repeats to check nonlinearity.
5. Capture each settled level separately, with no active calibration:

   ```sh
   python -m groundlark.cli live --profile instrument.json \
     --seconds 30 --output negative.ssrec --no-miniseed
   ```

   Use explicit filenames such as `zero.ssrec` and `positive.ssrec` for the
   other levels. `--no-miniseed` is optional for these bench recordings.
6. Inspect a settled sequence interval. These example sequence limits must
   exist and be free of loss in your recording:

   ```sh
   python -m groundlark.cli calibration-observe negative.ssrec \
     --device GL-HAT-001 --sensor 9 --field geophone_input_v \
     --first 1000 --last 8000
   ```

   The command reports raw mean, sample standard deviation, count,
   configuration hash and recording hash. Increase acquisition capacity or
   repeat the capture when loss occurs; do not interpolate a calibration gap.
7. Copy [the voltage fit template](../sw/pi/profiles/geophone-calibration.example.json).
   Fill in actual device identity, conditions, measured voltages, positive
   reference uncertainties, sequence limits and acceptance limits. `null`
   entries intentionally fail. Choose stability and residual limits from your
   measurement requirements before inspecting the fit.
8. Fit and review:

   ```sh
   python -m groundlark.cli calibration-fit voltage-fit.json --output GL-HAT-001-cal.json
   ```

   Paths in the specification are relative to that specification. The output
   is a calibration list plus `GL-HAT-001-cal.json.evidence.json`. Check all
   residuals, reference uncertainty, temperature and measured input ranges.
   Verify the result with additional levels/repeats not used in the fit.

The fitted `geophone_input_v` means J90 differential input volts. It includes
the assembled DC electronics path. Do not divide this by nominal geophone
sensitivity and label the result broadband ground velocity. Reconnect the
sensor after the electronics test and separately measure complete-chain noise.
TI's ADS122C04 internal short can diagnose ADC offset, but switching modes and
automatically restoring/discarding settling samples is not implemented here.
See [the TI datasheet](https://www.ti.com/lit/ds/symlink/ads122c04.pdf).

## 2. IMUs: six faces and known rotation

Use [the IMU template](../sw/pi/profiles/imu-calibration.example.json) for
sensor IDs 1, 2 and 3 independently. Hold the assembly still in +X, −X, +Y, −Y,
+Z and −Z orientations in the **ST package axes**. Record after settling in
each position. Use the measured local gravity magnitude and fixture alignment
uncertainty to specify reference vectors. The other two axes are near zero;
their uncertainty must include tilt. A nominal gravity value is an assumption,
not a traceable measurement.

The fitter solves each axis's scale and offset from all faces. This is a
diagonal affine fit, not a 3 × 3 misalignment correction. Validate at additional
orientations and repeat each face to expose seating or thermal errors. Six-face
static calibration only covers approximately ±1 g, not the full ±2 g range.

Stationary gyro measurements characterize bias. To fit gyro **scale**, use
known positive, zero and negative rates on each axis, with reference values in
rad/s and `angular_rate_rad_s` as the field. A zero-rate recording alone cannot
determine scale, so the fitter rejects it. A temperature fit requires at least
three measured temperatures in kelvin; it does not compensate acceleration or
gyro drift with temperature. Reference methods are described in this
[MEMS calibration study](https://www.mdpi.com/1424-8220/12/7/9448).

## 3. Apply and preserve the result

```sh
python -m groundlark.cli live --profile instrument.json \
  --calibrations GL-HAT-001-cal.json --seconds 30 --output calibrated.ssrec
```

The list may contain one active record per sensor. Combine the independently
reviewed sensor records into one JSON list for a complete HAT. If fitting more
than one quantity for an IMU, put those fields in the same fit specification;
do not provide two active records for the same sensor.

Version 2 records are content-addressed and bind to `device_id`, sensor ID and
the complete effective sensor configuration. They contain the evidence SHA-256
(canonical sorted compact JSON), gain/offset, and measured raw mean bounds.
Keep the evidence sidecar and source recordings with the calibration list.
The SSREC header includes the calibration list; it does not embed every source
recording or the full evidence sidecar. Archive those files together.

Raw values, quality flags, gaps and timestamps remain intact. A derived field
is absent outside its measured raw range; for a vector, all three axes must be
within range. Missing/fault samples have no derived values. The calibration ID
alone is not proof that a sample contains a usable SI field. Software does not
enforce temperature, mounting or elapsed-time validity: the operator must keep
operation within the documented conditions and recheck drift.

Older unbound affine records remain readable for compatibility. Prefer version
2 for new instruments. Simulation fixtures require `--allow-simulation` and
are identified as synthetic in their evidence; they cannot calibrate hardware.

Fit inputs are bounded to 3–12 observations per field, 32–100,000 consecutive
samples per interval and 256 MiB per recording. Unknown loss, saturation,
faults, incomplete runs, overlapping reference intervals and changed sensor
configurations fail. The report includes sample scatter and fit residuals;
these are **not** a combined metrological uncertainty budget. The positive
reference uncertainties are recorded, not used as regression weights.

miniSEED continues to store raw integer counts. Archive response metadata
alongside it; this DC fit is insufficient to generate a measured StationXML
velocity response. See [miniSEED storage](miniseed.md) and the
[FDSN response model](https://docs.fdsn.org/projects/stationxml/en/latest/response.html).

## 4. Qualify the complete instrument

- **Geophone dynamics:** compare the installed sensor/cable/electronics chain
  with a calibrated reference on a shaker or in a coherent colocated test.
  Measure amplitude at multiple frequencies and levels; fit sensitivity,
  resonance and damping with uncertainty. Validate using separate data.
  Measure the actual motion; shaker drive voltage is not a motion reference.
- **Timing and phase:** use a common reference clock or measured synchronization
  uncertainty. Characterize ADC/IMU filtering delay separately from capture
  time. The GNSS revision captures PPS, but physical sample UTC remains unqualified. Do not
  claim phase calibration by aligning traces visually.
- **Infrasound:** equalize both SDP32 ports for zero, then compare pressure
  levels and frequency response with a calibrated low-pressure reference.
  Include the deployed tubing, inlet, wind filter and enclosure leakage. The
  current live acquisition and static fitter do not yet support this workflow.
- **Repeatability/noise:** repeat after warm-up, at deployment temperatures,
  with the FPGA off/on if fitted, and after reinstalling the assembly. Keep
  shorted-input noise separate from sensor/environment noise. Three IMUs on
  one board may share noise; do not assume independent self-noise.

These complete-chain methods follow the
[USGS Raspberry Shake evaluation](https://manual.raspberryshake.org/_downloads/RS4D-ASL-SRL.pdf)
and [PTB field calibration guide](https://www.ptb.de/empir2020/infra-auv/information-communication/publications/good-practice-guide/part-1-seismic-technology/field-calibration/).
AnyShake's [ADC calibration procedure](https://anyshake.org/docs/anyshake-explorer/E-C111G/advanced-operations/adc-calibration/)
is useful precedent for recording offsets, but its fixture and response must
not be transferred to this different front end. Keep the
[physical qualification checklist](bench-procedure.md) with each instrument's
measurements. PCB/ERC/DRC and software tests do not establish physical calibration.
