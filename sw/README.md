# Software

The sensor HAT is driven by Pi software; it does not need separate MCU firmware.
The [acquisition software](../docs/sensor-software.md) supports sensors on the
DAQHAT-01 FPGA stack and runs without a configured FPGA. Its SDP32 pressure
profile uses average-until-read at 100 Hz for the 1–20 Hz landslide research band;
see [response and qualification limits](../docs/sensor-response.md).
The sensor contracts and Pi acquisition application are executable:

- [interfaces/](interfaces/README.md): Protobuf schemas, semantic validation and bounded USB framing.
- [pi/](pi/README.md): Pi device configuration, sensor drivers/adapters, acquisition,
  calibration and timestamps.
- [field-head/](field-head/README.md): microcontroller firmware for Burrowlark
  (DAQUSB-01), the remote USB-C magnetometer board.
- [skylark/](skylark/README.md): buildable STM32 USB air-quality firmware, native driver fault tests and shared v1 capture.
- [fpga/](fpga/README.md): Trenz pin/connectivity qualification and minimal test
  bitstreams; accelerator implementation is deferred.
- [tests/](tests/README.md): portable replay, fault injection and host integration.
- [ui/](ui/README.md): Python/NiceGUI local sensor workbench, board explorer,
  stimulus controls and recording/replay.

Run `./lab.ps1 test -Profile software` after rebuilding the portable image.
This checks schemas, compatibility, acquisition/replay, modeled bus drivers,
USB streams and recovery from injected faults. See the
[software run guide](../docs/sensor-software.md). Burrowlark and Skylark prototype firmware have native C and ARM checks; physical qualification remains pending. Tests do not emulate
Pi/MCU instructions or enumerate a USB sensor head.

## Pi power policy

The optional TI supervisor has a disabled [configuration template](pi/deploy/power-policy.example.json)
and a tested [validator](pi/groundlark/power_config.py). Battery thresholds are
intentionally unset. [Prototype MSPM0 firmware](supervisor/README.md), validated
build-time policy generation and Pi kernel shutdown/acknowledgement configuration
are implemented. The default firmware keeps RUN off; loading the JSON template
does not change hardware power. Battery selection and physical qualification remain pending.
See the [power operating specification](../docs/power-supplies.md#pi-supervisor-and-battery-input).
