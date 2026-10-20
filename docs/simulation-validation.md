# DAQHAT-01 simulation scope

Run `./lab.ps1 test -Profile simulation` (Linux: `sh lab.sh test --profile simulation`).
This rebuilds all three circuits and runs the hardware, software, native CAD,
routing replay, firmware and numerical/SPICE checks. Procurement is excluded by
one explicit test ID. Source CAD is read-only; reports live in the five retained
`.lab/runs/` directories. No instrument or live inventory connection is required.

A successful test run establishes that the implemented checks and model fixtures
pass. It does not turn a failing design target in a diagnostic report into a
pass. Keep the report's scope, corner assumptions and acceptance flags together.

## Pressure path

The 1–20 Hz landslide research profile records SDP32 average-until-read results
at **200 samples/s**. Ideal 20 Hz averaging loss is 0.142 dB and group delay is
2.25 ms. The old 80-to-20 Hz alias is removed from this sampling configuration;
the first relevant image is now 180 Hz. Raw data and timing bounds are preserved.
An alternating 1 ms scheduler-delay fixture checks interval metadata and the
continuous-integral reference independently of the bus model.

`pressure_pneumatics.py` specifies this external acoustic network:

```text
ambient -> 10 mm capillary -> 80 mL chamber -> 10 mm capillary -> 80 mL chamber
                                                                         |
                                                                    SDP32 (+)
                                                                    SDP32 (-)
                                                                         |
                                                               2 L reference volume
```

Both capillaries have 1.2 mm internal diameter. The reference equalizes through
the sensor's flow path. A sealed diaphragm assumption would give a misleading
result: the [Sensirion engineering guide](https://sensirion.com/media/documents/C3059EE6/667E9FD4/DP_AN_Engineering_Guide_V1.0.pdf)
explains why flow through these sensors loads attached pneumatic networks.
Use a sealing manifold adapter for the SDP32 ports; this model does not specify
a manufactured adapter, weather barrier or dust filter. The volumes are external
to the HAT enclosure and are not included in Gerber/BOM/CPL exports.

Pressure/flow use the voltage/current analogy. Chamber compliance is `V/(gamma P)`.
The circular-tube impedance uses the oscillatory viscous-flow Bessel solution
with an explicit end-inertance allowance, rather than treating the Poiseuille
resistance as valid at every frequency. The low-frequency limit is independently
checked against Poiseuille resistance and the 4/3 inertance correction; see
[Womersley's derivation](https://pmc.ncbi.nlm.nih.gov/articles/PMC1365740/).

The retained report sweeps 256 corners: diameter ±3%, chamber volume ±10%,
−10 to 40 °C, 80–105 kPa, chamber gamma 1–1.4, internal clock 1.8/2.2 kHz,
and assumed sensor first-order time constants 0/3 ms. The step-response
specification does **not** guarantee a first-order transfer; these are scenarios.
Host-sampling images into 1–20 Hz are evaluated through 4.4 kHz, including
images near the internal conversion clock. High-frequency lumped-model results
are diagnostic: compressible chamber/tube modes are not included.

Within an assumed sensor resistance of **10^8–10^10 Pa·s/m³**, the design
allocation is gain between −6 and +3 dB across 1–20 Hz and alias amplitude below
−40 dB for uniform sampling. The amplitude allowance preserves at least half
the input signal; it is not a landslide detection threshold. A 10^7 Pa·s/m³
negative control fails the band-gain allocation. No manufacturer resistance
bound for SDP32 has been established, so `conditional_design_pass` applies only
to the stated envelope. Keep that unknown visible. Wind, leaks, nonlinear flow,
noise spectra, rigid-volume accuracy and timing-modulated aliases are not covered
by the uniform alias sweep. Software jitter tests establish data semantics only.

## RF network

`field_solver.py` solves the electrostatic potential on a rectangular conforming
mesh. Dielectric interfaces and copper edges fall on mesh lines; flux gives
Maxwell capacitance. A second vacuum solve supplies quasi-TEM inductance.
Reciprocity, passivity, uniform-dielectric scaling, analytical microstrip
agreement and mesh convergence have independent tests.

`simulate_signal_integrity.py` reads the native 0.17 mm tracks, their 3.79 mm total
length, the 0.0994 mm reference spacing and pad dimensions. Native C148/L140/D140/
C151 values are checked before using the circuit model. Nominal filled-mask
impedance is approximately 46.2 Ω. The mask model bounds bare copper and a
planar filled coating; it does not resolve a conformal coating or nearby coplanar
metal. Etch ±20 µm, dielectric thickness ±10%, epsilon 3.8–4.6 and mask 0–25 µm
are engineering sensitivity ranges, not supplier tolerances.

The ABCD network includes distributed traces, pad capacitance, a series capacitor,
RF choke with self-capacitance, bypass/connector parasitics and ESD capacitance.
The [Nexperia datasheet](https://assets.nexperia.com/documents/data-sheet/PESD5V0F1BL.pdf)
supplies the 0.4 pF typical and 0.55 pF maximum diode values at its stated test
conditions. Its use at GNSS frequencies is a lumped approximation. The remaining
parasitics and their multipliers are assumptions recorded in the JSON.

Nominal network loss is approximately 0.42 dB with 10.5 dB return loss. The
sampled sensitivity envelope reaches approximately **1.03 dB loss and 6.83 dB
return loss**, missing the 1 dB / 10 dB allocations. Consequently
`all_corners_meet_targets` is false. Changing only the blocking-capacitor value
does not resolve the modeled reflection. These assumptions do not justify
claiming a robust RF pass or changing the PCB matching network without a better
pad/connector model. The PCB retains its existing RF circuit.

## Adjacent signal layers

Native In2/In3 segment lengths, widths and offsets feed coupled capacitance and
inductance extraction. The stress cross-sections add 20 µm width, reduce the
central dielectric by 10%, and use epsilon 4.6. Separated parallel regions are
collapsed into a coherent equivalent line for each net pair. That is a scenario,
not a proof that it bounds every whole-net topology.

Each pair is exercised at 0.5/2 ns edge times, 20/100 Ω aggressor drive,
20 Ω/4.7 kΩ quiet termination and 2/10 pF end loads, at a 3.465 V step. A passive
six-section coupled LC ladder predicts near/far-end excursions. Doubling the
section count and halving the timestep checks convergence; an independently
generated ngspice circuit agrees within 5 mV. A disconnected-coupling control
must produce zero noise, and an excessive parallel-length fault must increase it.

Worst modeled pair excursion is approximately 0.43 V on IMU3_INT/SPI_MISO;
the largest Pi-connected pair is approximately 0.19 V. These are sensitivity
results, not universal receiver margins. The model excludes perpendicular
crossings, vias, same-layer coupling, whole-net reflections, simultaneous
aggressors and nonlinear receiver behavior. It replaces a length-only estimate
with a reproducible electrical model while preserving those limits explicitly.
