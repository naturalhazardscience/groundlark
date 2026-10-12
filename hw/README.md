# Hardware

Each product has its own directory. Existing model names and atopile targets
remain stable so board identity does not depend on its directory name.

| Product | Model / outline | Build target | Status |
| --- | --- | --- | --- |
| [Groundlark FPGA HAT](groundlark-fpga-hat/README.md) | DAQHAT-01, 140 × 56 mm | `trenz_hat` | Active prototype; physical qualification pending. |
| [Burrowlark USB](burrowlark-usb/README.md) | DAQUSB-01 B1, 96 × 70 mm | `field_head` | Four-sensor prototype hardware/firmware; physical qualification pending. |
| [Skylark USB](skylark-usb/README.md) | Rev A, 90 × 100 mm | `skylark` | Routed air-quality prototype, STM32 firmware and Rev G bell enclosure; physical qualification pending. |

## Product contents

- `elec/`: authored circuit and product-specific part definitions.
- `layout/placement.json`: placement metadata for that board.
- `layout/<target>/`: atopile connectivity layout and local library tables.
- `boards/<board>/`: routed native CAD, review schematics, BOMs, previews and validation evidence.
- `mechanical/` and `simulation/`: product-specific artifacts where applicable.

Skylark includes its circuit, routed PCB, review schematic, BOM and CAD renders.
Stack concept boards are visualization artifacts.

## Shared resources and tooling

[shared/](shared/README.md) holds common part definitions, KiCad libraries, models,
vendor/reference material and simulations used by multiple boards. Custom CAD
resource paths remain relative.

`tools/` and `tests/` retain the existing shared and cross-board checks.
`assembly/<product>/` holds procurement overrides; `releases/<product>/` is for
ignored local fabrication packages, which require explicit authorization to publish.
Disposable runs belong in `.lab/`; local dependencies belong in `.local/`.
Firmware and host software belong in `sw/`.

`ato.yaml` defines four implemented targets. Direct atopile commands target
`hw/` from the repository root and write authoring outputs.

Use the root portable lab for routine checks. See the [build guide](../docs/build.md),
[Trenz guide](../docs/trenz-hat.md) and [validation limits](../docs/validation.md)
before invoking the lower-level authoring tools.
