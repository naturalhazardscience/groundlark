# Hardware simulation scope

The active DAQHAT-01 adds 15 ngspice cases in `geophone/`, run with
`python3 hw/tools/simulate_geophone.py`: Racotech mechanical response, coil
loading, passive input filtering, bias and PGA common-mode headroom at nominal
and tolerance corners. See [the circuit and limits](../../../docs/geophone-input.md).
These models omit ADC digital filtering, self-noise, parasitic coupling and
physical mounting.

`simulate_geophone_review.py` adds eight passive startup/pulse/recovery cases in
`geophone-review/`, with asymmetric components and leakage. A 50 mV input exceeds
the ADC range, but this model checks passive recovery only. `prefab_review.py`
adds 256 analytical corners at eleven frequencies, a planning noise budget and
read-only layout/fit measurements. Physical measurements follow the
[bench procedure](../../../docs/bench-procedure.md).

The FPGA carrier has fourteen additional bounded checks in `trenz/`, run with
`python3 hw/tools/simulate_trenz.py`. These cover DC input budgets, detection of
excessive supply-lead resistance and lumped UART RC loads. They do not simulate
the Trenz regulators or FPGA logic; see [DAQHAT-01 scope](../../../docs/trenz-hat.md).
The updated source envelope is 3.35 V ±0.5% at J83 with a 30 mΩ total hot loop
resistance limit. Four load-step cases add 50/200 nH, 20 mΩ capacitor ESR and
26.4 μF effective capacitance for 0.1↔3 A ramps lasting 100 μs. They do not
qualify sub-microsecond FPGA load edges, startup inrush or source control loops.

Run `python3 hw/tools/simulate.py` with ngspice. It writes all 18 circuit decks,
simulator logs and measured limits to `results.json`, failing on a missing or
out-of-range measurement.

| Cases | Model | Acceptance |
|---|---|---|
| 8 | Sensor rail 3.18/3.42 V; source resistance 0.05/0.2 ohm; 500 nH trace; 22 uF bulk at 40/100% effective capacitance; 1 uF aggregate local bypass; 20–200 mA steps | 3.0–3.6 V |
| 4 | USB 4.75/5.25 V, 25/80 mA; 2 ohm cable plus 1 ohm PTC; ideal LDO with 0.4 V headroom; 0.5 ohm sensor switch, 1–55 mA sensor steps and 500 nF external local bypass (excluding module-internal capacitance) | LDO input ≥4.35 V; sensor rail ≥3.20 V |
| 3 | 4.7 kohm +1% I2C pull-up; 50/100/200 pF; 20 ohm open-drain switch | Rise <1 us, low <0.4 V; 100 kHz bus target |
| 1 | 2 Mbaud UART; 47 ohm series, assumed 25 ohm driver and 100 pF | Rise <50 ns; mid-bit high >2.31 V |
| 2 | USB CC 5.1 kohm ±1% pull-down with a 56 kohm source pull-up at 5 V | CC 0.40–0.43 V |

These are **behavioral/passive support-circuit models**, not full sensor
silicon models. The sensor supply assumes a regulated source; it does not simulate TLV1117 loop
stability. Parasitics
are assumed bounds, not extracted PCB values. UART RC analysis is not IBIS/SI signoff.

The LDO thermal budget assumes 200 mA, 5.25 V input, 3.18 V output, 60 °C ambient
and **100 °C/W assumed board thermal resistance**: 101.4 °C estimated junction.
This is not a measured temperature.

Bench work must cover capacitor DC-bias derating, regulator startup/stability,
clock edges at the chip, reset/brownout, maximum-activity rail droop, cable
hot-plug/ESD, magnetic noise with the Pi and accelerator active, GNSS RF layout
and pressure-sensor pneumatics. These checks do not establish fabrication release.
