"""Independent skew/cohort/calibration and noise fixtures for four-lane reduction."""
import copy
import itertools
import unittest
from groundlark import messages
from groundlark.calibration import configuration_hash
from groundlark.magnetic_array import SENSORS, average_cohort


class MagneticArrayTests(unittest.TestCase):
    def setUp(self):
        self.config = messages.configuration('quad', 1, [dict(sensor_id=s, enabled=True,
            period_ns=100_000_000, cycle_count_x=200, cycle_count_y=200, cycle_count_z=200) for s in SENSORS])
        self.cal = dict(id='test-only', device_id='quad', provenance='Synthetic fixture, not a physical calibration',
            configuration_sha256=configuration_hash(self.config.configuration), lanes={str(s):
            dict(matrix_t_per_count=[[1e-9,0,0],[0,1e-9,0],[0,0,1e-9]], offset_t=[0,0,0]) for s in SENSORS})

    def samples(self, values=(0,1,2,3)):
        return [messages.batch('quad',1,s,0,20_000_000,{'counts':(values[i],0,0)},dropped=None,
            magnetic_timing=dict(cohort=0,trigger_ns=1_000_000,ready_observed_ns=14_000_000+i*100_000)) for i,s in enumerate(SENSORS)]

    def average(self, data):
        return average_cohort(data,self.config,self.cal,max_ready_skew_ns=1_000_000)

    def test_preserves_fractional_counts_raw_and_axis_calibration(self):
        data=self.samples();before=[m.SerializeToString() for m in data]
        field=self.average(list(reversed(data)))
        self.assertAlmostEqual(field.magnetic_t[0],1.5e-9)
        self.assertEqual(field.ready_skew_ns,300_000)
        self.assertEqual(before,[m.SerializeToString() for m in data])
        # Lane 2 has its X axis in common Y and a measured common-X offset.
        self.cal['lanes']['18'].update(matrix_t_per_count=[[0,-1e-9,0],[1e-9,0,0],[0,0,1e-9]],offset_t=[4e-9,0,0])
        field=self.average(data)
        self.assertAlmostEqual(field.magnetic_t[0],2.25e-9)
        self.assertAlmostEqual(field.magnetic_t[1],.25e-9)

    def test_independent_noise_halves_but_common_noise_remains(self):
        means=[self.average(self.samples(values)).magnetic_t[0] for values in itertools.product((-1,1),repeat=4)]
        self.assertAlmostEqual((sum(v*v for v in means)/16)**.5/1e-9,.5)
        self.assertAlmostEqual(self.average(self.samples((1,1,1,1))).magnetic_t[0]/1e-9,1)

    def test_rejects_missing_duplicate_mixed_late_saturated_or_unproven(self):
        for fault in ('missing','duplicate','cohort','trigger','boot','device','revision','late','saturated','no_timing'):
            data=self.samples();sample=data[3].batch.samples[0]
            if fault=='missing': data.pop()
            elif fault=='duplicate': data[3].CopyFrom(data[0])
            elif fault=='cohort': sample.sequence=sample.magnetic_timing.cohort=1
            elif fault=='trigger': sample.magnetic_timing.trigger_ns+=1
            elif fault=='boot': data[3].boot_id=2
            elif fault=='device': data[3].device_id='another'
            elif fault=='revision': data[3].batch.configuration_revision=2
            elif fault=='late': sample.magnetic_timing.ready_observed_ns+=2_000_000
            elif fault=='saturated': sample.quality=3
            elif fault=='no_timing': sample.ClearField('magnetic_timing')
            with self.subTest(fault=fault),self.assertRaises(ValueError): self.average(data)

    def test_calibration_and_configuration_must_match(self):
        for fault in ('digest','device','lane','matrix','disabled','cycles'):
            cal,config=copy.deepcopy(self.cal),type(self.config)();config.CopyFrom(self.config)
            if fault=='digest':cal['configuration_sha256']='0'*64
            elif fault=='device':cal['device_id']='other'
            elif fault=='lane':del cal['lanes']['18']
            elif fault=='matrix':cal['lanes']['18']['matrix_t_per_count'][1]=[0,0,0]
            elif fault=='disabled':config.configuration.sensors[1].enabled=False;config.configuration.sensors[1].period_ns=0
            elif fault=='cycles':config.configuration.sensors[1].cycle_count_x=400
            if fault in ('disabled','cycles'):cal['configuration_sha256']=configuration_hash(config.configuration)
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                average_cohort(self.samples(),config,cal,max_ready_skew_ns=1_000_000)
