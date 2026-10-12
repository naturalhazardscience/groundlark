"""Run Burrowlark production C and decode with the independent v1 receiver."""
from pathlib import Path
import subprocess
import sys
import unittest
from groundlark.messages import Envelope
from groundlark.session import Sessions
from groundlark_contract.framing import Decoder

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform.startswith('linux'),'native C runs in the portable software profile')
class HeadFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program=ROOT/'sw/build/head-native'
        cls.program.parent.mkdir(parents=True,exist_ok=True)
        fw=ROOT/'sw/field-head/firmware'
        subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                        '-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
                        '-I'+str(fw),str(fw/'head.c'),str(ROOT/'sw/field-head/tests/native.c'),'-o',str(cls.program)],check=True)

    def capture(self,mode):
        result=subprocess.run([str(self.program),str(mode)],capture_output=True,check=True,timeout=10)
        decoder=Decoder();session=Sessions();messages=[]
        for start in range(0,len(result.stdout),37):
            for payload in decoder.feed(result.stdout[start:start+37]):
                m=Envelope().FromString(payload);session.accept(m);messages.append(m)
        self.assertEqual(decoder.errors,0)
        return messages

    def test_inventory_signed_axes_and_crc(self):
        messages=self.capture(0)
        self.assertEqual(list(messages[0].identity.sensors),[7,18,19,20,17])
        samples=[(m.batch.sensor_id,s) for m in messages if m.WhichOneof('body')=='batch' for s in m.batch.samples]
        mag=[s for sid,s in samples if sid==7]
        self.assertEqual((mag[0].magnetic.counts.x,mag[0].magnetic.counts.y,mag[0].magnetic.counts.z),(-2,0,8388606))
        self.assertTrue(any(s.quality==1 for sid,s in samples if sid==17))
        self.assertTrue(all(s.time.domain==2 and not s.time.HasField('utc_unix_ns') for _,s in samples))

    def test_suspend_during_configuration_cannot_publish_stale_data(self):
        self.assertEqual(self.capture(6),[])

    def test_independent_conversion_clocks_and_four_distinct_spi_lanes(self):
        messages=self.capture(0)
        cohorts={}
        for m in messages:
            if m.WhichOneof('body')!='batch' or m.batch.sensor_id==17:continue
            s=m.batch.samples[0]
            self.assertTrue(s.HasField('magnetic_timing'))
            cohorts.setdefault(s.magnetic_timing.cohort,[]).append((m.batch.sensor_id,s))
        self.assertGreater(len(cohorts),40)
        for rows in cohorts.values():
            self.assertEqual({sid for sid,s in rows},{7,18,19,20})
            self.assertEqual({s.magnetic.counts.y for sid,s in rows},{0,1,2,3})
            self.assertEqual(len({s.magnetic_timing.trigger_ns for sid,s in rows}),1)
            ready=[s.magnetic_timing.ready_observed_ns for sid,s in rows]
            self.assertEqual(max(ready)-min(ready),410_000)
            self.assertTrue(all(not s.time.HasField('uncertainty_ns') for sid,s in rows))

    def test_missing_ready_latches_and_late_ready_evidence_is_preserved(self):
        for mode in (7,8,9):
            messages=self.capture(mode)
            samples=[s for m in messages if m.WhichOneof('body')=='batch' and m.batch.sensor_id in (7,18,19,20) for s in m.batch.samples]
            with self.subTest(mode=mode):
                self.assertTrue(samples)
                if mode in (7,9):
                    self.assertTrue(all(s.quality==2 for s in samples[4:]))
                    self.assertTrue(all(not s.magnetic_timing.HasField('trigger_ns') for s in samples[4:]))
                else:
                    self.assertTrue(all(s.quality==1 for s in samples))
                    ready=[s.magnetic_timing.ready_observed_ns for s in samples[:4]]
                    self.assertEqual(max(ready)-min(ready),2_630_000)

    def test_backpressure_drops_complete_quartets(self):
        cohorts={}
        for m in self.capture(5):
            if m.WhichOneof('body')=='batch' and m.batch.sensor_id in (7,18,19,20):
                cohorts.setdefault(m.batch.samples[0].magnetic_timing.cohort,set()).add(m.batch.sensor_id)
        self.assertTrue(all(ids=={7,18,19,20} for ids in cohorts.values()))

    def test_one_failed_configuration_readback_disables_array_only(self):
        messages=self.capture(10)
        config=next(m.configuration for m in messages if m.WhichOneof('body')=='configuration')
        self.assertEqual({s.sensor_id for s in config.sensors if s.enabled},{17})
        batches=[m.batch for m in messages if m.WhichOneof('body')=='batch']
        self.assertTrue(batches)
        self.assertEqual({b.sensor_id for b in batches},{17})
        self.assertTrue(all(s.quality==1 for b in batches for s in b.samples))

    def test_status_disagreement_or_late_edge_cannot_be_reused(self):
        for mode,failed_sensor in ((11,18),(12,20)):
            messages=self.capture(mode)
            rows=[(m.batch.sensor_id,m.batch.samples[0]) for m in messages
                  if m.WhichOneof('body')=='batch' and m.batch.sensor_id in (7,18,19,20)]
            with self.subTest(mode=mode):
                self.assertEqual({sid for sid,s in rows[:4] if s.quality==2},{failed_sensor})
                self.assertTrue(all(s.quality==1 for sid,s in rows[:4] if sid!=failed_sensor))
                self.assertTrue(all(s.quality==2 and not s.magnetic_timing.HasField('trigger_ns')
                                    and not s.magnetic_timing.HasField('ready_observed_ns') for sid,s in rows[4:]))
                self.assertTrue(any(m.WhichOneof('body')=='status' and m.status.code==3 for m in messages))

    def test_saturation_preserves_exact_signed_endpoints_and_other_lanes(self):
        rows={m.batch.sensor_id:m.batch.samples[0] for m in self.capture(13)
              if m.WhichOneof('body')=='batch' and m.batch.sensor_id in (7,18,19,20)}
        self.assertEqual({sid for sid,s in rows.items() if s.quality==3},{7,20})
        self.assertEqual(rows[7].magnetic.counts.x,8388607)
        self.assertEqual(rows[20].magnetic.counts.z,-8388608)
        self.assertTrue(all(rows[sid].quality==1 for sid in (18,19)))

    def test_maximum_identity_and_large_varints_fit_encoder(self):
        messages=self.capture(14)
        self.assertEqual(len(messages[0].device_id),32)
        self.assertEqual(messages[0].boot_id,2**64-1)
        config=next(m.configuration for m in messages if m.WhichOneof('body')=='configuration')
        self.assertEqual(config.revision,2**32-2)
        batches=[m.batch for m in messages if m.WhichOneof('body')=='batch']
        self.assertEqual({b.sensor_id for b in batches},{7,18,19,20,17})
        self.assertTrue(all(s.sequence>=2**64-1001 and s.time.acquisition_ns>=10**18
                            for b in batches for s in b.samples))

    def test_boot_journal_uses_f042_one_kib_pages_under_power_cuts(self):
        output=ROOT/'sw/build/head-boot-native'
        subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',
            '-DBOOT_PAGE_WORDS=256','-DTEST_PAGE_WORDS=256','-I'+str(ROOT/'sw/skylark/firmware'),
            str(ROOT/'sw/skylark/firmware/boot.c'),str(ROOT/'sw/skylark/tests/boot.c'),'-o',str(output)],check=True)
        subprocess.run([str(output)],check=True,timeout=10)

    def test_faults_disconnect_suspend_and_backpressure(self):
        for mode in range(1,6):
            with self.subTest(mode=mode):
                messages=self.capture(mode)
                batches=[m.batch for m in messages if m.WhichOneof('body')=='batch']
                self.assertTrue(batches)
                self.assertTrue(all(not b.HasField('dropped_before') for b in batches))
                if mode in (1,2):self.assertTrue(any(s.quality==2 for b in batches for s in b.samples))
                if mode in (3,4):self.assertGreater(len([m for m in messages if m.WhichOneof('body')=='identity']),1)
                if mode==5:
                    self.assertTrue(any(m.WhichOneof('body')=='status' and m.status.code==4 for m in messages))
                    seq=[s.sequence for b in batches if b.sensor_id==7 for s in b.samples]
                    self.assertTrue(any(b>a+1 for a,b in zip(seq,seq[1:])))
