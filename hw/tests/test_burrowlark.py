"""Independent population and SHT45 pin/rail fault fixtures."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from burrowlark_checks import population, climate_pins, array_pins, array_geometry, array_layout

REQUIRED = {"U2", "U7", "U8", "U9", "C4", "C11", "C12", "C13", "R9", "U6", "C10"}


class BurrowlarkPopulationTests(unittest.TestCase):
    def test_magnetic_population(self):
        population(REQUIRED)

    def test_rejects_each_removed_part_even_without_connected_pads(self):
        for ref in ('U3', 'C5'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                population(REQUIRED | {ref})

    def test_rejects_removal_of_magnetic_module_or_bypass(self):
        for refs in ({'U1', 'C4', 'U6', 'C10'}, {'U1', 'U2', 'U6', 'C10'}):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                population(refs)

    def test_requires_each_climate_component(self):
        for removed in ('U6', 'C10'):
            with self.subTest(removed=removed), self.assertRaisesRegex(ValueError, 'SHT45'):
                population(REQUIRED - {removed})

    def test_every_array_part_is_required(self):
        for ref in REQUIRED - {'U6','C10'}:
            with self.subTest(ref=ref),self.assertRaises(ValueError):population(REQUIRED-{ref})

    def test_grid_rejects_rotation_mirror_and_displacement(self):
        parts={ref:dict(xy=xy,angle=0) for ref,xy in
               [('U2',(20,20)),('U7',(50,20)),('U8',(20,50)),('U9',(50,50))]}
        array_geometry(parts,(96,70))
        for changed in ({'angle':180},{'side':'back'},{'xy':(49,50)}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                array_geometry({**parts,'U9':{**parts['U9'],**changed}},(96,70))

    def test_all_numbered_module_pins_and_separate_return_paths(self):
        # Independent manufacturer package fixture, not a copy of .ato nets.
        pins={}
        for lane,ref in enumerate(('U2','U7','U8','U9')):
            for num,net in enumerate(('MAG_SCK',f'MAG_MISO{lane}','MAG_MOSI','MAG_CSN',
                 f'MAG_DRDY{lane}',None,'GND',None,None,'GND',None,'V3_SENSOR','V3_SENSOR','GND'),1):
                pins[ref,str(num)]=net
        for ref in ('C4','C11','C12','C13'):pins[ref,'1']='V3_SENSOR';pins[ref,'2']='GND'
        for num,net in [(7,'MAG_SCK'),(8,'MAG_MOSI'),(9,'MAG_CSN'),(10,'MAG_MISO0'),(11,'MAG_MISO1'),
                        (12,'MAG_MISO2'),(13,'MAG_MISO3'),(14,'MAG_DRDY0'),(15,'MAG_DRDY1'),(26,'MAG_DRDY2'),(27,'MAG_DRDY3')]:
            pins['U1',str(num)]=net
        pins['R9','1']='MAG_CSN';pins['R9','2']='V3_SENSOR'
        array_pins(pins)
        for pin,net in [(('U9','2'),'MAG_MISO0'),(('U7','5'),'MAG_DRDY0'),(('U8','10'),'V3_SENSOR'),
                        (('U2','6'),'GND'),(('U9','11'),'MAG_CSN'),(('R9','2'),'V3'),(('U1','27'),'MAG_MISO3')]:
            with self.subTest(pin=pin),self.assertRaises(ValueError):array_pins({**pins,pin:net})

    def test_rejects_wrong_sensor_supply_and_swapped_bus_pins(self):
        pins = {('U6','1'):'SDA', ('U6','2'):'SCL', ('U6','3'):'V3_SENSOR',
                ('U6','4'):'GND', ('C10','1'):'V3_SENSOR', ('C10','2'):'GND'}
        climate_pins(pins)
        for pin, wrong in [(('U6','1'),'SCL'), (('U6','2'),'SDA'),
                           (('U6','3'),'V3'), (('U6','4'),'SDA'),
                           (('C10','1'),'V3'), (('C10','2'),None)]:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                climate_pins({**pins,pin:wrong})


class BurrowlarkNativeLayoutTests(unittest.TestCase):
    def test_actual_bypass_copper_and_missing_component_faults(self):
        try:import pcbnew as p
        except ImportError:self.skipTest('native KiCad checks run in portable hardware lab')
        from project_paths import board_dir
        path=board_dir('groundlark-field-head')/'groundlark-field-head.kicad_pcb'
        board=p.LoadBoard(str(path));array_layout(board)
        for ref in ('C4','C11','C12','C13'):
            broken=p.LoadBoard(str(path));cap=next(f for f in broken.GetFootprints() if f.GetReference()==ref)
            cap.SetDNP(True)
            with self.subTest(ref=ref),self.assertRaises(AssertionError):array_layout(broken)
