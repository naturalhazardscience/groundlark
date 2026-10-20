"""D90 replacement against TI pin assignments and frozen numbered supplier pads.

Deliberately isolates D90 from the older, incomplete full-board registry. These
checks never establish current inventory or authorize a complete assembly order.
"""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jlcpcb_bom import ROOT, build_bom, load_registry
from jlcpcb_placement import board_geometry, correct_placements, load_mappings


class D90ReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew
        cls.folder = ROOT / 'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01'
        cls.board_path = cls.folder / 'groundlark-daqhat-01.kicad_pcb'
        cls.before = cls.board_path.read_bytes()
        cls.board = pcbnew.LoadBoard(str(cls.board_path))
        with (cls.folder / 'bom.csv').open(newline='') as stream:
            cls.source = [r for r in csv.DictReader(stream) if r['Reference'] == 'D90']
        cls.registry = load_registry()
        cls.registry['parts'] = [p for p in cls.registry['parts'] if p['designators'] == ['D90']]
        cls.geometry = [g for g in board_geometry(cls.board) if g['reference'] == 'D90']
        cls.mapping = load_mappings()
        cls.mapping['footprints'] = [e for e in cls.mapping['footprints'] if e['designators'] == ['D90']]
        cls.mapping['unverified'] = []
        cls.placements = [dict(Designator='D90', MidX='61.800000mm', MidY='-96.800000mm',
                              Layer='Bottom', Rotation='0.000000')]

    @classmethod
    def tearDownClass(cls):
        assert cls.board_path.read_bytes() == cls.before, 'Replacement checks modified routed CAD'

    def solve(self, geometry=None, mapping=None, selections=None):
        if selections is None:
            _, _, selections = build_bom(self.source, 1, self.registry)
        return correct_placements(self.placements, self.geometry if geometry is None else geometry,
                                  selections, self.mapping if mapping is None else mapping)

    def test_exact_orderable_identity_in_source_and_upload(self):
        mpn = 'TPD2E2U06QDCKRQ1'
        self.assertEqual(self.source[0]['MPN'], mpn)
        bom, _, _ = build_bom(self.source, 1, self.registry)
        self.assertEqual((bom[0]['Comment'], bom[0]['MPN'], bom[0]['JLCPCB Part #'],
                          bom[0]['Manufacturer'], bom[0]['Footprint']),
                         (mpn, mpn, 'C915089', 'Texas Instruments', 'SC-70-3'))
        authored = (ROOT / 'hw/groundlark-fpga-hat/elec/geophone_parts.ato').read_text()
        self.assertIn(f'manufacturer="Texas Instruments", partnumber="{mpn}"', authored)
        for path, key in [(ROOT / 'hw/groundlark-fpga-hat/layout/placement.json', 'groundlark-daqhat-01'),
                          (self.folder / 'electrical.json', None)]:
            data = json.loads(path.read_text())
            if key:
                data = data[key]
            self.assertEqual(next(p for p in data['parts'] if p['ref'] == 'D90')['mpn'], mpn)
        # The portable lab intentionally excludes previously generated netlists.
        # Read the actual schematic through a fresh export, without rewriting CAD.
        with tempfile.TemporaryDirectory() as tmp:
            netlist = Path(tmp) / 'schematic.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                            '-o', str(netlist), str(self.folder / 'groundlark-daqhat-01.kicad_sch')],
                           check=True, capture_output=True)
            component = ET.parse(netlist).find('.//comp[@ref="D90"]')
            self.assertEqual(component.find('./fields/field[@name="MPN"]').text, mpn)

    def test_ti_dck_pin_fixture_and_native_pose(self):
        fp = next(f for f in self.board.GetFootprints() if f.GetReference() == 'D90')
        # TI SLLSEJ9E table 5-1: 1/2 are the signal pins; 3 is ground.
        self.assertEqual({p.GetNumber(): p.GetNetname() for p in fp.Pads()},
                         {'1': 'GEO_P', '2': 'GEO_N', '3': 'GND'})
        self.assertTrue(fp.IsFlipped())
        self.assertEqual(fp.GetOrientationDegrees() % 360, 90)
        self.assertEqual(self.geometry[0]['footprint_origin_mm'], [61.8, 96.8])

    def test_supplier_fit_preserves_bottom_90_degree_placement(self):
        rows, audit = self.solve()
        self.assertEqual(rows[0], dict(self.placements[0], Rotation='90.000000'))
        self.assertEqual(audit[0]['pads_checked'], 3)
        self.assertEqual(audit[0]['coordinate_projection'], 'mirror_local_x_then_ccw')
        self.assertGreater(audit[0]['min_pad_overlap_fraction'], 0.9)

    def test_wrong_ground_pad_or_displaced_land_rejected(self):
        for fault in ('ground_pin_swap', 'pad_shift'):
            geometry = copy.deepcopy(self.geometry)
            pads = {p['number']: p for p in geometry[0]['pads']}
            if fault == 'ground_pin_swap':
                pads['1']['number'], pads['3']['number'] = '3', '1'
            else:
                pads['3']['xy_mm'][0] += 1
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'No SMT orientation'):
                self.solve(geometry=geometry)

    def test_wrong_part_or_implicit_bottom_projection_rejected(self):
        _, _, selections = build_bom(self.source, 1, self.registry)
        selections['D90'] = dict(selections['D90'], mpn='TPD2E2U06QDBZRQ1')
        with self.assertRaisesRegex(ValueError, 'Stale supplier placement identity'):
            self.solve(selections=selections)
        mapping = copy.deepcopy(self.mapping)
        mapping['footprints'][0].pop('bottom_basis')
        with self.assertRaisesRegex(ValueError, 'bottom-side projection'):
            self.solve(mapping=mapping)

    def test_unavailable_or_bulk_only_record_cannot_pass_procurement(self):
        for fault in ({'available_order_quantity': 0}, {'minimum_quantity': 35},
                      {'status': 'preorder_required'}):
            registry = copy.deepcopy(self.registry)
            registry['procurement_policy']['require_available_stock'] = True
            registry['parts'][0]['stock_observation'].update(fault)
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'procurement policy'):
                build_bom(self.source, 1, registry)
