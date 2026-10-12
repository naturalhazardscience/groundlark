"""Skylark contract, UI controller and actual C firmware against injected buses."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from groundlark.messages import Envelope
from groundlark.session import Sessions
from groundlark.recording import Reader
from groundlark.transport import Receiver
from groundlark.workbench import Workbench
from groundlark.board_bench import run_bench
from groundlark_contract.framing import Decoder
from groundlark_contract.validation import validate

ROOT=Path(__file__).resolve().parents[2]


class SkylarkTests(unittest.TestCase):
    def test_board_benches_and_recording_inventory(self):
        for board, sensors in [('skylark',set(range(10,17))),('burrowlark',{7,18,19,20,17})]:
            data, report=run_bench(board)
            self.assertTrue(report['passed'],report)
            e=Workbench();e.load_recording(data);e.seek(8)
            self.assertEqual(e.board,board);self.assertEqual(set(e.sensor_ids),sensors)
            e.reset();self.assertEqual(set(e.sensor_ids),sensors)
            for _,m in Reader(BytesIO(data)):
                if not isinstance(m,dict) and m.WhichOneof('body')=='identity':
                    self.assertEqual(m.identity.board,3 if board=='skylark' else 2)

    def test_switch_is_atomic_and_independent(self):
        a,b=Workbench(board='skylark'),Workbench(board='hat')
        a.controls({'pm25_ug_m3':80});a.running=True;a.advance(100)
        self.assertEqual(a.snapshot(14)['latest'][14]['primary'][1],80)
        with self.assertRaises(ValueError):a.reset(board='unsupported-board')
        self.assertEqual(a.board,'skylark');self.assertEqual(b.now,0)
        a.reset(board='burrowlark');self.assertEqual(set(a.sensor_ids),{7,18,19,20,17})
        self.assertEqual(set(b.sensor_ids),{1,2,3,6,8,9})

    def test_reject_corrupt_raw_frames_and_gas_overflow(self):
        e=Workbench(board='skylark');e.running=True;e.advance(100)
        messages=[m for _,m in Reader(BytesIO(e.finish())) if not isinstance(m,dict) and m.WhichOneof('body')=='batch']
        for m in messages:
            sample=m.batch.samples[0];kind=sample.WhichOneof('raw')
            if kind=='gas':sample.gas.counts=8388608
            elif kind in ('particulate','climate'):
                raw=getattr(sample,kind);raw.response=raw.response[:-1]+bytes([raw.response[-1]^1])
            elif kind=='barometer':sample.barometer.calibration=b''
            else:self.fail(kind)
            with self.assertRaises(ValueError):validate(m)


@unittest.skipUnless(sys.platform.startswith('linux'),'native C fixtures run in the Linux software profile')
class NativeFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which('gcc')
        if not cc:raise RuntimeError('The software profile requires gcc for native firmware tests')
        build=ROOT/'sw/build/skylark-native';build.mkdir(parents=True,exist_ok=True)
        fw=ROOT/'sw/skylark/firmware';tests=ROOT/'sw/skylark/tests'
        cls.native=build/'native'
        flags=[cc,'-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',f'-I{fw}']
        subprocess.run(flags+[str(tests/'native.c'),str(fw/'core.c'),str(fw/'sensors.c'),'-o',str(cls.native)],check=True)
        subprocess.run(flags+[str(tests/'boot.c'),str(fw/'boot.c'),'-o',str(build/'boot')],check=True)
        subprocess.run([str(build/'boot')],check=True,timeout=10)
        cls.peripherals=build/'peripherals'
        subprocess.run(flags+[str(tests/'peripherals.c'),str(fw/'peripherals.c'),'-o',str(cls.peripherals)],check=True)

    def test_mcu_timeouts_errata_and_late_adc_results(self):
        subprocess.run([str(self.peripherals)],check=True,timeout=10)

    def messages(self,mode):
        raw=subprocess.run([str(self.native),str(mode)],capture_output=True,check=True,timeout=10).stdout
        decoder=Decoder();session=Sessions();messages=[]
        for payload in decoder.feed(raw):
            m=Envelope().FromString(payload);session.accept(m);messages.append(m)
        self.assertEqual(decoder.errors,0)
        self.assertFalse(decoder.buffer)
        return messages,raw

    def samples(self, messages, sid, after=0):
        return [s for m in messages if m.WhichOneof('body')=='batch' and m.batch.sensor_id==sid
                for s in m.batch.samples if s.time.acquisition_ns>=after*1_000_000]

    def test_real_encoder_drivers_and_startup_missing(self):
        messages,raw=self.messages(0)
        self.assertEqual(set(messages[0].identity.sensors),set(range(10,17)))
        for sid in range(10,17):
            samples=self.samples(messages,sid);self.assertTrue(samples)
            valid=[s for s in samples if s.quality==1];self.assertTrue(valid,sid)
            if sid<14:
                self.assertGreaterEqual(valid[0].time.acquisition_ns,60_000_000_000)
                self.assertEqual(valid[-1].gas.counts,0x401200+sid-10)
                self.assertTrue(all(s.WhichOneof('raw') is None for s in samples if s.quality==2))
            if sid==14:
                self.assertGreaterEqual(valid[0].time.acquisition_ns,30_000_000_000)
                self.assertEqual(int.from_bytes(valid[-1].particulate.response[12:14],'big'),37)
        receiver=Receiver(Sessions(),board=3);received=[]
        for offset in range(0,len(raw),37):received.extend(receiver.feed(raw[offset:offset+37],offset))
        self.assertEqual(len(received),len(messages));self.assertFalse(any(receiver.errors.values()))

    def test_corruption_latches_adc_and_climate_but_isolates_barometer(self):
        messages,_=self.messages(1)
        for sid in range(10,16):self.assertTrue(all(s.quality==2 for s in self.samples(messages,sid,65000)),sid)
        self.assertTrue(all(s.quality==1 for s in self.samples(messages,16,65000)))
        self.assertTrue(any(m.WhichOneof('body')=='status' and m.status.code==3 for m in messages))

    def test_conversion_counter_loss_is_missing_without_reset(self):
        messages,_=self.messages(2)
        gas=[s for sid in range(10,14) for s in self.samples(messages,sid,61000)]
        self.assertTrue(any(s.quality==2 for s in gas));self.assertTrue(any(s.quality==1 for s in gas))

    def test_wrong_pressure_chip_is_disabled(self):
        messages,_=self.messages(12)
        cfg=next(m.configuration for m in messages if m.WhichOneof('body')=='configuration')
        self.assertFalse(next(s.enabled for s in cfg.sensors if s.sensor_id==16))
        self.assertTrue(self.samples(messages,10,61000))

    def test_acquisition_with_realistic_i2c_transfer_time(self):
        messages,_=self.messages(13)
        for sid in range(10,14):
            samples=self.samples(messages,sid,61000)
            self.assertTrue(all(s.quality==1 for s in samples))
            # More than 29 samples/s over this 11-second window, even with
            # climate/pressure traffic. In-driver assertions reject early reads.
            self.assertGreater(len(samples),319)
            self.assertTrue(all(b.time.acquisition_ns-a.time.acquisition_ns>=32_000_000
                                for a,b in zip(samples,samples[1:])))

    def test_delayed_loop_preserves_conversion_time_and_mux_order(self):
        messages,_=self.messages(9)
        gas=[(m.batch.sensor_id,s) for m in messages if m.WhichOneof('body')=='batch'
             and m.batch.sensor_id<14 for s in m.batch.samples
             if s.time.acquisition_ns>=60_000_000_000]
        self.assertTrue(any(b.sequence>a.sequence+1 for sid in range(10,14)
                            for a,b in zip(self.samples(messages,sid),self.samples(messages,sid)[1:])))
        for (sid,a),(next_sid,b) in zip(gas,gas[1:]):
            self.assertEqual(next_sid,10+(sid-9)%4)
            self.assertGreaterEqual(b.time.acquisition_ns-a.time.acquisition_ns,8_000_000)
            self.assertEqual(b.quality,1)
            self.assertEqual(b.gas.counts,0x401200+next_sid-10)

    def test_queue_overflow_unknown_loss_and_dtr_reannounce(self):
        messages,_=self.messages(3)
        samples=self.samples(messages,10)
        self.assertTrue(any(b.sequence>a.sequence+1 for a,b in zip(samples,samples[1:])))
        self.assertTrue(all(not m.batch.HasField('dropped_before') for m in messages if m.WhichOneof('body')=='batch'))
        resumed,_=self.messages(4)
        self.assertEqual([m.configuration.revision for m in resumed if m.WhichOneof('body')=='configuration'],[1,2])
        self.assertTrue(all(s.quality==1 for s in self.samples(resumed,10,65100)))

    def test_suspend_restarts_conditioning_but_late_dtr_does_not(self):
        resumed,_=self.messages(7)
        self.assertEqual([m.configuration.revision for m in resumed if m.WhichOneof('body')=='configuration'],[1,2])
        self.assertTrue(all(s.quality==2 for s in self.samples(resumed,10,65100)))
        late,_=self.messages(8)
        samples=self.samples(late,10)
        self.assertTrue(samples)
        self.assertGreaterEqual(samples[0].time.acquisition_ns,65_000_000_000)
        self.assertTrue(all(s.quality==1 for s in samples))

    def test_absent_adc_is_explicitly_disabled(self):
        messages,_=self.messages(5)
        cfg=next(m.configuration for m in messages if m.WhichOneof('body')=='configuration')
        self.assertTrue(all(not c.enabled for c in cfg.sensors if c.sensor_id<14))
        self.assertFalse(self.samples(messages,10));self.assertTrue(self.samples(messages,15))

    def test_suspend_during_configuration_keeps_electrodes_clamped(self):
        messages,_=self.messages(6)
        self.assertEqual([m.configuration.revision for m in messages if m.WhichOneof('body')=='configuration'],[1])
        self.assertGreaterEqual(self.samples(messages,10)[0].time.acquisition_ns,1_000_000_000)

    def test_suspend_discards_pending_temperature_conversion(self):
        messages,_=self.messages(10)
        self.assertEqual([m.configuration.revision for m in messages if m.WhichOneof('body')=='configuration'],[1,2])
        self.assertTrue(all(s.quality==2 for s in self.samples(messages,10,62000)))
        self.assertTrue(any(s.quality==1 for s in self.samples(messages,15,62000)))

    def test_pms_supply_fault_does_not_stop_gas_acquisition(self):
        messages,_=self.messages(11)
        self.assertTrue(all(s.quality==2 for s in self.samples(messages,14,62000)))
        for sid in (10,11,12,13,15,16):
            self.assertTrue(any(s.quality==1 for s in self.samples(messages,sid,65000)),sid)

    def test_firmware_stream_to_standalone_capture_and_ui_replay(self):
        from groundlark.usb_capture import capture
        _,raw=self.messages(0)
        now=[0];closed=[]
        class USBFixture:
            def __init__(self,path,receiver):self.receiver=receiver;self.offset=0
            def poll(self,at,message,event):
                chunk=raw[self.offset:self.offset+4096];self.offset+=len(chunk)
                for m in self.receiver.feed(chunk,at):message(m,at)
            def close(self):closed.append(True)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'capture.ssrec'
            args=SimpleNamespace(board='skylark',usb='/dev/ttyACM0',seconds=1,max_mib=8,output=path)
            result=capture(args,factory=USBFixture,clock=lambda:now[0],sleep=lambda _:now.__setitem__(0,now[0]+1_000_000))
            self.assertTrue(result['completed']);self.assertGreater(result['valid'],0);self.assertEqual(closed,[True])
            e=Workbench();e.load_recording(path.read_bytes());e.seek(e.duration/1e9)
            self.assertEqual(e.board,'skylark');self.assertEqual(e.snapshot(14)['latest'][14]['primary'][1],37)
