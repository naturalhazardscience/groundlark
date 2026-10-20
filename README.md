<img src="sw/ui/assets/groundlark-wordmark.svg" alt="Groundlark — lark and seismic waveform" width="440">

# Groundlark — open hardware for seismic and environmental monitoring

Groundlark is a family of hardware boards and companion software for seismic
and environmental monitoring. Each board has its own hardware directory, with
shared component libraries, interfaces and validation tools.

The family has **three products**: the Groundlark FPGA HAT, Skylark and
Burrowlark USB sensor heads. All share the sensor contracts, simulation tools and local workbench.

## Groundlark

![Groundlark revised power and GNSS circuit: routed HAT with antenna current limiting, side SMA, Pi/Trenz stack and geophone](docs/images/groundlark-gnss.png)

**Seismic monitoring on a Raspberry Pi.** The active
[Groundlark FPGA HAT](hw/groundlark-fpga-hat/README.md), model **DAQHAT-01**, is a
140 × 56 mm, six-layer FR-4 board with three XYZ LSM6DSO IMUs and an ADS122C04
input for an external Racotech geophone, plus a fitted SDP32-125PA infrasound sensor and u-blox MAX-M10S GNSS with a side-facing SMA antenna connector. The stack is **Pi → HAT → Trenz
Artix-7 200T FPGA**. Pi acquisition works independently of a configured FPGA.

The [internal FPGA link](docs/fpga-host-link.md) provides six QSPI wires, UART,
reset and switched Pi-driven JTAG. An SPI echo bitstream is implemented;
accelerated sensor processing and native quad transfers remain future work.
The FPGA uses a separate Nexys Video-compatible 12 V, center-positive adapter through J83 and an onboard 3.326 V converter. See the [power limits](docs/trenz-hat.md).

**Status:** active prototype. Physical power, fit, timing, noise and thermal
qualification remain pending. See the [stack assembly guide](docs/stack-assembly.md),
[JLCPCB instructions](docs/jlcpcb-assembly.md) and [bench procedure](docs/bench-procedure.md).
The JLCPCB package targets one assembled HAT; sourcing, placement and J1 fit
checks remain open. Fabrication packages stay local in ignored `hw/releases/`.

*R3 [prototype enclosure](hw/mechanical/daqhat-01-case/README.md), current
140 mm HAT CAD with GNSS/SMA, infrasound, TI Pi supervision and independent FPGA power, vendor Trenz components and a detailed
[Pi 4B model](hw/shared/models/raspberrypi4/README.md) by integrated-circuit / FreeCAD
community (CC BY 3.0). Clear PETG appearance, risers, geophone and wiring are approximate.
Physical fit remains unqualified. [Render provenance](docs/images/groundlark-gnss.json).*

![Groundlark enclosure with the side SMA accessible](docs/images/groundlark-gnss-closed.png)

[Closed enclosure render provenance](docs/images/groundlark-gnss-closed.json).
Measured gain/offset workflows and PCB probe access are in the
[calibration guide](docs/calibration.md). Seismic recordings support local
[miniSEED export](docs/miniseed.md).

## Skylark

![Skylark USB: populated vertical PCB and gas cells in the removable tray, with the white bell enclosure beside it](docs/images/skylark-assembly.png)

**Outdoor air-quality monitoring over USB.** [Skylark USB](hw/skylark-usb/README.md)
combines a vertical **90 × 100 mm PCB** with a removable sensor tray and a
**130 × 94 × 185 mm bell enclosure**.

- **Particles:** Plantower PMS5003, with separate downward-facing inlet and exhaust paths.
- **Gases:** socketed SGX-7SO2-AQ-20 sulfur dioxide and SGX-7H2S-AQ-25 hydrogen sulfide cells.
- **Weather:** SHT40 temperature/humidity and BMP390 barometric pressure.
- **Connection:** USB-C power and data through an STM32F072 microcontroller.
- **Housing:** printable bell, rear M4 keyhole mounts and a removable tray with
  separate PMS cradle and splash cover. Bottom ventilation is sheltered by a 25 mm skirt.

[Prototype firmware](sw/skylark/README.md) implements sensor acquisition and
USB streaming. The shared workbench includes Skylark simulation, recording/replay,
board-specific tests and an interactive 3D PCB. Gas data retains separate raw
working and auxiliary electrode counts; concentrations require calibration.

**Status:** Rev A PCB, Rev G enclosure and prototype firmware are implemented.
Physical fit, USB power behavior, analog performance, gas response and weather
resistance still require qualification. The ventilated enclosure has no assigned
IP rating. Follow the [PCB guide](hw/skylark-usb/README.md) and
[enclosure assembly instructions](hw/skylark-usb/mechanical/bell/README.md).

