"""Reproduce successive BOM/rotation fixes without any local release archive.

Real KiCad export and native DRC run against read-only CAD; every generated
file lives in a temporary directory. The prior-upload faults are independent
fixtures from the reported supplier failures, not output of the fit solver.
"""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from jlcpcb_package import export, sha, write_csv
from jlcpcb_bom_overlay import bundle_overlay, read_csv
from jlcpcb_placement_overlay import export_placement_overlay


class AssemblyExportIntegrationTests(unittest.TestCase):
    def test_full_export_and_overlay_recover_combined_inventory_rotation_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=root/'prior'; overlay=root/'corrected'
            export(base,1)
            expected={name:(base/name).read_bytes() for name in ('BOM-review.csv','CPL-review.csv')}
            manifest=json.loads((base/'manifest.json').read_text())
            # A reviewed procurement update intentionally changes this hash;
            # source CAD hashes must still match, as tested separately.
            manifest['source_sha256']['hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-parts.json']='0'*64
            (base/'manifest.json').write_text(json.dumps(manifest))
            # Simulate a previously uploaded BOM with the old unavailable choices.
            bom=read_csv(base/'BOM-review.csv')
            for row in bom:
                if row['Designator']=='J1':
                    row.update(Comment='ESQ-120-23-G-D',MPN='ESQ-120-23-G-D',
                               Manufacturer='Samtec',**{'JLCPCB Part #':'C21390538'})
                if row['Designator']=='C91,C92':
                    row.update(Comment='C0603C102J5GACTU',MPN='C0603C102J5GACTU',
                               **{'JLCPCB Part #':'C2181873'})
            write_csv(base/'BOM-review.csv',list(bom[0]),bom)
            rows=read_csv(base/'CPL-review.csv')
            old_angles={'J1':90,'J4':0,'JP1':90,'JP80':90,'JP81':90,'J80':0,'J81':0,'J82':90,
                        'U1':0,'U22':0,'U41':0,'U42':0,'U100':0,'U101':0,'U102':0,'U103':0,
                        'Q1':0,'U40':0,'U51':0,'U52':0,'D90':0}
            for row in rows:
                if row['Designator'] in old_angles:
                    row['Rotation']=f'{old_angles[row["Designator"]]:.6f}'
            write_csv(base/'CPL-review.csv',list(rows[0]),rows)
            names=['manifest.json','BOM-review.csv','CPL-review.csv','DAQHAT-01-Gerbers-REVIEW.zip']
            before={name:sha(base/name) for name in names}
            (base/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in before.items()))
            report=export_placement_overlay(base,overlay)
            for name,data in expected.items():
                self.assertEqual((overlay/name).read_bytes(),data,name)
            self.assertEqual({name:sha(base/name) for name in names},before)
            self.assertEqual(report['physical_placements'],189)
            self.assertEqual(report['BOM_lines'],71)
            self.assertEqual(report['catalog_fitted_components'],137)
            self.assertEqual(report['pads_checked'],713)
            self.assertEqual(len(report['unverified_placements']),52)
            self.assertFalse(manifest['supplier_placement_complete'])
            self.assertEqual(len(manifest['unverified_placements']),52)
            self.assertEqual({a['reference'] for a in report['placement_changes']},set(old_angles))
            self.assertIn('Unverified supplier-footprint exceptions',(overlay/'README.md').read_text())
            self.assertIn('C7499354',(overlay/'README.md').read_text())
            self.assertIn('C140950',(overlay/'README.md').read_text())
            purchase=read_csv(overlay/'procurement.csv')
            self.assertEqual(sum(int(r['Installed_total']) for r in purchase),189)
            self.assertTrue(all(r['Requested_HATs']=='1' for r in purchase))
            bundle_overlay(overlay,name='assembly.zip')
            with zipfile.ZipFile(overlay/'assembly.zip') as archive:
                self.assertIsNone(archive.testzip())
                for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                    digest,name=line.split('  ',1)
                    self.assertEqual(digest,sha(overlay/name))
                    self.assertEqual(archive.read(name),(overlay/name).read_bytes())
            self.assertEqual(report['unchanged_Gerber_ZIP_sha256'],before[names[-1]])


if __name__=='__main__':unittest.main()
