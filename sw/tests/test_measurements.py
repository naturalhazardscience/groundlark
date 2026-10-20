import copy
import math
from pathlib import Path
import tempfile
import unittest
from groundlark.measurements import Moments, analyze, compare
from groundlark.hat_signals import run_bench


class MeasurementTests(unittest.TestCase):
    def test_legacy_dlvr_remains_raw_without_invented_averaging_metadata(self):
        from groundlark import messages
        from groundlark.pressure import DLVR_SETTINGS
        from groundlark.recording import Writer
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'legacy.ssrec'
            with path.open('wb') as stream:
                writer=Writer(stream,dict(format='groundlark-acquisition-v1',source='test',calibrations=[]))
                writer.message(messages.identity('hat',1,1,[8]),0)
                writer.message(messages.configuration('hat',1,[DLVR_SETTINGS]),0)
                writer.message(messages.batch('hat',1,8,0,1,dict(response=bytes.fromhex('20006000')),clock_domain=1),1)
            fields=analyze(path)['sensors']['8']['fields']
        self.assertEqual(fields['legacy_pressure_counts']['mean'],8192)
        self.assertNotIn('read_interval_min_s',fields)

    def test_independent_statistics_known_ramp(self):
        m = Moments()
        for x, y in enumerate((1, 3, 5, 7)): m.add(x, y)
        result = m.report()
        self.assertEqual(result['mean'], 4)
        self.assertEqual(result['slope_per_second'], 2)
        self.assertAlmostEqual(result['stddev'], math.sqrt(20/3))
        self.assertEqual(result['peak_to_peak'], 6)
        self.assertIsNone(Moments().report()['stddev'])

    def test_recording_measurements_do_not_claim_hardware_pass(self):
        data, _ = run_bench()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bench.ssrec'
            path.write_bytes(data)
            report = analyze(path)
        self.assertTrue(report['completed'])
        self.assertIn('no physical acceptance', report['qualification'])
        self.assertEqual(report['sensors']['1']['valid'], 208)
        self.assertEqual(report['sensors']['1']['sequence_gaps'], 0)
        self.assertAlmostEqual(report['sensors']['1']['fields']['acceleration_m_s2.x']['stddev'], .3/math.sqrt(2), delta=.004)
        self.assertNotIn('5', report['sensors'])
        self.assertAlmostEqual(report['sensors']['1']['fields']['temperature_k']['mean'], 298.15, delta=.04)
        self.assertEqual(report['sensors']['9']['valid'], 2640)
        self.assertAlmostEqual(report['sensors']['9']['fields']['input_voltage_v']['stddev'], .002299408/math.sqrt(2), delta=.00001)
        self.assertEqual(report['sensors']['9']['sequence_gaps'], 0)
        self.assertEqual(report['sensors']['8']['valid'],799)
        self.assertEqual(report['sensors']['8']['missing'],1)
        self.assertAlmostEqual(report['sensors']['8']['fields']['pressure_pa']['stddev'],.5/math.sqrt(2),delta=.004)
        self.assertEqual(report['sensors']['8']['fields']['read_interval_max_s']['mean'],.01)
        comparison = compare(report, report)
        self.assertEqual(comparison['changes']['1']['acceleration_m_s2.x']['noise_ratio'], 1)
        self.assertIsNone(comparison['changes']['1']['temperature_k']['noise_ratio'])
        bad = copy.deepcopy(report)
        bad['sensors']['1']['configuration_sha256'] = 'changed'
        with self.assertRaises(ValueError): compare(report, bad)
        bad = copy.deepcopy(report); bad['completed'] = False
        with self.assertRaises(ValueError): compare(report, bad)


if __name__ == '__main__': unittest.main()
