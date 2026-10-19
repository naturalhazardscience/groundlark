"""Export assembly selections against an unchanged, previously reviewed PCB.

The overlay replaces BOM/procurement data only. It copies placement data and
records the base Gerber ZIP hash; it never edits CAD or clears release holds.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import zipfile
from jlcpcb_bom import ROOT, REGISTRY, build_bom, check_upload_roundtrip
from jlcpcb_package import BOARD, BOARD_DIR, check_reference_sets, sha, write_csv, write_json


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def verify_base_files(base):
    expected=dict(line.split('  ',1)[::-1] for line in (base/'SHA256SUMS.txt').read_text().splitlines() if line)
    for name in ['manifest.json','BOM-review.csv','CPL-review.csv','DAQHAT-01-Gerbers-REVIEW.zip']:
        if expected.get(name)!=sha(base/name):
            raise ValueError(f'Base-package checksum mismatch: {name}')


def export_overlay(base, out):
    if out.exists():
        raise ValueError('Use a new output directory; preserve previous packages')
    verify_base_files(base)
    manifest=json.loads((base/'manifest.json').read_text())
    # Verify every original validated design input, not the old procurement
    # registry: changing reviewed assembly selections is the purpose of this tool.
    for name, expected in manifest['source_sha256'].items():
        if name != REGISTRY.relative_to(ROOT).as_posix() and sha(ROOT/name) != expected:
            raise ValueError(f'Stale base-package design input: {name}')
    source=read_csv(BOARD_DIR/'bom.csv')
    bom, procurement, selections=build_bom(source,1)
    cpl=read_csv(base/'CPL-review.csv')
    check_reference_sets(bom,cpl)
    old={ref:r for r in read_csv(base/'BOM-review.csv') for ref in r['Designator'].split(',')}
    new={ref:r for r in bom for ref in r['Designator'].split(',')}
    if set(old)!=set(new):
        raise ValueError('BOM-only overlay cannot add/remove placements')
    if next(r for r in cpl if r['Designator']=='J1')['Layer']!='Bottom':
        raise ValueError('J1 must remain bottom-mounted')
    changes={ref:{k:dict(before=old[ref][k],after=new[ref][k]) for k in new[ref]
                  if old[ref][k]!=new[ref][k]} for ref in new if old[ref]!=new[ref]}
    out.mkdir(parents=True)
    write_csv(out/'BOM-review.csv',list(bom[0]),bom)
    check_upload_roundtrip(out/'BOM-review.csv',bom)
    write_csv(out/'procurement.csv',list(procurement[0]),procurement)
    shutil.copyfile(base/'CPL-review.csv',out/'CPL-review.csv')
    shutil.copyfile(REGISTRY,out/'assembly-selections.json')
    report=dict(status='ASSEMBLY SELECTION REVIEW; NOT MANUFACTURING RELEASE',
        base_package=base.name,requested_assembled_HATs=1,
        BOM_lines=len(bom),physical_placements=len(cpl),changes=changes,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [BOARD,BOARD_DIR/'bom.csv',REGISTRY,Path(__file__),ROOT/'hw/tools/jlcpcb_bom.py']},
        unchanged_CPL_sha256=sha(base/'CPL-review.csv'),
        unchanged_Gerber_ZIP_sha256=sha(base/'DAQHAT-01-Gerbers-REVIEW.zip'),
        sourcing_holds=[f'J1 {selections["J1"]["mpn"]} / {selections["J1"]["lcsc"]}: {selections["J1"]["sourcing_note"]}',
                       'All allocations, placement/process approval and existing engineering holds remain open.'])
    write_json(out/'validation.json',report)
    (out/'README.md').write_text(f'''# DAQHAT-01 assembly selection correction

Upload this BOM-review.csv instead of every previous BOM. CPL-review.csv is
byte-identical to {base.name}/CPL-review.csv. Keep that base package's Gerber ZIP.
This folder is an assembly-data overlay, not a Gerber upload ZIP or fabrication release.

{len(bom)} BOM rows / {len(cpl)} installed components for ONE HAT. No quantities increased.
Website fabrication and assembly quantities remain separate from per-board BOM counts.

Reviewed replacements:
- C42/C80/C81/C82: Samsung CL31A226KAHNNNE, C12891, 22uF 25V X5R +/-10%, 1206.
- C84/C85: Murata GRM21BR71C475KE51L, C408144, 4.7uF 16V X7R +/-10%, 0805.
- C90: Murata GRM31C5C1H104JA01L, C97946, 100nF 50V C0G +/-5%, 1206.
- F80: Littelfuse 0466002.NRHF, C3105, 1206 2A fuse on the 12V input.
- F130: Littelfuse 0466004.NRHF, C187596, 1206 4A fuse on the Pi supply input.
- U23: Sensirion SDP32-125PA-TR-250PCS, C6473035; matching redesigned PCB required.
- U11/U12/U13: ST LSM6DSOXTR, C481766; use the existing mode-1 acquisition subset.
- J1: {selections['J1']['manufacturer']} {selections['J1']['mpn']} / {selections['J1']['lcsc']}.
  {selections['J1']['sourcing_note']}

Stock observations are snapshots, not reservations. No order or account was changed.
See procurement.csv and assembly-selections.json for exact evidence and limitations.
The separate 3A power allocations and <=15mOhm FPGA output-loop target remain.
Physical power/transient, fuse inrush/fault and noise qualification remain open.
''',encoding='utf-8')
    return report


def bundle_overlay(out, name='DAQHAT-01-BOM-CORRECTION.zip'):
    bundle=out/name
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name not in [bundle.name,'SHA256SUMS.txt'])
    checksum=out/'SHA256SUMS.txt'
    checksum.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files))
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files+[checksum]: archive.write(path,path.name)
    with zipfile.ZipFile(bundle) as archive:
        if archive.testzip(): raise ValueError('ZIP integrity failure')
        for path in files:
            if archive.read(path.name)!=path.read_bytes(): raise ValueError('ZIP content mismatch')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(export_overlay(args.base,args.output),indent=2))
    bundle_overlay(args.output)
