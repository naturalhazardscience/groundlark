# Sensor bandwidth and timing

DAQHAT-01 U23 is an SDP32-125PA at I2C 0x21. Its landslide research profile
targets a **1–20 Hz pressure band**, acquiring at 200 Hz with differential
pressure compensation and **average-until-read command 0x3615**. Raw recordings
retain all nine response bytes and bounds on the interval between reads.
The port/tubing response, alias rejection and usable noise floor remain unmeasured.

These specifications cover the current Groundlark FPGA HAT and Skylark USB.
Raw recordings preserve sensor counts. They do not apply inverse response,
gas compensation, or a shared phase correction. Modeled response is not
physical qualification.

## Groundlark

### Infrasound selection and limits

The 1–20 Hz choice covers debris-flow observations from four field sites in
[the 2011 multi-site study](https://rosa.uniroma1.it/rosa02/engineering_geology_environment/article/view/1317).
[Marchetti et al. (2019)](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2018JF004785)
found a roughly 5 Hz infrasound peak at Illgraben and processed 1–10 Hz array
signals. A [Beijing field study](https://dzkjtb.cug.edu.cn/en/article/doi/10.19509/j.cnki.dzkq.tb20240223)
found 6–15 Hz useful for separating debris flows from local background. Retain
both diagnostic bands, 1–10 and 6–15 Hz, during subsequent analysis; do not narrow
the recording to a single 5 Hz tone. These results concern moving debris and
depend on site and propagation. They do not establish a universal precursor
frequency, a detection range, or a warning threshold for all landslide types.

The [Sensirion digital datasheet](https://sensirion.com/media/documents/4D045D69/6375F34F/DP_DS_SDP3x_digital_D1.pdf)
specifies nominal 2 kHz internal conversions (1.8–2.2 kHz). Arithmetic averaging
applies for the first 25 ms between reads; longer windows change to exponential
averaging. The driver discards uncertain or overlong windows with `DataGap`,
then resumes without resetting a healthy sensor. Reads less than 1 ms after the
previous transaction complete return `NotReady`. These are host transaction
bounds, not conversion times or measured sensor/filter delay.

At ideal 200 Hz service, the nominal ten-conversion boxcar contributes:

| Frequency | Averaging gain | Ideal averaging delay |
| --- | --- | --- |
| 1 Hz | −0.00035 dB | 2.25 ms |
| 5 Hz | −0.0088 dB | 2.25 ms |
| 10 Hz | −0.035 dB | 2.25 ms |
| 20 Hz | −0.142 dB | 2.25 ms |

This is not the complete pneumatic or sensor response. Reset phase and bus
timing add uncertainty. The former 80 Hz input stays at 80 Hz. A 180 Hz input
now aliases to 20 Hz at about −19.1 dB;
averaging alone is **not adequate evidence of anti-alias performance**. Filtering
after acquisition cannot remove that alias. Run the reproducible model with
`python sw/tools/pressure_response.py`; the portable software profile retains
its report and tests 1/5/12.5/20 Hz tones at 0.05/0.1/0.5 Pa through the driver.
These amplitudes test arithmetic and quantization, not physical sensitivity.
An independent integral fixture also checks alternating 1 ms service delays.
The [pneumatic design simulation](simulation-validation.md#pressure-path) combines
finite sensor flow, oscillatory tube impedance, chamber compliance and the actual
200 Hz averaging profile. It specifies an external accessory and its conditional
operating envelope; that accessory is not part of the PCB package.

One pressure count is 1/240 Pa. The specified 0.025 Pa zero-point repeatability
is not a noise spectral density or a guaranteed minimum detectable signal.
Keep the required noise floor and alarm threshold unset until the deployment's
distance, background and reference measurements support them. Use the
[pressure bench procedure](bench-procedure.md#3a-infrasound-response-and-aliasing)
to qualify the actual ports, reference volume, tubing and wind protection.
Coincident geophone observations can aid interpretation; they do not share the
pressure transfer function. Groundlark does not implement a validated alarm.

### Geophone and IMUs

The 4.5 Hz geophone measures ground velocity through its mechanical response,
coil/loading network, ADS122C04 PGA and digital filter. The nominal mechanical
response alone is down **26.13 dB at 1 Hz**. The PCB input network adds about
**0.011 dB at 10 Hz**. Sub-hertz velocity sensitivity cannot be recovered merely
by multiplying raw counts by the nominal 23.4 V/(m/s) sensitivity.

The ADC's nominal 330 SPS profile has an actual nominal period of 3116 clocks
at 1.024 MHz: **328.626 samples/s**, subject to oscillator tolerance. Its
digital filter has a **150.1 Hz −3 dB bandwidth**. Combined nominal estimates
from the mechanical model, routed component values and TI's response plot are:

| Input frequency | Combined attenuation relative to nominal velocity sensitivity |
| --- | --- |
| 1 Hz | approximately −26.1 dB |
| 10 Hz | approximately −0.2 dB |
| 100 Hz | approximately −1.4 dB |

Allow approximately 0.5 dB uncertainty for reading the ADC plot; this is not a
device tolerance. Coil resonance, damping, sensitivity and passive tolerances
add uncertainty. The digital filter is linear phase, but its coefficients and
exact delay are not provided by this analysis. Conversion duration is not a
measured group delay. See [TI SBAS751B, §§8.3.5–8.3.6](https://www.ti.com/lit/ds/symlink/ads122c04.pdf).

The IMU driver explicitly writes and verifies its high-performance filter
settings and records them in `register_config`. Accelerometer LPF2 and the
high-pass paths are disabled; gyro LPF1 is bypassed and LPF2 remains active.

| IMU output rate | Accelerometer LPF1 cutoff | Gyro LPF2 bandwidth |
| --- | --- | --- |
| 26 Hz (default) | 13 Hz | 8.3 Hz |
| 52 Hz | 26 Hz | 16.6 Hz |
| 104 Hz | 52 Hz | 33 Hz |
| 208 Hz | 104 Hz | 66.8 Hz |

At the default gyro setting, ST reports −36° phase at 2.5 Hz, equivalent to
40 ms phase delay **at that frequency**. Do not apply that as a constant delay
to every channel or frequency. FIFO timestamps identify sensor time slots;
they do not remove internal filtering delay. Bandwidth figures and this phase
point come from [ST AN5192, accelerometer and gyroscope bandwidth sections](https://www.st.com/resource/en/application_note/DM00517282-.pdf).

## Skylark

The working and auxiliary electrode paths have nominal **15.9 Hz feedback**
and **1.59 Hz output** poles. Their cascaded electronics settle to within 1% of
an ideal current step in approximately **471 ms**. This excludes cell chemistry,
potentiostat dynamics, enclosure exchange and the ADC. Attenuation at 0.1 Hz is
about 0.017 dB. Nominal conversion factors remain 40 mV/ppm for SO₂ and 34 mV/ppm
for H₂S; actual cells require calibration.

The normal 330 SPS single-shot ADC takes 3,141 clock periods: about 3.067 ms,
or 3.130 ms at a 2% slow oscillator. Firmware schedules reads eight milliseconds
apart, with a separate five-tick guard after each START command. The 100 kHz
I²C status/data/mux/readback/start transactions consume approximately 2.44 ms
including small bus-transition allowances. The native fixture advances the
clock during these transactions and checks conversion readiness independently.
Each electrode has a nominal **32 ms period (31.25 Hz)**. Longer delays are
visible in timestamps and sequence gaps; no catch-up conversion burst is used.
Timestamps mark service time, not the center of the integration window.

The analog circuit attenuates the first nominal alias at 31.25 Hz by **32.7 dB**.
A deliberately conservative scenario with half the nominal output capacitance
and low resistor/feedback-capacitance tolerances gives about **26.4 dB**. That
scenario is not a guaranteed MLCC limit: qualify effective capacitance under
bias, temperature and aging. Neither figure establishes a system noise floor.
Electrical injection is still needed at mains frequencies and around multiples
of the actual sample rate. Digital filtering cannot remove prior aliasing.

Faster conversion increases individual ADC noise. TI table 3 gives typical
18.58 µV RMS at 330 SPS, gain one, PGA bypassed, 3.3 V supply and internal
2.048 V reference. That is roughly 465 ppb SO₂-equivalent per raw conversion at
nominal gain; it is not a measured Skylark detection limit. Averaging can reduce
uncorrelated noise, but reference noise, drift and electrode correlation need
measurement. Preserve raw readings and apply a qualified averaging/calibration
policy when reporting trends. No firmware decimation or averaging changes the
recorded counts. The old 240 ms profile remains accepted for recorded sessions.

WE and AE remain sequential, about 8 ms apart. Identical sinusoidal pickup leaves
`2 × |sin(π × f × 0.008)|` after unadjusted subtraction: approximately 0.5% at
0.1 Hz and 5.0% at 1 Hz, before filter mismatch. Compensation must account for
actual timestamps and measured cell behavior.

Both selected SGX cells specify T90 below 60 seconds. That upper limit neither
defines their full transfer functions nor guarantees rejection of rapid inputs.
It also cannot suppress electrical noise introduced after the cell. References:
[SO₂ DS-0685](https://sgxsensortech.com/uploads/f_note/DS-0685-SGX-7SO2-AQ-20.pdf),
[H₂S DS-0681](https://sgxsensortech.com/uploads/f_note/DS-0681-SGX-7H2S-AQ-25.pdf).

SHT40 measurements and PMS5003 frames are published at 1 Hz; conversion time or
frame cadence does not establish their environmental response. BMP388 uses
pressure ×8 / temperature ×2 oversampling at 3.125 Hz, with IIR off, and publishes
the latest reading at 1 Hz. This pressure stream is intended for weather trends;
it is not a qualified infrasound channel. Its rate reduction has no added
anti-alias filter. See the [BMP388 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp388-ds001.pdf).

## Reproduction and qualification

`./lab.ps1 test` (or `./lab.sh test`) runs
[signal_response.py](../hw/tools/signal_response.py) and independent response
regressions. The bounded run retains
`results/hw/shared/simulation/signal-response/results.json`, including routed
PCB/source hashes, gain and phase calculations, passive corner scenarios,
ADC plot checkpoints, alias frequencies, timing and explicit unknowns. The
first-order gas examples are illustrative scenarios, not fitted sensor models.

Neither board has a qualified end-to-end noise floor or alias-rejection result.
Before interpreting field spectra, perform the sweeps and enclosure/cell step
tests in the [bench procedure](bench-procedure.md). Select a required signal
band, maximum interfering amplitude and allowable input-referred alias error
before passing the design. If it fails, reduce analog bandwidth or increase
acquisition rate with filtering before decimation; retain raw measurements and
requalify noise, timing, settling and firmware metadata for that configuration.
