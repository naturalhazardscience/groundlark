"""Supplier orientation regressions and bad-data fault injection; read-only CAD."""
import copy
import csv
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from jlcpcb_placement import ROOT, fit_pads, supplier_pads, correct_placements, load_mappings, board_geometry
from jlcpcb_bom import build_bom


class RigidFitTests(unittest.TestCase):
    source=[('1',-2,1),('2',2,1),('3',1,-1)]

    def test_all_quadrants_and_translation(self):
        for degrees in (0,37,90,180,270,359):
            c,s=math.cos(math.radians(degrees)),math.sin(math.radians(degrees))
            target=[(n,12+c*x-s*y,-20+s*x+c*y) for n,x,y in self.source]
            with self.subTest(degrees=degrees):
                result=fit_pads(self.source,target)
                self.assertAlmostEqual(result['rotation_deg'],degrees)
                self.assertAlmostEqual(result['x_mm'],12)
                self.assertAlmostEqual(result['y_up_mm'],-20)

    def test_wrong_pitch_scale_mirror_and_pin_swap_rejected(self):
        bad=[[(n,2*x,2*y) for n,x,y in self.source],
             [(n,-x,y) for n,x,y in self.source],
             [('2',-2,1),('1',2,1),('3',1,-1)]]
        for target in bad:
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'pad fit'):
                fit_pads(self.source,target)

    def test_missing_extra_and_duplicate_contacts_rejected(self):
        for target in (self.source[:-1],self.source+self.source[:1],[('1',-2,1),('1',2,1),('3',1,-1)]):
            with self.assertRaisesRegex(ValueError,'identities or counts'):
                fit_pads(self.source,target)

    def test_nonfinite_or_degenerate_geometry_rejected(self):
        for pads in ([('1',0,0),('2',0,0)],[('1',float('nan'),0),('2',1,0)]):
            with self.assertRaises(ValueError): fit_pads(pads,pads)

    def test_both_common_ground_mounts_checked(self):
        pads=self.source+[('S',-5,0),('S',5,0)]
        self.assertEqual(fit_pads(pads,pads)['pads_checked'],5)
        wrong=self.source+[('S',-6,0),('S',6,0)]
        with self.assertRaisesRegex(ValueError,'pad fit'): fit_pads(pads,wrong)

    def test_two_pin_polarity_is_not_180_degree_ambiguous(self):
        source=[('1',-1.27,0),('2',1.27,0)]
        result=fit_pads(source,[('2',-1.27,0),('1',1.27,0)])
        self.assertEqual(result['rotation_deg'],180)


class NativeConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew as p
        cls.path=ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'
        cls.board_bytes=cls.path.read_bytes()
        cls.geometry=board_geometry(p.LoadBoard(str(cls.path)))
        with cls.path.with_name('bom.csv').open(newline='') as stream:
            _,_,cls.selections=build_bom(list(csv.DictReader(stream)),1)
        cls.mappings=load_mappings()
        cls.placements=[dict(Designator=g['reference'],MidX=f"{g['footprint_origin_mm'][0]:.6f}mm",MidY=f"{-g['footprint_origin_mm'][1]:.6f}mm",
                             Rotation=f"{g['rotation_deg']:.6f}",Layer=g['side'])
                        for g in cls.geometry if g['reference'] in cls.selections]

    def solve(self, placements=None, geometry=None, selections=None):
        return correct_placements(self.placements if placements is None else placements,
                                  self.geometry if geometry is None else geometry,
                                  self.selections if selections is None else selections,self.mappings)

    def test_actual_connectors_and_supplier_pin_one(self):
        rows,audit=self.solve(); lookup={r['Designator']:r for r in rows}
        expected={'J1':0,'J4':270,'JP1':0,'JP80':0,'JP81':0,'JP130':0,'J80':180,'J81':180,'J82':270,'J90':0}
        self.assertEqual(sum('pads_checked' in a and a['reference'] in expected for a in audit),10)
        for ref,angle in expected.items():
            self.assertEqual(float(lookup[ref]['Rotation']),angle,ref)
            entry=next(e for e in self.mappings['footprints'] if ref in e['designators'])
            _,x,y=next(a for a in supplier_pads(entry) if a[0]=='1')
            r=lookup[ref];c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
            pin=next(a for g in self.geometry if g['reference']==ref for a in g['pads'] if a['number']=='1')
            self.assertAlmostEqual(float(r['MidX'][:-2])+c*x-s*y,pin['xy_mm'][0],places=3)
            self.assertAlmostEqual(float(r['MidY'][:-2])+s*x+c*y,-pin['xy_mm'][1],places=3)
        self.assertEqual(self.path.read_bytes(),self.board_bytes)

    def test_horizontal_j90_corrects_old_rotation_and_preserves_polarity(self):
        rows=copy.deepcopy(self.placements)
        next(r for r in rows if r['Designator']=='J90')['Rotation']='180.000000'
        corrected,audit=self.solve(placements=rows)
        row=next(r for r in corrected if r['Designator']=='J90')
        self.assertEqual(float(row['Rotation']),0)
        pads=next(g['pads'] for g in self.geometry if g['reference']=='J90')
        for number,x in [('1',60.38),('2',64.19),('3',68.0)]:
            xy=next(p['xy_mm'] for p in pads if p['number']==number)
            self.assertAlmostEqual(xy[0],x);self.assertAlmostEqual(xy[1],100.9)
        entry=next(a for a in audit if a['reference']=='J90')
        self.assertEqual((entry['mpn'],entry['lcsc']),('1803280','C480530'))
        self.assertLess(entry['max_pad_error_mm'],1e-6)

    def test_only_mapped_components_change_and_inputs_not_mutated(self):
        original=copy.deepcopy(self.placements)
        rows,_=self.solve()
        mapped={r for e in self.mappings['footprints'] for r in e['designators']}
        self.assertEqual(self.placements,original)
        for before,after in zip(original,rows):
            if before['Designator'] not in mapped: self.assertEqual(before,after)

    def test_idempotent_no_double_rotation(self):
        first,_=self.solve(); second,_=self.solve(placements=first)
        self.assertEqual(first,second)

    def test_catalog_or_native_footprint_change_rejected(self):
        for key in ('mpn','lcsc','source_footprint'):
            selections=copy.deepcopy(self.selections);selections['J4'][key]='changed'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Stale supplier'):
                self.solve(selections=selections)

    def test_bottom_side_not_silently_mirrored(self):
        rows=copy.deepcopy(self.placements)
        next(r for r in rows if r['Designator']=='J4')['Layer']='Bottom'
        with self.assertRaisesRegex(ValueError,'bottom-side'): self.solve(placements=rows)

    def test_j1_old_ninety_degree_axis_is_corrected_and_centre_stays(self):
        rows=copy.deepcopy(self.placements)
        old=next(r for r in rows if r['Designator']=='J1')
        old.update(MidX='82.510000mm',MidY='-53.499999mm',Rotation='90.000000')
        result,audit=self.solve(placements=rows)
        new=next(r for r in result if r['Designator']=='J1')
        self.assertEqual(new,dict(old,Rotation='0.000000'))
        self.assertEqual(new['Layer'],'Bottom')
        evidence=next(a for a in audit if a['reference']=='J1')
        self.assertEqual(evidence['pads_checked'],40)
        self.assertLess(evidence['max_pad_error_mm'],.000001)
        self.assertIn('bottom-side model/pin-1 preview required',evidence['status'])
        # Independent axis check: old 90 degrees makes the 48.26mm row
        # vertical, missing the physical horizontal hole array by ~24mm.
        pads=next(g['pads'] for g in self.geometry if g['reference']=='J1')
        xs=[a['xy_mm'][0] for a in pads]; ys=[a['xy_mm'][1] for a in pads]
        self.assertAlmostEqual(max(xs)-min(xs),48.26)
        self.assertAlmostEqual(max(ys)-min(ys),2.54)
        self.assertGreater(abs(48.26*math.sin(math.radians(float(old['Rotation'])))),48)
        self.assertEqual(48.26*math.sin(math.radians(float(new['Rotation']))),0)

    def test_j1_requires_explicit_bottom_basis_and_selected_socket_identity(self):
        for key in ('bottom_basis','bottom_projection'):
            mappings=copy.deepcopy(self.mappings)
            next(e for e in mappings['footprints'] if e['designators']==['J1']).pop(key)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'bottom-side projection'):
                correct_placements(self.placements,self.geometry,self.selections,mappings)
        selections=copy.deepcopy(self.selections);selections['J1']['lcsc']='C21390538'
        with self.assertRaisesRegex(ValueError,'Stale supplier placement identity: J1'):
            self.solve(selections=selections)

    def test_j1_cannot_move_to_top_or_mirror_board_coordinates(self):
        rows=copy.deepcopy(self.placements)
        next(r for r in rows if r['Designator']=='J1')['Layer']='Top'
        with self.assertRaisesRegex(ValueError,'side'): self.solve(placements=rows)
        geometry=copy.deepcopy(self.geometry)
        for a in next(g['pads'] for g in geometry if g['reference']=='J1'):
            a['xy_mm'][0]=165.02-a['xy_mm'][0]
        with self.assertRaisesRegex(ValueError,'pad fit'): self.solve(geometry=geometry)

    def test_missing_connector_rejected(self):
        rows=[r for r in self.placements if r['Designator']!='J4']
        with self.assertRaisesRegex(ValueError,'missing'): self.solve(placements=rows)

    def test_one_moved_mount_rejected(self):
        geometry=copy.deepcopy(self.geometry)
        g=next(g for g in geometry if g['reference']=='J80')
        next(a for a in g['pads'] if a['number']=='101')['xy_mm'][0]+=.1
        with self.assertRaisesRegex(ValueError,'pad fit'): self.solve(geometry=geometry)

    def test_all_bom_placements_have_mapping_or_explicit_exception(self):
        result,audit=self.solve()
        self.assertEqual(len(result),188)
        self.assertEqual(sum('pads_checked' in a for a in audit),136)
        missing={a['reference'] for a in audit if 'pads_checked' not in a}
        self.assertEqual(len(missing),52)
        self.assertTrue({'J83','F80','U23','U11','U12','U13'} <= missing)
        # A complete review inventory is deliberately not a release approval.
        from jlcpcb_placement import require_verified_placements
        with self.assertRaisesRegex(ValueError,'52 unverified supplier placements'):
            require_verified_placements(audit)
        extra=dict(self.placements[0],Designator='U999')
        with self.assertRaisesRegex(ValueError,'coverage'):self.solve(placements=self.placements+[extra])

    def test_known_ic_rotation_regressions_and_unchanged_devices(self):
        result,audit=self.solve();rows={r['Designator']:r for r in result}
        expected={'D90':90,'Q1':180,'U1':270,'U22':270,'U40':180,'U41':270,'U42':270,
                  'U51':180,'U52':180,'U100':270,'U101':270,'U102':270,'U103':270,
                  'U11':0,'U12':0,'U13':0,'U43':0,'U104':0,'U105':0,'U106':0}
        for ref,angle in expected.items():
            with self.subTest(ref=ref):
                self.assertEqual(float(rows[ref]['Rotation']),angle)
                g=next(g for g in self.geometry if g['reference']==ref)
                self.assertEqual(rows[ref]['Layer'],g['side'])
                self.assertAlmostEqual(float(rows[ref]['MidX'][:-2]),g['footprint_origin_mm'][0])
                self.assertAlmostEqual(float(rows[ref]['MidY'][:-2]),-g['footprint_origin_mm'][1])
        u102=next(a for a in audit if a['reference']=='U102')
        self.assertEqual(u102['coordinate_projection'],'mirror_local_x_then_ccw')
        self.assertEqual(u102['pads_checked'],16)
        self.assertGreater(u102['min_pad_overlap_fraction'],.98)

    def test_wrong_ic_pin_order_and_displaced_pad_are_rejected(self):
        for fault in ('pin_swap','pad_shift'):
            geometry=copy.deepcopy(self.geometry)
            pads=next(g['pads'] for g in geometry if g['reference']=='U102')
            first=next(p for p in pads if p['number']=='1')
            if fault=='pin_swap':
                other=next(p for p in pads if p['number']=='9')
                first['number'],other['number']='9','1'
            else:first['xy_mm'][1]+=1
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'No SMT orientation'):
                self.solve(geometry=geometry)

    def test_bottom_ic_cannot_use_top_chirality(self):
        mappings=copy.deepcopy(self.mappings);geometry=copy.deepcopy(self.geometry);rows=copy.deepcopy(self.placements)
        entry=next(e for e in mappings['footprints'] if 'U102' in e['designators']);entry['side']='Top'
        next(g for g in geometry if g['reference']=='U102')['side']='Top'
        next(r for r in rows if r['Designator']=='U102')['Layer']='Top'
        with self.assertRaisesRegex(ValueError,'No SMT orientation'):
            correct_placements(rows,geometry,self.selections,mappings)

    def test_nonpolar_passives_keep_native_axis_without_spurious_half_turns(self):
        result,_=self.solve();rows={r['Designator']:r for r in result}
        for g in self.geometry:
            ref=g['reference']
            if ref in rows and ref[0] in 'RCF':
                self.assertEqual(float(rows[ref]['Rotation']),g['rotation_deg'],ref)

    def test_regulator_tab_alias_is_required_and_both_output_lands_checked(self):
        result,audit=self.solve()
        self.assertEqual(next(a['pads_checked'] for a in audit if a['reference']=='U40'),4)
        mapping=copy.deepcopy(self.mappings)
        next(e for e in mapping['footprints'] if 'U40' in e['designators'])['pad_aliases']={}
        with self.assertRaisesRegex(ValueError,'identities or counts'):
            correct_placements(self.placements,self.geometry,self.selections,mapping)

    def test_replacement_capacitor_mapping_rejects_wrong_part(self):
        selections=copy.deepcopy(self.selections);selections['C91']['lcsc']='C123'
        with self.assertRaisesRegex(ValueError,'Stale supplier placement identity'):self.solve(selections=selections)

    def test_replacement_capacitors_have_exact_catalog_pad_checks(self):
        rows,audit=self.solve()
        for ref in ('C91','C92'):
            a=next(a for a in audit if a['reference']==ref)
            self.assertEqual(a['lcsc'],'C140950')
            self.assertEqual(a['mpn'],'C0603C102J5GAC7867')
            self.assertEqual(a['pads_checked'],2)
            self.assertGreater(a['min_pad_overlap_fraction'],.95)
            row=next(r for r in rows if r['Designator']==ref)
            self.assertEqual((row['Layer'],row['Rotation']),('Top','0.000000'))

    def test_export_summary_does_not_keep_stale_missing_capacitor_warning(self):
        from jlcpcb_placement_overlay import exception_summary
        _,audit=self.solve()
        self.assertIn('Unverified supplier-footprint exceptions',exception_summary(audit))
        self.assertIn('U23',exception_summary(audit))
        self.assertNotIn('C91',exception_summary(audit))
        self.assertIn('C91',exception_summary([dict(reference='C91')]))

    def test_duplicate_mapping_cannot_silently_override_reviewed_identity(self):
        mappings=copy.deepcopy(self.mappings)
        mappings['footprints'].append(copy.deepcopy(mappings['footprints'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate placement mapping'):
            correct_placements(self.placements,self.geometry,self.selections,mappings)

    def test_smt_nonfinite_or_nonpositive_geometry_fails_closed(self):
        for value in (float('nan'),float('inf'),0,-1):
            geometry=copy.deepcopy(self.geometry)
            pad=next(g for g in geometry if g['reference']=='C91')['pads'][0]
            pad['size_mm'][0]=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Invalid SMT geometry'):
                self.solve(geometry=geometry)
        geometry=copy.deepcopy(self.geometry)
        next(g for g in geometry if g['reference']=='C91')['footprint_origin_mm'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'Invalid SMT geometry'):
            self.solve(geometry=geometry)

    def test_mapping_exception_is_bound_to_exact_part(self):
        mappings=copy.deepcopy(self.mappings)
        entry=next(e for e in mappings['footprints'] if 'C91' in e['designators'])
        mappings['footprints'].remove(entry)
        mappings['unverified']+=[dict(designators=['C91','C92'],mpn=entry['mpn'],lcsc=entry['lcsc'],
            source_footprint=self.selections['C91']['source_footprint'],reason='Explicit review fixture')]
        rows,audit=correct_placements(self.placements,self.geometry,self.selections,mappings)
        self.assertEqual({a['reference'] for a in audit if 'pads_checked' not in a},
                         {'C91','C92'} | {r for e in self.mappings['unverified'] for r in e['designators']})
        selections=copy.deepcopy(self.selections);selections['C92']['lcsc']='C123'
        with self.assertRaisesRegex(ValueError,'Stale placement exception'):
            correct_placements(rows,self.geometry,selections,mappings)


if __name__=='__main__': unittest.main()
