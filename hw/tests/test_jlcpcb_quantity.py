"""Reject the observed five-board supplier default and panel/multiplication errors."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from jlcpcb_bom import ROOT, build_bom
from jlcpcb_package import write_csv, write_json
from jlcpcb_quantity import audit_quantity, check_single_outline

RECT = [((50,-50),(190,-50)), ((190,-50),(190,-106)),
        ((190,-106),(50,-106)), ((50,-106),(50,-50))]


class SingleHATTests(unittest.TestCase):
    def test_single_outline_and_reversed_edges(self):
        self.assertEqual(check_single_outline(RECT)['closed_board_outlines'], 1)
        self.assertEqual(check_single_outline([(b,a) for a,b in reversed(RECT)]), check_single_outline(RECT))

    def test_open_repeated_translated_and_multiple_outlines_rejected(self):
        translated = [((a[0]+90,a[1]), (b[0]+90,b[1])) for a,b in RECT]
        for bad in [RECT[:3], RECT*2, translated, RECT+translated]:
            with self.assertRaises(ValueError): check_single_outline(bad)

    def test_package_audit_rejects_batch_and_component_multiplication(self):
        with (ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/bom.csv').open(newline='') as stream:
            bom, procurement, selections = build_bom(list(csv.DictReader(stream)), 1)
        manifest = dict(requested_assembled_HATs=1, requested_fabricated_HATs=1,
                        boards_per_gerber_design=1, panelized=False,
                        counts={'physical_placements':188})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out/'review').mkdir()
            write_csv(out/'BOM-review.csv', list(bom[0]), bom)
            write_csv(out/'CPL-review.csv', ['Designator'], [{'Designator':r} for r in selections])
            write_csv(out/'procurement.csv', list(procurement[0]), procurement)
            write_json(out/'manifest.json', manifest)
            write_json(out/'review/independent-check.json', {'single_board_outline':check_single_outline(RECT)})
            self.assertEqual(audit_quantity(out)['installed_components'], 188)
            for key, value in [('requested_assembled_HATs',5), ('requested_fabricated_HATs',5),
                               ('boards_per_gerber_design',2), ('panelized',True)]:
                write_json(out/'manifest.json', dict(manifest, **{key:value}))
                with self.assertRaises(ValueError): audit_quantity(out)
            write_json(out/'manifest.json', manifest)
            procurement[0]['Installed_total'] *= 5
            write_csv(out/'procurement.csv', list(procurement[0]), procurement)
            with self.assertRaises(ValueError): audit_quantity(out)


if __name__ == '__main__': unittest.main()
