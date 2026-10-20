"""Streaming stationary bench measurements; never manufacture a qualification PASS.

All units use advertised nominal sensor sensitivity, not a claimed calibration.
Record separate stationary runs with the FPGA off, idle and active for comparison.
"""
import hashlib
import math
from .recording import Reader, is_acquisition_metadata
from .session import Sessions
from .calibration import Calibrations, configuration_hash


class Moments:
    def __init__(self):
        self.n = 0
        self.mx = self.my = self.xx = self.yy = self.xy = 0.0
        self.low = self.high = None

    def add(self, x, y):
        self.n += 1
        dx, dy = x - self.mx, y - self.my
        self.mx += dx / self.n
        self.my += dy / self.n
        self.xx += dx * (x - self.mx)
        self.yy += dy * (y - self.my)
        self.xy += dx * (y - self.my)
        self.low = y if self.low is None else min(self.low, y)
        self.high = y if self.high is None else max(self.high, y)

    def report(self):
        slope = self.xy / self.xx if self.xx else None
        return dict(count=self.n, mean=self.my if self.n else None,
                    stddev=math.sqrt(max(0, self.yy / (self.n - 1))) if self.n > 1 else None,
                    slope_per_second=slope, peak_to_peak=self.high - self.low if self.n else None)


def analyze(path):
    stats = {}
    complete, pps_previous, pps_period = False, None, Moments()
    with open(path, 'rb') as stream:
        reader = Reader(stream)
        metadata = reader.metadata
        if not is_acquisition_metadata(metadata): raise ValueError('recording format')
        sessions = Sessions(Calibrations(metadata.get('calibrations', [])), checkpoint=metadata.get("session_checkpoint"))
        for arrival, item in reader:
            complete = isinstance(item, dict) and item.get('code') == 'acquisition_summary'
            if isinstance(item, dict):
                if item.get('code') == 'pps_edge':
                    edge = item.get('monotonic_ns')
                    if type(edge) is not int or edge < 0: raise ValueError('invalid PPS event')
                    if pps_previous is not None:
                        if edge <= pps_previous: raise ValueError('PPS time moved backwards')
                        pps_period.add(pps_period.n, (edge - pps_previous) / 1e9)
                    pps_previous = edge
                if item.get('code') == 'usb_disconnected' and item.get('device') is not None:
                    sessions.disconnect(item['device'])
                continue
            kind = sessions.accept(item)
            if kind != 'batch' or item.batch.sensor_id not in (1,2,3,4,5,8,9): continue
            sid = item.batch.sensor_id
            cfg = sessions.devices[item.device_id].settings[sid]
            digest = configuration_hash(cfg)
            row = stats.setdefault(sid, dict(configuration_sha256=digest, owner=(item.device_id, item.boot_id),
                total=0, valid=0, missing=0, saturated=0, fault=0, sequence_gaps=0,
                first=None, last=None, previous_sequence=None, periods=Moments(), fields={}))
            if row['configuration_sha256'] != digest or row['owner'] != (item.device_id, item.boot_id):
                raise ValueError('bench comparison requires one boot/configuration per sensor')
            for sample in item.batch.samples:
                t = sample.time.acquisition_ns
                if row['first'] is None:
                    row['first'] = t
                    row['sequence_gaps'] += sample.sequence
                if row['last'] is not None:
                    row['periods'].add(row['total'], (t - row['last']) / 1e9)
                    row['sequence_gaps'] += sample.sequence - row['previous_sequence'] - 1
                row['last'], row['previous_sequence'] = t, sample.sequence
                row['total'] += 1
                row[{1:'valid', 2:'missing', 3:'saturated', 4:'fault'}[sample.quality]] += 1
                if sample.quality != 1: continue
                seconds = (t - row['first']) / 1e9
                if sid == 8:
                    frame=sample.pressure.sdp3x_response
                    if frame:
                        values={'pressure_pa':int.from_bytes(frame[:2],'big',signed=True)/240,
                                'temperature_k':int.from_bytes(frame[3:5],'big',signed=True)/200+273.15}
                    else:
                        frame=sample.pressure.response
                        values={'legacy_pressure_counts':int.from_bytes(frame[:2],'big') & 0x3fff,
                                'legacy_temperature_counts':int.from_bytes(frame[2:],'big') >> 5}
                    if sample.pressure.HasField('read_interval_min_ns'):
                        values.update(read_interval_min_s=sample.pressure.read_interval_min_ns/1e9,
                                      read_interval_max_s=sample.pressure.read_interval_max_ns/1e9)
                elif sid == 9:
                    values = {'adc_counts': sample.geophone.counts,
                              'input_voltage_v': sample.geophone.counts * cfg.geophone_reference_v / cfg.geophone_gain / 8388608}
                else:
                    raw = sample.imu if sid <= 4 else sample.tilt
                    scale = ({2:.061,4:.122,8:.244,16:.488}[cfg.acceleration_range_g] * .00980665
                             if sid <= 4 else 9.80665 / {1:6000,2:3000,3:12000,4:12000}[cfg.tilt_mode])
                    vectors = {}
                    if raw.HasField('acceleration'):
                        vectors['acceleration_m_s2'] = [getattr(raw.acceleration, a) * scale for a in 'xyz']
                    if sid <= 4:
                        gyro = {125:4.375,250:8.75,500:17.5,1000:35,2000:70}[cfg.angular_rate_range_dps] * math.pi/180000
                        vectors['angular_rate_rad_s'] = [getattr(raw.angular_rate, a) * gyro for a in 'xyz']
                    elif raw.HasField('angle'):
                        vectors['angle_rad'] = [getattr(raw.angle, a) * math.pi/32768 for a in 'xyz']
                    values = {f'{name}.{axis}': value for name, vector in vectors.items() for axis, value in zip('xyz', vector)}
                    if 'acceleration_m_s2' in vectors:
                        values['gravity_m_s2'] = math.sqrt(sum(v*v for v in vectors['acceleration_m_s2']))
                    if raw.HasField('temperature'):
                        values['temperature_k'] = raw.temperature / (256 if sid <= 4 else 18.9) + (298.15 if sid <= 4 else .15)
                for name, value in values.items(): row['fields'].setdefault(name, Moments()).add(seconds, value)
    result = {}
    for sid, row in stats.items():
        result[str(sid)] = {k:v for k,v in row.items() if k not in ('first','last','fields','owner','periods','previous_sequence')}
        result[str(sid)].update(duration_s=(row['last'] - row['first'])/1e9,
            sample_period_s=row['periods'].report(), fields={k:v.report() for k,v in sorted(row['fields'].items())})
    with open(path, 'rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(source=metadata.get('source', 'unknown'), completed=complete, recording_sha256=digest,
                sensors=result, pps_period_s=pps_period.report(),
                qualification='measurements only; no physical acceptance asserted',
                conditions='stationary installation required; nominal sensitivity; package axes; no spectral density or absolute timing claim')


def compare(baseline, active):
    if not baseline['completed'] or not active['completed']: raise ValueError('incomplete bench recording')
    if baseline['sensors'].keys() != active['sensors'].keys(): raise ValueError('sensor inventory changed')
    result = {}
    for sid, old in baseline['sensors'].items():
        new = active['sensors'][sid]
        if old['configuration_sha256'] != new['configuration_sha256']: raise ValueError('configuration changed')
        changes = {}
        for name in old['fields'].keys() & new['fields'].keys():
            a, b = old['fields'][name], new['fields'][name]
            changes[name] = dict(mean_change=b['mean']-a['mean'],
                                 noise_ratio=b['stddev']/a['stddev'] if a['stddev'] and b['stddev'] is not None else None)
        result[sid] = changes
    return dict(baseline_sha256=baseline['recording_sha256'], active_sha256=active['recording_sha256'],
                changes=result, qualification='comparison only; test conditions and acceptance limits required')
