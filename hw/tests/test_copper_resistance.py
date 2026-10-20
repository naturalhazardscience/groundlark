"""Analytical networks and independent native-board copper-removal faults."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from copper_resistance import network_resistance,resistivity,stackup,extract,pi_loop,fpga_loop

BOARD=Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'


class NetworkTests(unittest.TestCase):
    def test_series_parallel_and_floating_island(self):
        # 2 ohms + (3 || 6) ohms; isolated 7-ohm edge cannot carry current.
        self.assertAlmostEqual(network_resistance(5,[0,1,1,3],[1,2,2,4],[.5,1/3,1/6,1/7],[0],[2]),4)
        with self.assertRaises(ValueError):network_resistance(4,[0,2],[1,3],[1,1],[0],[3])
        with self.assertRaises(ValueError):network_resistance(2,[0],[1],[-1],[0],[1])
    def test_copper_temperature_and_real_stack(self):
        self.assertAlmostEqual(resistivity(20),1.724e-5)
        self.assertAlmostEqual(resistivity(85)/resistivity(20),1.25545)
        layers=stackup(BOARD)
        self.assertEqual([r['name'] for r in layers],['F.Cu','In1.Cu','In2.Cu','In3.Cu','In4.Cu','B.Cu'])
        self.assertEqual([r['thickness_mm'] for r in layers],[.035,.0152,.0152,.0152,.0152,.035])


class NativeCopperTests(unittest.TestCase):
    def load(self):
        import pcbnew as p
        return p.LoadBoard(str(BOARD))
    def test_native_loop_and_refinement(self):
        board=self.load();before=BOARD.read_bytes();report=pi_loop(board,BOARD)
        self.assertLess(report['copper_with_reserve_ohm'],.035)
        fine=extract(board,'PI_5V',[('U133',9),('U133',10)],[('J1',2),('J1',4)],stackup(BOARD),.05)
        coarse=next(r for r in report['paths'] if r['net']=='PI_5V')['resistance_ohm']
        self.assertLess(abs(fine['resistance_ohm']/coarse-1),.05)
        self.assertFalse(report['contacts_measured']);self.assertEqual(before,BOARD.read_bytes())
    def test_original_inner_only_distribution_fails(self):
        board=self.load()
        removed=[z for z in board.Zones() if z.GetNetname()=='PI_5V']
        for z in removed:board.Delete(z)
        result=extract(board,'PI_5V',[('U133',9),('U133',10)],[('J1',2),('J1',4)],stackup(BOARD))
        self.assertGreater(result['resistance_ohm'],.05)
    def test_missing_output_vias_disconnects_supply(self):
        import pcbnew as p
        board=self.load()
        removed=[t for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='PI_5V']
        for t in removed:board.Delete(t)
        # Front edge copper is still present, so explicitly cut it too.
        zones=[z for z in board.Zones() if z.GetNetname()=='PI_5V']
        for z in zones:board.Delete(z)
        with self.assertRaises(ValueError):
            extract(board,'PI_5V',[('U133',9),('U133',10)],[('J1',2),('J1',4)],stackup(BOARD))
    def test_diode_thermal_copper_omission(self):
        from pi_power_checks import diode_spreader
        board=self.load();report=diode_spreader(board)
        self.assertGreater(report['loss_scenario_W'],1)
        self.assertIsNone(report['junction_temperature_C'])
        removed=[z for z in board.Zones() if z.GetNetname()=='BAT_PROTECTED']
        for z in removed:board.Delete(z)
        with self.assertRaisesRegex(ValueError,'heat-spreading'):diode_spreader(board)
    def test_fpga_distribution_bridge_required(self):
        import pcbnew as p
        board=self.load()
        fpga_loop(board,BOARD)
        bridge=[z for z in board.Zones() if z.GetNetname()=='FPGA_VIN' and z.GetLayer()==p.F_Cu and z.GetAssignedPriority()==5]
        self.assertEqual(len(bridge),1)
        for z in bridge:board.Delete(z)
        with self.assertRaisesRegex(ValueError,'FPGA copper'):fpga_loop(board,BOARD)
