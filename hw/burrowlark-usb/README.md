# Burrowlark USB — DAQUSB-01

Burrowlark is the separate 96 × 70 mm USB-C magnetometer and enclosure-climate
sensor head. It uses four identically oriented PNI 14190 RM3100 XYZ modules on a 30 mm square grid; U3/C5 and their pressure-sensor
branches are removed. The DLVR pressure sensor is on DAQHAT-01. Prototype
[USB-head firmware](../../sw/field-head/README.md) has native and ARM checks;
physical qualification remains pending.

![Burrowlark DAQUSB-01 Rev B1 with four aligned RM3100 modules and SHT45](boards/groundlark-field-head/3d.png)

Native PCB render with the Groundlark favicon, Burrowlark name and
`DAQUSB-01 / REV B1` front silkscreen. Shared SPI commands start all four conversions together; separate SO and DRDY lines preserve each raw result and completion observation. Internal sensor clocks remain independent.
Module, fuse and SHT45 bodies are simplified envelopes; see
[render provenance](boards/groundlark-field-head/render-provenance.json).

- [Electrical source](elec/field_head.ato)
- [Placement inputs](layout/placement.json)
- [Routed KiCad project](boards/groundlark-field-head/groundlark-field-head.kicad_pro)
- [Assembly and interface guide](../../docs/usb-sensor-head.md)
- [Firmware directory](../../sw/field-head/)

Build target: `field_head` in [hw/ato.yaml](../ato.yaml). Existing CAD filenames
and the DAQUSB-01 model identifier are preserved.
