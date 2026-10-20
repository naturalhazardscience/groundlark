# DAQHAT-01 external pressure filter

This simulation-defined accessory preserves the 1–20 Hz landslide research band
with the SDP32 read at 200 samples/s. Its dimensions are authored in
[network.json](network.json); it is separate from the HAT enclosure and PCB package.

| Element | Nominal dimensions |
| --- | --- |
| First inlet bank | Four parallel capillaries, each 10 mm long, 1.2 mm ID |
| First rigid chamber | 320 mL |
| Second inlet bank | Four parallel capillaries, each 10 mm long, 1.2 mm ID |
| Second rigid chamber | 320 mL, connected to SDP32 positive port |
| Reference chamber | 4 L, connected to SDP32 negative port |
| Independent reference vent | Ambient to reference, 10 mm long, 0.3 mm ID |

Connect ambient, first bank, first chamber, second bank and second chamber in
sequence. The separate reference vent permits slow equalization without depending
on flow through the sensor. Include connection dead volume in chamber volume;
additional tubing impedance is not included in this nominal network.

Use a sealed manifold adapter for the sensor's ports. Do not push tubing directly
onto the SDP32 manifold ports. Adapter, weather protection, dust filtering,
drainage and rigid chamber construction are not specified by this model. A
different filter or tube arrangement needs its own acoustic impedance model.
See the [Sensirion engineering guide](https://sensirion.com/media/documents/C3059EE6/667E9FD4/DP_AN_Engineering_Guide_V1.0.pdf).

Run `python hw/tools/pressure_pneumatics.py` in the lab environment.
The report covers 4,096 tolerance corners and 101 interior resistance points.
Independent tests retain the old failing geometry, blocked tubes, shorted vent,
undersized chambers and excessive sensor flow as failure controls.

Within the stated scenarios, gain is −5.21 to +2.07 dB over 1–20 Hz and the largest
uniform-sampling alias is −53.22 dB. Tube ID tolerance is ±3%, chamber volume
tolerance is ±10%, and tube lengths remain nominal. The sensor resistance sweep
is 10^7–10^12 Pa·s/m³; the manufacturer does not guarantee this range. These
results do not establish noise floor, leak tolerance, wind rejection, higher
acoustic modes or a minimum detectable landslide signal. See the complete
[model assumptions](../../../docs/simulation-validation.md#pressure-path).
