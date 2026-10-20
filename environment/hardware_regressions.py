"""Simulation profile excludes one procurement-release gate, explicitly by ID.

All native geometry and available supplier-pad fault fixtures remain enabled.
Full/quick profiles keep normal unittest discovery, including the release gate.
"""
import sys
import unittest

PROCUREMENT_GATE='test_pcb_handedness.HandednessTests.test_supplier_placement_release_gate'


def without_procurement(suite):
    selected=unittest.TestSuite();excluded=[]
    def visit(item):
        if isinstance(item,unittest.TestSuite):
            for child in item:visit(child)
        elif item.id()==PROCUREMENT_GATE:excluded.append(item.id())
        else:selected.addTest(item)
    visit(suite)
    if excluded!=[PROCUREMENT_GATE]:raise RuntimeError('Expected exactly one named procurement gate')
    return selected,excluded


if __name__=='__main__':
    suite,excluded=without_procurement(unittest.defaultTestLoader.discover('hw/tests',pattern='test_*.py'))
    print('Scope exclusion (not a pass): '+', '.join(excluded),flush=True)
    sys.exit(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