*Render: native PCB artwork and authored component models in the CAD-derived
tray, with the bell set beside it. Component bodies are dimension envelopes;
fasteners and cable dressing are illustrative. [Render provenance](docs/images/skylark-assembly.json).*

## Burrowlark

![Burrowlark DAQUSB-01 Rev B1: USB-C PCB with four aligned PNI RM3100 XYZ magnetometers and SHT45 temperature/humidity](hw/burrowlark-usb/boards/groundlark-field-head/3d.png)

**Remote magnetic and enclosure-climate sensing over USB.**
[Burrowlark USB](hw/burrowlark-usb/README.md), model **DAQUSB-01**, carries four
RM3100 magnetometers on a 30 mm square grid and an SHT45 temperature/humidity
sensor. One STM32F042K6 coordinates their measurements and sends each sensor's
raw data and timing evidence to the Pi over USB-C.
The SDP32-125PA infrasound sensor is fitted on Groundlark DAQHAT-01.

**Status:** routed prototype hardware, MCU firmware and workbench simulation are
implemented. Physical USB, synchronization, magnetic cross-talk and noise
qualification remain pending. See the
[USB sensor-head guide](docs/usb-sensor-head.md) for interfaces and assembly details.

*Render: native 96 × 70 mm PCB with favicon, Burrowlark name and DAQUSB-01 / REV B1
silkscreen, four RM3100 modules and SHT45 U6/C10; the former infrasound
footprint and bypass capacitor are removed. Module, fuse and SHT45 bodies are simplified
dimensional envelopes. [Render provenance](hw/burrowlark-usb/boards/groundlark-field-head/render-provenance.json).*

## Sensor workbench

The dark-mode Python UI lets you switch between Groundlark, Skylark and
Burrowlark, with interactive 3D views, raw-data charts, stimulus/fault controls,
board-specific tests and recording/replay.
No hardware or Docker is required. Follow the
[beginner walkthrough](docs/sensor-workbench.md) to create your first signal.

```powershell
# Windows: set up once, then launch
./setup-ui.ps1 -Check
./ui.ps1
```

On Linux/macOS, use `sh ./setup-ui.sh --check`, then `sh ./ui.sh`.
Open **http://127.0.0.1:8080**. Tools and dependencies stay in ignored `.local/`.

![Groundlark sensor workbench showing the external geophone and a simulated 2 Hz signal](docs/images/sensor-workbench.png)

This is an actual browser screenshot with simulated data. Select the geophone
can or its HAT input to highlight both and inspect the same ADC stream.
Use the **Board** selector for the FPGA HAT, Burrowlark or Skylark.
**Test selected board** runs the selected board’s checks; the HAT test covers all
six sensors over eight simulated seconds. IMU, ADC and GNSS use production Pi
drivers on modeled buses; infrasound uses a raw-response model pending its Pi
driver. Signal checks and recordings/results are downloadable.
The Groundlark GNSS panel also models disconnected or shorted antennas, lock
loss and recovery, and PPS loss independently.
The UI simulates and replays; physical acquisition uses the [Pi software](docs/sensor-software.md).
Live seismic capture stores raw geophone and IMU counts locally as
[miniSEED 3](docs/miniseed.md), with SSREC companions for diagnostics and replay.

## Project files and tests

| Directory | Contents |
| --- | --- |
| [hw/](hw/README.md) | Four product directories, shared component resources, hardware checks and SPICE. |
| [sw/](sw/README.md) | Pi acquisition, contracts, simulator, FPGA and remote firmware interfaces. |
| [docs/](docs/README.md) | Setup, hardware specifications, assembly, interfaces and testing instructions. |
| [environment/](docs/portable-lab.md) | Pinned Docker test environment and bounded cleanup tooling. |

For the full test environment, run `./lab.ps1 build` once, then `./lab.ps1 test`.
Use `./lab.ps1 test -Profile software` for sensor contracts, acquisition,
recording/replay and recovery. Use `./lab.ps1 test -Profile simulation` for fresh
circuit builds, CAD checks and all models while excluding the procurement release
gate. See the [simulation scope](docs/simulation-validation.md) and [portable lab guide](docs/portable-lab.md)
for Linux commands, test scope, five-run retention and cleanup.

Hardware sources: [DAQHAT-01 circuit](hw/groundlark-fpga-hat/elec/hat_trenz.ato),
[KiCad PCB](hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb),
[Burrowlark DAQUSB-01](hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.kicad_pcb), and
[Skylark USB](hw/skylark-usb/boards/skylark-usb/skylark-usb.kicad_pcb).
See [build instructions](docs/build.md) and [source references](docs/sources.md).

## License

Project-authored code, hardware designs and documentation use the [MIT License](LICENSE).
Third-party assets and dependencies retain their own licenses and attribution.
