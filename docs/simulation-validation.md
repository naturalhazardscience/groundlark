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

`pressure_pneumatics.py` reads the [external pneumatic network](../hw/mechanical/daqhat-01-pressure/README.md):

```text
ambient -> four parallel capillaries -> 320 mL -> four parallel capillaries -> 320 mL -> SDP32 (+)
ambient -> separate slow reference vent -> 4 L reference ---------------------------> SDP32 (-)
```

Each main capillary is 10 mm long with 1.2 mm internal diameter. The reference
vent is 10 mm long with 0.3 mm internal diameter. Parallel capillaries lower source
impedance; proportionally larger chambers preserve filtering. The independent
vent equalizes the reference even when sensor flow tends toward zero. The
[Sensirion engineering guide](https://sensirion.com/media/documents/C3059EE6/667E9FD4/DP_AN_Engineering_Guide_V1.0.pdf)
provides approximate family-level flow estimates, not guaranteed SDP32 small-signal
resistance limits. Do not treat the sensor as a sealed diaphragm. Use a sealing
manifold adapter; the model does not specify a manufactured adapter, weather
barrier or dust filter. The external volumes are outside the PCB package.

Pressure/flow use the voltage/current analogy. Chamber compliance is `V/(gamma P)`.
Circular-tube impedance uses the oscillatory viscous-flow Bessel solution with
an end-inertance allowance. Independent fixtures check the Poiseuille limit,
4/3 inertance correction, parallel-tube scaling, open sensor flow and vent faults;
a separately assembled ngspice network also checks the vented nodal solution;
see [Womersley's derivation](https://pmc.ncbi.nlm.nih.gov/articles/PMC1365740/).

The report evaluates **4,096 corners**, with independent stage diameters ±3%,
chamber and reference volumes ±10%, vent diameter ±3%, −10 to 40 °C,
80–105 kPa, chamber gamma 1–1.4, internal clock 1.8/2.2 kHz and assumed
first-order sensor time constants 0/3 ms. Tube lengths remain nominal.
The step-response specification does not guarantee a first-order transfer.
An additional 101-point resistance sweep checks the interior at nominal geometry.
These sampled cases do not prove every combination of continuous parameters.

Across the **10^7–10^12 Pa·s/m³** resistance scenarios, gain is **−5.21 to
+2.07 dB** over 1–20 Hz and the largest uniform-sampling alias is **−53.22 dB**.
The unchanged allocations are −6 to +3 dB gain and alias below −40 dB.
The old 10^7 Pa·s/m³ failure now passes; the old geometry and 10^6 Pa·s/m³
remain independent failure controls. The amplitude allowance is not a landslide
detection threshold. `conditional_design_pass` remains conditional because no
manufacturer resistance bound has been established. Flow estimates at 100/500 Pa
cannot establish a small-signal bound; the 500 Pa family point exceeds SDP32's range.

Host-sampling images into 1–20 Hz are evaluated through 4.4 kHz, including images
near the internal conversion clock. High-frequency lumped results omit compressible
chamber/tube modes. Wind, leaks, nonlinear flow, sensor noise spectra and
nonuniform-sampling aliases remain outside this model. Software jitter tests
establish data semantics only.

## RF network

`field_solver.py` solves electrostatic potential on a conforming rectangular
mesh. Copper edges and dielectric interfaces fall on mesh lines; flux gives
Maxwell capacitance. A vacuum solve supplies quasi-TEM inductance. Reciprocity,
passivity, dielectric scaling, analytical microstrip agreement and mesh convergence
have independent fixtures.

The assembly selections are **Murata LQW15AN56NG80D, 56 nH choke (L140)** and
**LQW15AN3N6G80D, 3.6 nH series matching inductor (L141)**, retaining the 47 pF
C0G blocking capacitor and PESD5V0F1BL ESD protection. All five RF traces are
0.17 mm B.Cu over the 0.0994 mm reference spacing. Bias/ESD branches are shortened
to 1.02/0.80 mm; series segments total approximately 4.28 mm. Every RF segment,
value and selected MPN is checked against the model inputs. Reference-plane
coverage is checked outside the bounded SMA antipad; both shunt branches are
inside that unreferenced transition. Its surrounding return annulus is checked
separately. The line/connector surrogate does not solve this launch in 3-D.
L141 remains a VNA tuning position with provisional 3.6 nH, dependent on estimated
pad capacitance. Both Murata catalog mappings are established. Their Coilcraft source identities
remain in native authoring metadata as documented procurement overrides.
Manufacturer terminal-tolerance checks confirm centered overlap with native
lands; they do not clear supplier placement/process holds.

The nominal filled-mask field impedance is approximately 46.2 Ω. Etch ±20 µm,
dielectric thickness ±10%, epsilon 3.8–4.6 and mask 0–25 µm are sensitivity ranges,
not supplier tolerances. The mask model bounds bare copper and planar coating;
it omits conformal coating and nearby coplanar metal.

The RF network includes separate distributed bias/ESD branches, node-specific
pad areas, blocking capacitor ESL/ESR, matching inductor loss/self-capacitance,
connector parasitics and passive parallel-capacitance/series-RL inductor models.
[Murata JELF243A_0100K-01](https://search.murata.co.jp/Ceramy/image/img/P02/JELF243A-0100.pdf)
specifies minimum SRFs of 2.9/10 GHz and maximum DCRs of 0.996/0.030 Ω.
The sweep includes those SRFs and zero winding capacitance, with inductance
±7% (wider than the initial ±2% tolerance). Both inductors sweep assumed L1
Q from 10 to no AC loss, retaining DCR. Datasheet Q minima of 25/30 are
measured at 200/250 MHz and do not establish Q at L1. This is a sensitivity
surrogate, not fitted vendor S-parameter data or a guaranteed RF bound.
The reference case uses minimum specified SRF and assumed choke/matching Q
of 30/60; it must not be interpreted as a manufacturer-typical prediction.
The [Nexperia capacitance specification](https://assets.nexperia.com/documents/data-sheet/PESD5V0F1BL.pdf)
is measured at 1 MHz; using it at GNSS frequencies is an approximation. Parasitic
ranges and the unresolved L1-Q assumption are recorded in the report.

**196,608 corner cases** and **771 additional frequency points** pass unchanged
allocations: return loss ≥10 dB, insertion loss ≤1 dB and choke impedance ≥500 Ω.
Reference-case return/insertion loss is approximately **19.02/0.15 dB**; sampled
worst values are **10.15/0.94 dB**, with minimum choke impedance **519.94 Ω**.
The narrow margins remain conditional on the model assumptions. A separately
assembled ngspice circuit agrees with the ABCD calculation. Removing the matching
inductor, increasing ESD capacitance, or restoring long stubs exercises failure
controls. A failed RF allocation now fails the lab stage. The model is not a
three-dimensional connector solution or a controlled-impedance fabrication claim.

## Adjacent signal layers

Native In2/In3 segments are screened using exact round-ended proximity intervals
within three dielectric heights of edge separation. Angled segments, crossings,
and endpoints are included. Intervals are unioned per In2 segment and opposing
net, preventing duplicate length at bends. The reported length follows In2;
it is not the sum of both traces. IMU3_INT/SPI_MISO measures approximately
**9.47 mm**, compared with 4.8 mm in the retained parallel-only diagnostic.
The 5 mm parallel-only regression limit remains separate from electrical acceptance.

Distance contours split the intervals into 25 µm bins, rounded toward closer
coupling. Tests check both length and distance-bin invariance when straight
tracks are subdivided. The stress cross-sections add 20 µm width, reduce the
central dielectric by 10%, and use epsilon 4.6. Angled regions use a parallel
surrogate; separated regions are collapsed into a coherent equivalent line for
each net pair. This is a conservative engineering scenario, not a proof that it
bounds every 3-D crossing or whole-net topology.

Each pair is exercised in **both aggressor directions**, at 0.5/2 ns edge times, 20/100 Ω aggressor drive,
20 Ω/4.7 kΩ quiet termination and 2/10 pF end loads, at a 3.465 V step. A passive
six-section coupled LC ladder predicts near/far-end excursions. Doubling the
section count and halving the timestep checks convergence; an independently
generated ngspice circuit agrees within 5 mV. A disconnected-coupling control
must produce zero noise, and an excessive parallel-length fault must increase it.
There are 32 scenarios per pair.

The model has a **0.20 V maximum near/far-end excursion allocation**, applied to
every evaluated pair. A missing, nonfinite or excessive result fails acceptance;
the signal-integrity stage writes its evidence before failing the build.
This is a project allocation for one coupling mechanism, not a guaranteed
receiver noise margin. It is below the 0.227 V assumed host-bus static margin
in the [GNSS rail/threshold scenario](gnss-hardware.md), leaving only 27 mV in
that scenario for other effects. The actual receiver thresholds, output levels,
ground movement and combined noise budget remain unqualified.

The revised native routing **passes this allocation** for all 217 evaluated net
pairs. Worst excursion is 0.188 V on FPGA_RESET_N/PI_SPI_MISO, under the
same extraction, threshold and stress scenarios. Long parallel runs were
separated; three short runs use outer copper over ground planes, and one
LINK_DQ2 run changes inner layer. One redundant through-via was removed.
No components, power pours or stackup settings changed.
Use the saved `coupling.acceptance` and each pair's worst aggressor/scenario.
This pass applies to adjacent In2/In3 proximity only. The model omits vias,
same-layer coupling, whole-net reflections, simultaneous aggressors and
nonlinear receiver behavior. Physical interface qualification remains open.
