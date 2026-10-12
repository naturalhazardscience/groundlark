# Reproducible hardware builds

For validation in an isolated, portable environment, use the
[portable lab](portable-lab.md). It does not depend on the migrated local venvs.

The Pi-outline DAQHAT-01 build and rendering commands are in
[Trenz carrier documentation](trenz-hat.md#rebuild).

Used environment: WSL Ubuntu 24.04, atopile 0.15.9 with Python 3.14.7,
KiCad/pcbnew 9.0.9, ngspice 42 and Freerouting 1.9.0. These lower-level commands
require KiCad's system Python bindings, sexpdata, and ngspice in Linux/WSL.
Recreate an optional local atopile environment with an installed `uv`:

```sh
uv venv --python 3.14.7 .local/atopile
uv pip sync --python .local/atopile/bin/python --require-hashes environment/requirements.lock
```

Run the following from the repository root. They write authoring outputs; use
the portable lab for disposable validation instead. Freerouting's jar is a local
dependency at `hw/tools/freerouting-1.9.0.jar`, excluded from Git.

```sh
mkdir -p hw/logs
CI=1 .local/atopile/bin/python -m atopile build -v hw > hw/logs/atopile-build.log 2>&1
.local/atopile/bin/python hw/tools/solve_constraints.py > hw/logs/constraint-solve.log 2>&1
.local/atopile/bin/python hw/tools/solve_constraints.py --negative > hw/logs/negative-voltage.log 2>&1
python3 hw/tools/simulate.py
python3 hw/tools/assemble_pcb.py
```

`solve_constraints.py` explicitly invokes atopile's full numeric solver for
voltage/resistance/capacitance parameters. This is necessary because the stock
0.15.9 picker skips numeric solving for manually selected atomic components.
The negative case must reject 5 V applied to the 3.6 V IMU. No installed package
is patched and no electrical check is disabled. Component ratings use `assert
... within`; power sources specify their delivered range.

`assemble_pcb.py` resets routing, applies mechanical placement, adds the outline
and plane rules, and exports Specctra. It reads the compiled native KiCad board;
it does not create connections from a Python netlist. Save manual layout changes
before rerunning it. Electrical source is in each product's `elec/` directory,
with common definitions in `hw/shared/elec/`. Each product's
`layout/placement.json` has no pin net assignments. Review BOM presentation
metadata when changing a selected MPN.

The commands below rebuild Burrowlark. DAQHAT-01 and Skylark have dedicated
authoring and validation commands in their product guides.
The checked route sessions are supplied with the boards. Reconstruct the
delivered layout after `assemble_pcb.py` with:

```sh
python3 hw/tools/import_routes.py
python3 hw/tools/trim_dangling.py
python3 hw/tools/widen_power.py
python3 hw/tools/review_schematic.py
python3 hw/tools/models.py
python3 hw/tools/check_circuit.py
python3 hw/tools/check_design.py
```

The power-width pass tries 0.4/0.3/0.25/0.2 mm and uses native DRC to retain only
legal widening. Remaining 0.15 mm sections and per-net lengths are recorded in
`power-widths.json`; this is not an ampacity or extracted voltage-drop analysis.

For a changed placement/circuit, reroute each board and repeat the checks:

```sh
xvfb-run -a java -jar hw/tools/freerouting-1.9.0.jar \
  -de hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.dsn \
  -do hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.ses -mp 25 -mt 1 -da
python3 hw/tools/import_routes.py
python3 hw/tools/trim_dangling.py
python3 hw/tools/widen_power.py
python3 hw/tools/review_schematic.py
python3 hw/tools/models.py
python3 hw/tools/check_design.py
```

The restricted SES importer verifies placements and rejects unsupported route
objects. KiCad performs independent DRC afterwards. Review schematics use local
symbols with physical pin numbers, explicit no-connects and documented supply
flags. They are derived artifacts, not a second electrical source.

Burrowlark B1 stores its finished copper in a complete native SES snapshot,
including local ground returns. Refresh it after authorized routing edits with
`python3 hw/tools/export_session.py groundlark-field-head`. Validate reproducibility
with `python3 hw/tools/replay_burrowlark.py`, which uses a temporary tree and never
reroutes or rewrites authoring CAD. The full and quick lab profiles run this check.

Autorouter completion is never assumed from a successful process exit; the
independent unconnected-net check is required. Use each product's documented
render command to refresh its actual native PCB view.

The KiCad project opens directly in PCB Editor; use Alt+3 for its interactive 3D
viewer. Stock models require KiCad's 3D packages. Custom envelopes are portable
under `hw/shared/models/`. Prototype render geometry is not mechanical signoff.

Do not use the empty BOM emitted by atopile's automatic picker: this design uses
manual manufacturer parts. The explicit per-board `bom.csv` files are the review
BOMs. No purchase, assembly order or board fabrication was submitted.

Render the current RM3100/SHT45 Burrowlark PCB with
`python3 hw/tools/render_burrowlark.py`. It verifies that U3/C5 are absent and
records PCB, model and image hashes in `render-provenance.json`. Refresh its
schematic, assembly and layout previews with
`python3 hw/tools/export_previews.py groundlark-field-head`. These commands
read the native CAD without rerouting or rewriting it; KiCad models, Xvfb for
headless rendering, and `rsvg-convert` for preview PNGs must be installed.

For a Burrowlark-only CAD check, run
`python3 hw/tools/check_circuit.py --board groundlark-field-head` and
`python3 hw/tools/check_design.py --board groundlark-field-head`. The latter
refreshes its ERC, DRC, netlist and validation reports without changing the PCB.
The full portable lab remains the required cross-product regression check.

Burrowlark identity artwork is authored in the `silkscreen` section of
`hw/burrowlark-usb/layout/placement.json` and applied during board assembly.
To refresh only these board graphics on existing routed CAD, run
`python hw/tools/burrowlark_silkscreen.py` in the KiCad Python environment, then
run the native design check and regenerate the render/previews. The command
verifies that copper is unchanged; it uses the shared 7 mm favicon artwork.
