"""Independent mirror, row-swap and missing-contact fault fixtures."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pcb_handedness import audit,check_header


class HandednessTests(unittest.TestCase):
    def test_native_boards_and_supplier_sides(self):
        report=audit()['boards']['groundlark-daqhat-01']
        self.assertEqual(report['pi_numbered_positions'],40)
        self.assertEqual(report['Trenz']['module_contact_checks'],260)
        self.assertEqual(report['supplier_numbered_placements'],188)

    def test_mirror_and_row_swap_rejected(self):
        # Official 2.54 mm header fixture: pin 1 is on the inner row.
        fixture={str(n):(8.38+((n-1)//2)*2.54,4.77 if n%2 else 2.23) for n in range(1,41)}
        for bad in ({n:(x,7-y) for n,(x,y) in fixture.items()},
                    {n:(65.02-x,y) for n,(x,y) in fixture.items()},
                    {n:xy for n,xy in fixture.items() if n!='40'}):
            with self.assertRaises(ValueError):check_header(bad,fixture)


if __name__=='__main__':unittest.main()
