# Burrowlark DAQUSB-01 firmware

Prototype STM32F042K6 firmware implements four-module RM3100 magnetic and SHT45
temperature/humidity acquisition, USB CDC framing and reconnect handshakes.
The authoritative interface is the existing
[Burrowlark circuit and firmware contract](../../docs/usb-sensor-head.md), with
messages and framing in the [sensor data contract](../../docs/sensor-contract.md).
The bounded encoder uses no heap. The ARM build reserves two 1 KiB boot-journal
pages and at least 2 KiB of stack; the shared software profile checks the link.

Actual enumeration, sensor behavior, USB suspend current and physical validation are pending.
This firmware is separate from the Pi software that drives the accelerometer HAT.

The SHT45 profile uses address 0x44, heater-off high precision (0xFD), a 9 ms
conversion wait and one six-byte CRC-checked raw frame per second. Publish
sensor 17 under the USB-head identity using MCU timing. The Python injected-bus
reference is `sw/pi/groundlark/burrowlark.py`; the browser simulation exercises
it. Native C tests independently decode the target encoder's output and inject
independent conversion clocks, missing/late/stuck DRDY, distinct SPI return lanes,
configuration readback/status disagreement, signed saturation endpoints, maximum
identity/large encoder fields, I2C failures, CRC faults, DTR reconnects, suspend
and quartet backpressure. The native acquisition/encoder scenarios run with
address and undefined-behavior sanitizers. The lab retains the ARM image hashes and memory
allocation in `results/sw/build/burrowlark-arm/firmware.json` for each run.

Run `./lab.ps1 test -Profile software` (or `./lab.sh test --profile software`).
Firmware sources are in `firmware/`; binaries are retained in the bounded lab.
The default USB VID/PID is a private testing placeholder, not an allocated
product identity. Do not distribute it as a production USB device.

B1 uses cycle count 200 and one shared XYZ POLL (`0x70`) every 100 ms.
PA1/2/3 drive SCK/SI/SSN; PA4–7 read four separate SO lanes. PB0/1/3/4
capture separate DRDY interrupts. A 1 MHz TIM2 clock records command completion,
DRDY observations and read completion; it does not establish physical sample-time
accuracy. IDs 7/18/19/20 correspond to U2/U7/U8/U9. All four configuration
readbacks must agree before the magnetic array is enabled. This firmware requires
the B1 SPI PCB and is not compatible with the former A2 I2C wiring.

The array has a 50 ms completion deadline. A stuck-ready input, absent edge,
inconsistent ready status or SPI failure latches the array until sensor power
cycles. Subsequent slots are missing with no invented trigger time. The eight-frame
USB queue reserves four slots before publishing a quartet; backpressure drops the
whole quartet and reports unknown loss. Climate reads run between integrations;
three consecutive climate failures latch that sensor. Physical conversion loss
remains unknown. Raw signed 24-bit values and separate completion observations are
retained; averaging is an explicit calibrated host operation, described in the
[USB-head guide](../../docs/usb-sensor-head.md). USB configuration
controls sensor power; suspend/reset turns it off. An independent watchdog
resets a stalled loop. Preserve the boot-journal pages when updating firmware.
