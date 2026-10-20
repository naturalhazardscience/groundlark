"""Regression fixtures from the failed JLC match, independent of exporter logic."""
import copy
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jlcpcb_bom import ROOT, build_bom, resolve, load_registry, check_upload_roundtrip, sourcing_status
from jlcpcb_package import check_reference_sets, write_csv, export


class ExactAssemblyBOMTests(unittest.TestCase):
    def setUp(self):
        with (ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/bom.csv').open(newline='') as f:
            self.source = list(csv.DictReader(f))
        self.registry = load_registry()

    def rows(self, quantity=1):
        return build_bom(self.source, quantity, self.registry)

    def test_known_bad_matches_replaced_with_exact_identities(self):
        bom, _, _ = self.rows()
        by_ref = {ref: row for row in bom for ref in row['Designator'].split(',')}
        # Supplier suggested diode C19077484, inductor C20612919, 01005
        # capacitor C161372, X7R filters C24497/C1588 and non-TI ICs.
        fixture = {
            'R61': ('RC0603FR-0747RL', 'C114623', '0603', 'YAGEO'),
            'R96': ('RC0603FR-0722RL', 'C107701', '0603', 'YAGEO'),
            'C12': ('GRM155R71C104KA88D', 'C71629', '0402', 'Murata Electronics'),
            'C90': ('GRM31C5C1H104JA01L', 'C97946', '1206', 'Murata Electronics'),
            'C91': ('C0603C102J5GAC7867', 'C140950', '0603', 'KEMET'),
            'U40': ('LDL1117S33R', 'C435835', 'SOT-223-4', 'STMicroelectronics'),
            'D90': ('TPD2E2U06QDCKRQ1', 'C915089', 'SC-70-3', 'Texas Instruments'),
        }
        for ref, expected in fixture.items():
            with self.subTest(ref=ref):
                row = by_ref[ref]
                self.assertEqual(tuple(row[k] for k in ('Comment','JLCPCB Part #','Footprint','Manufacturer')), expected)
        for ref in ['C13','C14','C15','C16','C17']:
            self.assertEqual(by_ref[ref], by_ref['C12'])
        for ref in ['R100','R101','R102','R103','R104','R105']:
            self.assertEqual(by_ref[ref], by_ref['R96'])
        self.assertEqual(by_ref['C92'], by_ref['C91'])

    def test_all_190_placements_once_and_no_removed_sensors(self):
        bom, procurement, _ = self.rows()
        refs = [r for row in bom for r in row['Designator'].split(',')]
        self.assertEqual(len(refs),190)
        self.assertEqual(len(set(refs)),190)
        self.assertFalse(set(refs) & {'U14','U20','C18','C19','C20','C21','C22','C23','R14','R20'})
        self.assertEqual(sum(r['Installed_total'] for r in procurement),190)
        check_reference_sets(bom,[{'Designator':ref} for ref in refs])

    def test_preorder_bulk_minimum_unknown_or_insufficient_stock_rejected(self):
        for fault in [dict(status='preorder_required'), dict(minimum_quantity=35),
                      dict(minimum_quantity=None), dict(available_order_quantity=0),
                      dict(available_order_quantity=None), dict(source_url='https://jlcpcb.com/other')]:
            registry = copy.deepcopy(self.registry)
            registry['procurement_policy']['require_available_stock'] = True
            registry['parts'][0]['stock_observation'].update(fault)
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'procurement policy'):
                build_bom(self.source, 1, registry)

    def test_stock_is_aggregated_across_source_footprints(self):
        registry = copy.deepcopy(self.registry)
        registry['procurement_policy']['require_available_stock'] = True
        parts = [p for p in registry['parts'] if p['lcsc'] == 'C77055']
        required = sum(len(p['designators']) for p in parts)
        self.assertGreater(len(parts), 1)
        for p in parts:
            p['stock_observation']['available_order_quantity'] = required - 1
            self.assertGreaterEqual(required - 1, len(p['designators']))
        with self.assertRaisesRegex(ValueError, 'procurement policy'):
            build_bom(self.source, 1, registry)

    def test_reviewed_shortage_replacements_and_unchanged_counts(self):
        bom, procurement, selections = self.rows()
        by_ref = {ref: r for r in bom for ref in r['Designator'].split(',')}
        expected = [(['C42','C80','C81','C82'], 'CL31A226KAHNNNE', 'C12891', '1206'),
                    (['C84','C85'], 'GRM21BR71C475KE51L', 'C408144', '0805'),
                    (['C90'], 'GRM31C5C1H104JA01L', 'C97946', '1206'),
                    (['F80'], '0466002.NRHF', 'C3105', '1206'),
                    (['U23'], 'SDP32-125PA-TR-250PCS', 'C6473035', 'SMD-16P'),
                    (['U11','U12','U13'], 'LSM6DSOXTR', 'C481766', 'LGA-14')]
        for refs, mpn, code, package in expected:
            for ref in refs:
                self.assertEqual((by_ref[ref]['MPN'], by_ref[ref]['JLCPCB Part #'], by_ref[ref]['Footprint']), (mpn,code,package))
                self.assertTrue(selections[ref]['resolution'])
                self.assertTrue(selections[ref]['manufacturer_evidence'])
        self.assertEqual(len(bom), 72)
        self.assertEqual(sum(r['Installed_total'] for r in procurement), 190)
        self.assertEqual(by_ref['F80']['Description'], '2A fast-acting fuse, 32V, 1206')

    def test_wrong_chip_package_and_undocumented_substitution_rejected(self):
        for ref in ['F80','C42','C84','C90']:
            for mode in ['package','resolution']:
                if ref == 'F80' and mode == 'resolution':continue  # Exact source MPN now.
                reg=copy.deepcopy(self.registry)
                part=next(p for p in reg['parts'] if ref in p['designators'])
                part[mode]='0603' if mode=='package' else ''
                with self.subTest(ref=ref,mode=mode), self.assertRaises(ValueError):
                    resolve(self.source,reg)

    def test_f80_routed_lands_fit_1206_fuse_not_old_0603_selection(self):
        import pcbnew as p
        board=p.LoadBoard(str(ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'))
        fuse=next(f for f in board.GetFootprints() if f.GetReference()=='F80')
        pads=sorted(fuse.Pads(),key=lambda pad:pad.GetNumber())
        self.assertEqual(len(pads),2)
        x1,y1=p.ToMM(pads[0].GetPosition()); x2,y2=p.ToMM(pads[1].GetPosition())
        self.assertAlmostEqual(((x2-x1)**2+(y2-y1)**2)**.5,2.8,places=5)
        for pad in pads:
            self.assertEqual(tuple(round(v,5) for v in p.ToMM(pad.GetSize())),(1.25,1.75))
        # 466 end terminations overlap the pads even at minimum body length;
        # the longest body ends remain within the outer pad span.
        self.assertLess(1.4-1.25/2,(3.175-.127)/2)
        self.assertGreater(1.4+1.25/2,(3.175+.127)/2)

    def test_one_hat_quantity_is_not_supplier_five_board_default(self):
        _, procurement, _ = self.rows()
        for row in procurement:
            self.assertEqual(row['Requested_HATs'],1)
            self.assertEqual(row['Installed_total'],row['Per_HAT'])
        connectors = {r['Designator']: r['Installed_total'] for r in procurement}
        self.assertEqual(connectors['J80,J81'], 2)
        self.assertEqual(connectors['J82'], 1)

    def test_invalid_quantities(self):
        for qty in [0,-1,1.0,1.5,True,2,5,10]:
            with self.assertRaises(ValueError): self.rows(qty)

    def test_export_rejects_batch_before_creating_files_or_loading_cad(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'must-not-exist'
            for qty in [2,5,10,True]:
                with self.assertRaisesRegex(ValueError, 'ONE SINGLE HAT'):
                    export(out, qty)
                self.assertFalse(out.exists())

    def test_primary_import_fields_are_sufficient(self):
        bom,_,_ = self.rows()
        for row in bom:
            self.assertEqual(row['Comment'],row['MPN'])
            self.assertNotIn('__',row['Footprint'])
            self.assertNotIn('service ONLY',row['Comment'])
        self.assertEqual({row['Designator'] for row in bom if not row['JLCPCB Part #']},{'L140','L141'})
        self.assertEqual({row['MPN'] for row in bom if not row['JLCPCB Part #']},
                         {'0402HPH-56NXJRW','0402HP-3N6XJRW'})

    def test_placeholder_and_generic_device_resolutions_are_explicit(self):
        _, _, selections = self.rows()
        for ref,mpn in [('J4','TSW-104-07-G-S'),('JP1','TSW-102-07-G-S'),('Q1','2N7002,215')]:
            self.assertEqual(selections[ref]['mpn'],mpn)
            self.assertTrue(selections[ref]['resolution'])
        self.assertEqual(selections['Q1']['manufacturer'],'Nexperia')

    def test_jumper_same_part_grouped_once(self):
        bom,_,_ = self.rows()
        rows=[r for r in bom if r['MPN']=='TSW-102-07-G-S']
        self.assertEqual(len(rows),1)
        self.assertEqual(set(rows[0]['Designator'].split(',')),{'JP1','JP80','JP81','JP130'})

    def test_filter_caps_use_available_equivalent_with_documented_specification(self):
        bom,procurement,selections=self.rows()
        row=next(r for r in bom if r['Designator']=='C91,C92')
        self.assertEqual(row['MPN'],'C0603C102J5GAC7867')
        self.assertEqual(row['JLCPCB Part #'],'C140950')
        self.assertEqual(row['Description'],'1nF 50V C0G +/-5% 0603 nonpolar MLCC')
        self.assertEqual(next(r for r in procurement if r['Designator']=='C91,C92')['Installed_total'],2)
        self.assertEqual(selections['C91']['source_mpn'],'C0603C102J5GACTU')
        self.assertIn('alias',selections['C91']['resolution'])
        self.assertIn('search.kemet.com',selections['C91']['manufacturer_evidence'])
        registry=copy.deepcopy(self.registry)
        next(p for p in registry['parts'] if 'C91' in p['designators'])['resolution']=''
        with self.assertRaisesRegex(ValueError,'Undocumented'):build_bom(self.source,1,registry)

    def test_missing_catalog_code_does_not_omit_pi_socket(self):
        registry = copy.deepcopy(self.registry)
        next(p for p in registry['parts'] if p['designators'] == ['J1'])['lcsc'] = ''
        _, procurement, _ = build_bom(self.source, 1, registry)
        row=next(r for r in procurement if r['Designator']=='J1')
        self.assertEqual(row['MPN'],'ZX-PM2.54-2-20PY')
        self.assertEqual(row['JLCPCB Part #'],'')
        self.assertEqual(row['Installed_total'],1)
        self.assertIn('MANUAL SOURCING',row['Sourcing_status'])

    def test_j1_selectable_part_propagates_to_every_upload_field(self):
        bom, procurement, selections = self.rows()
        row = next(r for r in bom if r['Designator'] == 'J1')
        self.assertEqual(row['Comment'], 'ZX-PM2.54-2-20PY')
        self.assertEqual(row['MPN'], 'ZX-PM2.54-2-20PY')
        self.assertEqual(row['Manufacturer'], 'Megastar')
        self.assertEqual(row['JLCPCB Part #'], 'C7499354')
        self.assertEqual(row['Footprint'], 'THT socket 2x20 P2.54mm')
        part = selections['J1']
        self.assertEqual(part['evidence_url'], 'https://jlcpcb.com/partdetail/Megastar-ZX_PM2_54_220PY/C7499354')
        self.assertEqual(part['jlc_match_status'], 'catalog_listed')
        self.assertEqual(part['source_mpn'], 'ESQ-120-23-G-D')
        self.assertTrue(part['resolution'])
        self.assertEqual(part['mechanical_review'], 'CAD envelope updated; physical mating pending')
        self.assertIn('stack-height and placement review required', row['Description'])
        purchase = next(r for r in procurement if r['Designator'] == 'J1')
        self.assertEqual(purchase['Installed_total'], 1)
        self.assertEqual(purchase['MPN'], row['MPN'])
        self.assertEqual(purchase['JLCPCB Part #'], row['JLCPCB Part #'])
        self.assertIn('Listed in JLCPCB assembly catalog', purchase['Sourcing_status'])
        self.assertIn('approval pending', purchase['Sourcing_status'])

    def test_j1_replacement_requires_documented_resolution(self):
        registry=copy.deepcopy(self.registry)
        next(p for p in registry['parts'] if p['designators']==['J1'])['resolution']=''
        with self.assertRaisesRegex(ValueError,'Undocumented ordering-code resolution'):
            build_bom(self.source,1,registry)

    def test_changed_value_footprint_mpn_or_dnp_requires_review(self):
        for key,value in [('Value','47k'),('Footprint','R_0402'),('MPN','1SMA4747A'),('DNP','True')]:
            source=copy.deepcopy(self.source)
            next(r for r in source if r['Reference']=='R61')[key]=value
            with self.assertRaises(ValueError): resolve(source,self.registry)

    def test_missing_duplicate_or_new_source_reference_rejected(self):
        for source in [self.source[1:],self.source+[self.source[0]],self.source+[dict(self.source[0],Reference='J999')]]:
            with self.assertRaises(ValueError): resolve(source,self.registry)

    def test_missing_duplicate_selection_or_evidence_rejected(self):
        for mode in ['missing','duplicate','evidence','resolution']:
            reg=copy.deepcopy(self.registry)
            if mode=='missing':reg['parts'].pop()
            if mode=='duplicate':reg['parts'].append(reg['parts'][0])
            if mode=='evidence':reg['parts'][0]['evidence_url']=''
            if mode=='resolution':next(p for p in reg['parts'] if p['source_mpn']=='2N7002')['resolution']=''
            with self.assertRaises(ValueError):resolve(self.source,reg)

    def test_conflicting_catalog_code_and_placeholder_rejected(self):
        for mode in ['conflict','placeholder']:
            reg=copy.deepcopy(self.registry)
            p=next(p for p in reg['parts'] if 'C90' in p['designators'])
            if mode=='conflict':
                p['lcsc']='C71629';p['evidence_url']='https://jlcpcb.com/partdetail/C71629'
            else:p['mpn']='100n C0G capacitor'
            with self.assertRaises(ValueError):resolve(self.source,reg)

    def test_csv_roundtrip_handles_comma_in_nexperia_ordering_code(self):
        bom,_,_=self.rows()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bom.csv';write_csv(path,list(bom[0]),bom)
            check_upload_roundtrip(path,bom)
            text=path.read_text()
            self.assertIn('"2N7002,215"',text)
            path.write_text(text.replace('JLCPCB Part #','Ignored Column'))
            with self.assertRaises(ValueError):check_upload_roundtrip(path,bom)

    def test_substitution_requires_manufacturer_evidence(self):
        for ref in ('U11', 'C86', 'C89', 'C42', 'C84', 'C90', 'C91', 'J1'):
            registry=copy.deepcopy(self.registry)
            next(p for p in registry['parts'] if ref in p['designators']).pop('manufacturer_evidence')
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError,'manufacturer evidence'):
                build_bom(self.source,1,registry)

    def test_catalog_evidence_matches_whole_code_not_substring(self):
        for url in ('https://jlcpcb.com/partdetail/C1409500',
                    'https://example.com/partdetail/C140950',
                    'https://jlcpcb.com/partdetail/C999?old=C140950'):
            registry=copy.deepcopy(self.registry)
            next(p for p in registry['parts'] if 'C91' in p['designators'])['evidence_url']=url
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'catalog evidence'):
                resolve(self.source,registry)

    def test_stock_observation_never_becomes_reservation_or_purchase_quantity(self):
        # Offline regression: a historic stock snapshot must not promise today's allocation.
        registry=copy.deepcopy(self.registry)
        p=next(p for p in registry['parts'] if 'C91' in p['designators'])
        for note in ('Available order quantity 0; not reserved',
                     'Available order quantity 616; not reserved'):
            p['sourcing_note']=note
            _,procurement,_=build_bom(self.source,1,registry)
            row=next(r for r in procurement if r['Designator']=='C91,C92')
            self.assertEqual(row['Installed_total'],2)
            self.assertIn('TBD',row['Purchase_quantity'])
            self.assertIn('allocation',row['Sourcing_status'])
            self.assertIn('pending',row['Sourcing_status'])
            self.assertEqual(row['Note'],note)
        p['jlc_match_status']='unconfirmed'
        self.assertIn('UNCONFIRMED',sourcing_status(p))
        p['lcsc']=''
        self.assertIn('MANUAL SOURCING REQUIRED',sourcing_status(p))


if __name__=='__main__':unittest.main()
