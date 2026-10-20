# JLCPCB assembled DAQHAT-01 HAT

The package targets **one fabricated PCB and one assembled HAT**, the same
physical board. The current HAT is 140 × 56 mm with 189 fitted placements.
The current exact-part registry covers all 189 placements with 71 unique JLCPCB
catalog identities. Dated live inventory and MOQ observations are recorded in
the registry. Procurement identities include the revised FPGA power input,
Pi supervisor, GNSS and SDP32 pressure sensor; older packages are incompatible.

**Assembly hold:** 137 placements have frozen numbered supplier-pad fits;
52 retain explicitly unverified supplier origins/rotations. The complete review
export includes these exceptions and cannot be submitted as a released assembly.
The placement release gate rejects unresolved entries. Obtain supplier geometry
and verify the actual order preview before manufacture.
The Pi, Trenz module, geophone, riser, supply and mounting hardware are separate
purchases. The USB sensor heads are not included.

## Files to upload

| File | Purpose |
| --- | --- |
| `DAQHAT-01-Gerbers-REVIEW.zip` | Current full-export fabrication data. |
| `BOM-review.csv` and `CPL-review.csv` together | Matching current full-export part selections and placements. |

Generate a complete package with the commands below before ordering. The older
2026-09-26 local packages predate the current copper and part selections; do not
combine their Gerbers with the revised BOM.

Use the BOM and CPL from the same fresh full export, or the same corrected
overlay. Do not mix versions or reuse previous manual rotation overrides. Gerbers contain one closed outline;
BOM quantities are per HAT. Set the supplier's PCB and assembly quantities
separately: the CSV cannot control the website's quantity selector.

Packages remain local and Git-ignored. They include checksums and validation
records; source CAD, part, side or process changes require a fresh export.
The package retains manufacturing holds and is not a fabrication approval.

## Fabrication and assembly requirements

- Six-layer FR-4, nominal 1.6 mm, TG135, ENIG, 1 oz outer / 0.5 oz inner copper.
  Use the stock JLC06161H-3313 stack, with no HDI or custom lamination.
  Its 1.5384 mm copper/dielectric sum is ordered as nominal 1.6 mm, ±10%.
- Through-vias only, 0.30/0.40 mm drills, epoxy-filled and copper-capped (POFV),
  including vias in solder pads. Tenting alone is insufficient.
  Do not fill component plated holes or non-plated mounting holes.
- Double-sided assembly. The export manifest records current SMT, THT and mixed
  process counts. J80/J81/J82 have SMT contacts and plated mounts.
  J1 is the bottom Pi socket.
- Confirm the supplier's one-piece assembly acceptance, handling frame,
  fiducials, part allocation and process requirements. Recorded Standard PCBA
  rules require a two-piece minimum and a 70 mm minimum dimension; the 140 × 56 mm
  HAT therefore needs a supplier-agreed quantity exception and handling frame.
  Do not change the requested quantity without the owner's agreement.
- Verify the supplier placement preview and final proposed production data.
  CAD, modeled tests and catalog pad fits do not establish physical fit or DFM approval.

## BOM mapping and selected parts

The [exact-part registry](../hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-parts.json) binds each
reference to its source value/footprint and approved manufacturer, MPN and C-code.
Catalog listing does not reserve stock or guarantee assembly eligibility.
Recheck allocation at ordering; do not accept automatic substitutes.

All 71 unique selections have dated **2026-10-19** JLCPCB available-order
observations and component minimum quantity 1, sufficient for one HAT.
Pre-order-only parts are rejected. Shared catalog identities are counted across
all source groups when checking inventory. Offline checks validate the recorded
snapshot; recheck allocation and assembly attrition at ordering.

D90 uses TI **TPD2E2U06QDCKRQ1 / C915089** in the authored circuit, BOM and
review schematic. It preserves the SC-70 pinout and existing bottom-side copper.
U23 uses **SDP32-125PA-TR-250PCS / C6473035** with its redesigned 17-pin split-pad
footprint, 3.3 V supply, I2C address 0x21 and matching driver. The sensor must be
installed in the final reflow only, with no board wash; protect both ports.
Maximum reflow temperature is 260 C, with at most 150 seconds above 200 C.
Pneumatic filtering and infrasound noise/response still require measurement.

