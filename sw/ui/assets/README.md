# Board visualization provenance

The workbench favicon uses a teal lark with a seismic waveform tail on dark
navy. `groundlark-icon.png` is the generated master; `groundlark-favicon.ico`
contains browser sizes from 16 to 256 pixels. See the
[generation prompt and export command](groundlark-icon-prompt.md).

`groundlark-wordmark.svg` combines the existing favicon's master PNG
(unchanged) with the name in Segoe UI Bold, matching the Windows system font
previously used in the workbench header. Text is stored as vector outlines so
the README and UI render identically without downloading or installing a font.
Both use this same self-contained image on a navy background. The PCB artwork
and browser favicon remain unchanged.
Regenerate with `python sw/ui/build_wordmark.py --font C:/Windows/Fonts/segoeuib.ttf`
using build-only `fonttools` (verified with 4.63.0). No font binary is distributed.

`daqhat-01.glb` is a display asset exported with KiCad 9.0.9 from the checked DAQHAT-01 PCB.
It includes the routed board's outline, holes, pads, mask, silkscreen and available
stock component models. It is not a manufacturing deliverable.
The current revision includes U141 antenna current limiting, local C151/C152
bypasses and the corrected power and I²C routing. Package bodies are display
models; procurement and physical qualification remain separate checks.

KiCad's exporter cannot convert the local VRML bodies. The Python scene adds
simplified envelopes for the selected 8.5 mm Megastar Pi socket and Trenz connectors. Selection rings use `hw/groundlark-fpga-hat/layout/placement.json` XY values.
The fitted SDP32 U23 is represented by a conservative SDP32 envelope on
the HAT; its custom VRML cannot be converted by KiCad. The remote head is a
native PCB GLB containing RM3100 and SHT45, with placement-based selection rings.

The external geophone is authored in Python in `../geophone_scene.py`, with a
25.4 mm diameter / 33 mm high Racotech body. Terminals and leads to J90 are
illustrative. Its selectable can and the ADC both map to sensor 9, and both
highlights follow the same selection. It adds no synthetic data stream or
mechanical motion to the acquisition models. Scene source is also hash-pinned.

Regenerate from the repository root on the Linux lab toolchain:

```sh
kicad-cli pcb export glb --force --no-dnp --include-pads --include-silkscreen \
  --include-soldermask --subst-models --output sw/ui/assets/daqhat-01.glb \
  hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb
```

The exporter reports missing local VRML models and may return nonzero despite creating
the GLB. Inspect the result and missing-model inventory before accepting it.
Do not ignore other export failures. The scene converts GLB metres/Y-up to
centimetres/Z-up, subtracts the CAD origin (50, 50 mm), then centres the current 140 x 56 mm
board. The placement coordinates themselves are unchanged.

`provenance.json` pins the PCB, placements and display asset. Update its SHA-256
values only after re-export and alignment review. For a path-only relocation,
retain the previous hashes and verify unchanged normalized CAD, placement data,
model bytes and display assets before refreshing their bindings. The current asset includes the horizontal J90 connector, relocated D90 protection
diode and four passive underside calibration pads TP90–TP93. The lead approaches the header parallel to the PCB. Startup fails on stale inputs.
Stock KiCad component geometry retains its upstream attribution/license; see
[KiCad's library licensing](https://www.kicad.org/libraries/license/).

## Skylark

`skylark.glb` combines the native 90 × 100 mm PCB, holes, silkscreen (including
the Groundlark favicon), pads and mask with the existing authored package
models. Both front and rear components are included. The SGX bodies use the
same 31.5 mm cell diameter and 4.88 mm socket standoff as the native CAD render.
The current asset includes the guarded sensor region, 1206 C0G capacitor banks
corrected clamp packages, HRO USB-C receptacle and 0805 gas output filter capacitors. Cell tops are 20.38 mm above the PCB front.
`skylark_scene.py` adds selectable sensor targets and an illustrative PMS5003
beside the board; this is an exploded inspection view, not enclosure placement.

Regenerate the bare PCB using KiCad 9.0.9:

```sh
kicad-cli pcb export glb --force --no-dnp --include-pads --include-silkscreen \
  --include-soldermask --subst-models --output .local/skylark-bare.glb \
  hw/skylark-usb/boards/skylark-usb/skylark-usb.kicad_pcb
python sw/ui/build_skylark_model.py .local/skylark-bare.glb
```

Run the converter in a separate local build environment with `trimesh==4.8.3`
and `numpy==2.5.3`; these are not runtime/UI dependencies. KiCad cannot import
these VRML bodies into GLB and reports each missing model. The converter reads
the bounded Box/IndexedFaceSet subset of the authored models, preserves their
colors, and places them using the current placement metadata. It rejects
unsupported geometry. It writes `skylark-provenance.json`, pinning every source
model, PCB, placement, converter, scene and output. Inspect front/back alignment
before accepting regenerated assets. Startup validates both board manifests.
These authored envelopes are display geometry, not supplier-certified models.

The 12 V revision re-exports the enlarged PCB and adds explicit PJ-102AH and
TPSM53603 display envelopes because those native VRML models are omitted from
GLB. Their dimensions come from manufacturer drawings; they are not certified
mating solids. The jack faces away from the geophone exit.

## Burrowlark

`burrowlark.glb` contains the native 96 x 70 mm B1 routed PCB with four aligned RM3100 modules and stock models plus
simplified PNI14190, PTC1812 and SHT45 envelopes. The SHT45 body is an authored
nominal 1.5 x 1.5 x 0.5 mm model based on the Sensirion SHT4x package drawing,
not a supplier-certified solid. It is included in both the native README render
and browser GLB. Export with KiCad 9.0.9:

```sh
kicad-cli pcb export glb --force --no-dnp --include-pads --include-silkscreen \
  --include-soldermask --subst-models --output .local/burrowlark-native.glb \
  hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.kicad_pcb
python sw/ui/build_burrowlark_model.py .local/burrowlark-native.glb
```

Use a separate build environment with `trimesh==4.8.3` and `numpy==2.5.3`.
The six local VRML parts (four PNI modules, fuse and SHT45) are the expected missing native GLB models and are
added by the converter. Inspect alignment before accepting the hashes in
`burrowlark-provenance.json`. Runtime/UI dependencies remain unchanged.

The GNSS revision includes the underside authored MAX-M10S package envelope and an authored
HenryTech SMA STEP (`hw/tools/gnss_model.py`) using its published dimensions.
Unlike local VRML bodies, this STEP is included by native GLB export. The antenna
points along PCB -X. PPS and lock overlays describe modeled evidence, not hardware measurements.

Interface identifier and service-label updates preserve normalized placement
geometry, PCB/model bytes and GLB assets. Their provenance bindings can be
refreshed after verifying those equalities; no mesh regeneration is needed.
