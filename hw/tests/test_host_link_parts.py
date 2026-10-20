"""BOM faults independent of physical net connectivity."""
import copy
import csv
import json
from pathlib import Path
import sys
import unittest
import pcbnew

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'))
from host_link_checks import verify_parts


class HostLinkPartsTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01'
        self.board=pcbnew.LoadBoard(str(folder/'groundlark-daqhat-01.kicad_pcb'))
        self.spec=json.loads((ROOT/'hw/groundlark-fpga-hat/layout/placement.json').read_text())['groundlark-daqhat-01']
        with (folder/'bom.csv').open(newline='',encoding='utf8') as stream:self.bom=list(csv.DictReader(stream))

    def test_complete_parts_fixture(self):
        self.assertEqual(verify_parts(self.spec,self.bom,self.board),33)

    def test_wrong_supervisor_variant(self):
        row=next(p for p in self.spec['parts'] if p['ref']=='U104')
        row['mpn']='TLV810EA30DBZR'  # Same land pattern, opposite reset polarity.
        with self.assertRaises(AssertionError):verify_parts(self.spec,self.bom,self.board)

    def test_missing_bypass_or_wrong_resistor_decade(self):
        for ref,field,value in [('C103','DNP','True'),('R107','Value','1k'),('U106','Footprint','SOT-23')]:
            with self.subTest(ref=ref):
                bom=copy.deepcopy(self.bom)
                next(p for p in bom if p['Reference']==ref)[field]=value
                with self.assertRaises(AssertionError):verify_parts(self.spec,bom,self.board)

    def test_board_value_drift(self):
        f=next(f for f in self.board.GetFootprints() if f.GetReference()=='R100')
        f.SetValue('0')
        with self.assertRaises(AssertionError):verify_parts(self.spec,self.bom,self.board)

    def test_duplicate_bom_reference(self):
        self.bom.append(self.bom[-1].copy())
        with self.assertRaises(AssertionError):verify_parts(self.spec,self.bom,self.board)

    def test_uart_idle_bias_cannot_be_omitted_or_tied_to_fpga(self):
        from host_link_checks import verify
        resistor=next(f for f in self.board.GetFootprints() if f.GetReference()=='R118')
        resistor.SetDNP(True)
        with self.assertRaises(AssertionError):verify_parts(self.spec,self.bom,self.board)
        resistor.SetDNP(False)
        pin=next(q for q in resistor.Pads() if q.GetNumber()=='2')
        pin.SetNet(self.board.GetNetsByName()['FPGA_3V3'])
        pins={(f.GetReference(),q.GetNumber()):q.GetNetname() for f in self.board.GetFootprints() for q in f.Pads() if q.GetNumber()}
        with self.assertRaises(AssertionError):verify(pins)


if __name__=='__main__':unittest.main()