U11/U12/U13 use **LSM6DSOXTR / C481766** as an explicit procurement override.
The LGA-14 pinout, mode-1 SPI, identity and acquisition register/FIFO subset are
compatible with the existing LSM6DSO driver. Unused auxiliary interfaces and
machine-learning features remain disabled. Physical acquisition is unqualified.
U40 retains GND/OUT/IN pins 1/2/3 and output tab. Its ceramic output capacitor
must retain at least 4.7 µF effective capacitance; C42 is 22 µF X5R, 25 V.
Allow ±3% regulator accuracy plus load/line regulation within the existing
3.18–3.42 V sensor-rail envelope. ST specifies typical 60 µVrms **per volt of
output** (198 µVrms at 3.3 V), 10 Hz–100 kHz; this is not an input-referred
geophone noise prediction. Retain the ADC analog RC filter.
D90's automotive variant preserves the SC-70 pinout, 5.5 V standoff, 10 nA
maximum leakage at 2.5 V and 1.5 pF typical capacitance.
See [ST LDL1117](https://www.st.com/resource/en/datasheet/ldl1117.pdf) and
[TI TPD2E2U06-Q1](https://www.ti.com/lit/ds/symlink/tpd2e2u06-q1.pdf).

Stock is not reserved. Component MOQ 1 does not remove assembly attrition,
process charges or the separate PCB/assembly service minimum described above.
The Pi, Trenz module, external geophone and risers remain outside this PCB BOM.

| Upload field | CSV column |
| --- | --- |
| Comment / manufacturer part number | `Comment` (full orderable MPN) |
| Designator | `Designator` |
| Footprint / package | `Footprint` |
| JLCPCB / LCSC part number | `JLCPCB Part #` |

Do not use `Description` as the ordering code. Confirm all 71 nonblank catalog
identities and all 189 placements survive import.

| References | Assembly selection | Required specification |
| --- | --- | --- |
| J1 | Megastar ZX-PM2.54-2-20PY / C7499354 | Bottom-mounted 2×20 female socket, 8.5 mm body; use two external SSQ risers and measured supports. |
| C42, C80–C82 | Samsung CL31A226KAHNNNE / C12891 | 22 µF, ±10%, X5R, 25 V, 1206. |
| C84, C85 | Murata GRM21BR71C475KE51L / C408144 | 4.7 µF, ±10%, X7R, 16 V, 0805. |
| C90 | Murata GRM31C5C1H104JA01L / C97946 | 100 nF, ±5%, C0G, 50 V, 1206. |
| C91, C92 | KEMET C0603C102J5GAC7867 / C140950 | 1 nF, ±5%, C0G, 50 V, 0603. |
| F80 | Littelfuse 0466002.NRHF / C3105 | 2 A fuse, 1206, FPGA 12 V input. |
| F130 | Littelfuse 0466004.NRHF / C187596 | 4 A fuse, 1206, Pi supply input. |

Both fuses use 466-series 1206 bodies; 467-series parts do not fit. The FPGA
output allocation is 3 A with a 15 milliohm hot output-loop target; the Pi supply
has a separate 3 A total allocation. Check startup, hot voltage drop and fuse
behavior on hardware. See [power supplies](power-supplies.md).
Signal capacitors C90–C92 must retain C0G dielectric, tolerance and voltage rating.

**J1 stack:** the model uses the selected 8.5 mm socket plus two external
SSQ-120-02-G-D risers, giving 28.06 mm nominal Pi-top to HAT-underside clearance.
Four supports must match the measured seated height. The old tall Samtec socket
model and one-riser assembly are superseded. Contact engagement, retention and
GPIO signal integrity still require first-article checks; see [stack assembly](stack-assembly.md).

## Placement conventions

J90 uses Phoenix Contact **1803280 / C480530**, the horizontal 3.81 mm header.
Its exact numbered supplier pads are frozen in the placement registry. The
2026-09-28 live catalog showed 2,209 available to order, MOQ 1; stock is not reserved.
The matching 1803581 cable plug is separately sourced.

The exporter fits supplier numbered pads to native footprints using the frozen
[catalog geometry](../hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-placement.json). It accounts
for bottom-side projection and preserves absolute component positions.
Use its CPL rather than raw KiCad angles or manual per-reference offsets.

| References | Supplier CPL rotation |
| --- | --- |
| J1 (Bottom) | 0° |
| J4 | 270° |
| JP1, JP80, JP81, JP130 | 0° |
| J80, J81 | 180° |
| J82 | 270° |
| J90 | 0° |
| U1, U22, U41, U42 | 270° |
| U100–U103 (Bottom) | 270° |
| Q1, U40, U51, U52 | 180° |
| D90 (Bottom, C915089) | 90° |
| C91, C92 (Top) | 0° |

Check J1's underside model and pin-1 direction in the supplier preview. Its
front-layer land pattern requires a bottom-mounted socket. Confirm mixed
SMT/THT assembly, reflow/cleaning limits and sensor handling with the supplier.
Each placement must have a part-bound catalog mapping
or explicit exception. Changed MPNs or footprints invalidate those mappings.
The full exporter and overlay use the same solver; repeated export does not
apply an extra rotation. This checks registration, not solder-joint reliability.

## Reproduce exports without changing CAD

Use KiCad 9.0.9 and a Python that imports `pcbnew` (WSL or the portable lab).
The exporter rejects source CAD/BOM hashes that differ from recorded validation,
checks all native DRC severities, validates the layer/drill inventory, and verifies
that BOM and CPL references agree. It refuses to overwrite a populated directory.

```bash
python3 hw/tools/jlcpcb_package.py --quantity 1 --output .local/jlcpcb/new-review
python3 -m unittest discover -s hw/tests -p 'test_jlcpcb*.py' -v
```

For optional independent plot inspection and PDF production, keep dependencies
inside the repo rather than installing into the atopile environment. The review
renderer uses rsvg-convert for luminance masks so silkscreen cutouts preserve
underlying copper, and draws the silkscreen above copper:

```bash

# Also requires rsvg-convert (librsvg2-bin on Debian/Ubuntu).
python3 -m venv --system-site-packages .local/fab-venv
.local/fab-venv/bin/pip install gerbonara==1.5.0 reportlab==4.4.10
.local/fab-venv/bin/python hw/tools/jlcpcb_inspect.py .local/jlcpcb/new-review
.local/fab-venv/bin/python hw/tools/jlcpcb_drawings.py .local/jlcpcb/new-review
```

The independent parser compares every exported hole location, diameter and
span to CAD (1 micrometre coordinate quantization), and parses all 13 plot layers.
The package report gives actual drill counts; no blind-drill files are accepted.
It emits benign parser warnings about KiCad's G90 header position and unused
RoundRect macro parameters; these are retained rather than suppressed. Render
the PDF with `pdftoppm` and inspect each page. Gerber parsing does not establish
DFM approval or validate solder-paste apertures against supplier process limits.

After adding the package README and reviewing the PDF, run
`python3 hw/tools/jlcpcb_seal.py .local/jlcpcb/new-review` to write checksums
and the complete review ZIP. This retains all manufacturing holds; it does not
promote the package to an approved release.
The assembly PDF reads J1 and J90 manufacturer, MPN and catalog identity from
that package's procurement CSV, keeping its instructions aligned with the BOM.

## Sources reviewed 2026-09-25

- [JLCPCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities):
  Standard service, two-piece minimum, panel dimensions, rails and fiducials.
- [PCB capabilities](https://jlcpcb.com/capabilities/Capab) and
  [six-layer POFV](https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv).
- [KiCad 9 export guide](https://jlcpcb.com/help/article/how-to-generate-gerber-and-drill-files-in-kicad-9).
- [BOM format](https://jlcpcb.com/help/article/bill-of-materials-for-pcb-assembly)
  and [CPL format](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly).
- [Parts sourcing](https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction).
- [LSM6DSOXTR catalog](https://jlcpcb.com/partdetail/LSM6DSOXTR/C481766)
  and [TCA9534PWR catalog](https://jlcpcb.com/partdetail/TexasInstruments-TCA9534PWR/C783615).
