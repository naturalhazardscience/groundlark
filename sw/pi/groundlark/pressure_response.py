"""Ideal SDP32 averaging response for the 1-20 Hz landslide research band.

This models conversion averaging only, not pneumatic response, sensor noise,
the internal analog response or a qualified anti-alias filter. See
docs/sensor-response.md for the field studies and physical acceptance procedure.
"""
import cmath
import math
from .pressure import SETTINGS

BAND_HZ = (1, 20)
DIAGNOSTIC_BANDS_HZ = ((1, 10), (6, 15))


def boxcar(frequency_hz, conversion_hz=2000, read_hz=100):
    """Uniform conversion ticks ending at an ideal instantaneous read."""
    if not all(math.isfinite(v) for v in (frequency_hz, conversion_hz, read_hz)):
        raise ValueError('finite frequencies required')
    if frequency_hz < 0 or not 1800 <= conversion_hz <= 2200 or read_hz <= 0:
        raise ValueError('SDP32 oscillator/read frequency outside model')
    count = round(conversion_hz / read_hz)
    if not 1 <= count <= 55 or abs(count - conversion_hz / read_hz) > 1e-9 or 1/read_hz > .025:
        raise ValueError('model requires an integer arithmetic conversion window <=25 ms')
    transfer = sum(cmath.exp(-2j * math.pi * frequency_hz * i / conversion_hz)
                   for i in range(count)) / count
    gain = abs(transfer)
    return dict(gain=gain, gain_db=20*math.log10(max(gain, 1e-15)),
                phase_deg=math.degrees(cmath.phase(transfer)),
                aliased_hz=abs((frequency_hz+read_hz/2) % read_hz-read_hz/2))


def report(settings=None):
    settings = SETTINGS if settings is None else settings
    if (settings.get('pressure_measurement_command') != 0x3615 or
            settings.get('period_ns') != 10_000_000 or
            settings.get('pressure_part_number') != 'SDP32-125PA-TR-250PCS'):
        raise ValueError('response requires the fitted SDP32 average-until-read 100 Hz profile')
    frequencies = (.5, 1, 5, 10, 12.5, 15, 20, 50, 80, 90, 100)
    return dict(scope='ideal conversion averaging only; physical qualification pending',
                band_hz=BAND_HZ, diagnostic_bands_hz=DIAGNOSTIC_BANDS_HZ,
                read_hz=100, command='0x3615', pressure_count_pa=1/240,
                required_noise_floor_pa=None, qualified=False,
                oscillator_cases_hz={rate:[dict(input_hz=f, **boxcar(f, rate)) for f in frequencies]
                                     for rate in (1800, 2000, 2200)},
                limitations=['No sensor, port, tubing, wind or reference-volume transfer modeled.',
                             'Reset epoch and conversion phase are not established by read completion.',
                             'Boxcar averaging leaves substantial aliases; a later digital filter cannot undo them.',
                             'No detection threshold, range, precursor or alarm reliability claimed.'])
