"""Exact assembly selections and JLC upload rows; no fuzzy part matching.

The separate procurement registry resolves source placeholders without changing
the validated electrical CAD. Its expected references/value/footprint are guards,
not a replacement for the source BOM. Catalog evidence does not reserve stock.
"""
import csv
import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-parts.json'
UPLOAD_FIELDS = ['Comment', 'Designator', 'Footprint', 'JLCPCB Part #',
                 'Manufacturer', 'MPN', 'Description']


def load_registry(path=REGISTRY):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['schema_version'] != 1:
        raise ValueError('Unsupported assembly registry version')
    return data


def resolve(source, registry=None):
    registry = load_registry() if registry is None else registry
    selections = {}
    codes = {}
    for part in registry['parts']:
        for key in ('mpn', 'manufacturer', 'package', 'evidence_url', 'checked_on'):
            if not part.get(key):
                raise ValueError(f'Missing selection {key}: {part.get("designators")}')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.,/+_-]*', part['mpn']):
            raise ValueError(f'Invalid orderable MPN: {part["mpn"]}')
        code = part['lcsc']
        if code:
            evidence=urlsplit(part['evidence_url'])
            catalog_codes=re.findall(r'(?<![A-Za-z0-9])C[1-9][0-9]*(?![A-Za-z0-9])',unquote(evidence.path))
            if (not re.fullmatch(r'C[1-9][0-9]*', code) or code not in catalog_codes
                    or evidence.scheme != 'https'
                    or evidence.hostname not in ('jlcpcb.com','www.jlcpcb.com','lcsc.com','www.lcsc.com')):
                raise ValueError(f'Invalid catalog evidence: {code}')
            identity = (part['manufacturer'], part['mpn'], part['package'])
            if code in codes and codes[code] != identity:
                raise ValueError(f'Conflicting catalog identity: {code}')
            codes[code] = identity
        elif not part['sourcing_note']:
            raise ValueError('Unmapped catalog part requires an explicit sourcing note')
        for ref in part['designators']:
            if ref in selections:
                raise ValueError(f'Duplicate selection: {ref}')
            selections[ref] = part
    physical = [r for r in source if not re.fullmatch(r'(H|TP)\d+', r['Reference'])]
    if len({r['Reference'] for r in physical}) != len(physical):
        raise ValueError('Duplicate source reference')
    if {r['Reference'] for r in physical} != set(selections):
        raise ValueError('Assembly registry/source reference mismatch')
    for row in physical:
        part = selections[row['Reference']]
        actual = (row['MPN'].removeprefix('Samtec '), row['Value'], row['Footprint'])
        expected = (part['source_mpn'], part['source_value'], part['source_footprint'])
        if actual != expected:
            raise ValueError(f'Stale assembly selection: {row["Reference"]}')
        if row['DNP'] != 'False':
            raise ValueError(f'Unreviewed DNP: {row["Reference"]}')
        # Library names can hide a package mismatch (F80 previously selected
        # a 0603 fuse on a 1206 land pattern). Check recognized chip packages.
        chip = re.search(r'(?:C|R)_(0201|0402|0603|0805|1206|1210)_', row['Footprint'])
        expected_package = '1206' if row['Footprint'] == 'TZ_TZ_FUSE' or re.search(r'Fuse_?1206', row['Footprint']) else (chip[1] if chip else None)
        if expected_package and part['package'] != expected_package:
            raise ValueError(f'Assembly package mismatch: {row["Reference"]}: expected {expected_package}')
        if part['mpn'] != part['source_mpn'] and not part['resolution']:
            raise ValueError(f'Undocumented ordering-code resolution: {row["Reference"]}')
        if part['mpn'] != part['source_mpn'] and not part.get('manufacturer_evidence'):
            raise ValueError(f'Substitution requires manufacturer evidence: {row["Reference"]}')
    return selections


def require_single_hat(quantity):
    """This prototype order is explicitly limited to one fabricated/assembled HAT."""
    if type(quantity) is not int or quantity != 1:
        raise ValueError('This order is for ONE SINGLE HAT; quantity must be exactly 1')


def sourcing_status(part):
    if not part['lcsc']:
        return 'MANUAL SOURCING REQUIRED; do not substitute'
    if part.get('jlc_match_status') == 'unconfirmed':
        return 'Exact LCSC identity; JLCPCB matching UNCONFIRMED; source exact MPN if unavailable'
    if part.get('jlc_match_status') == 'catalog_listed':
        return 'Listed in JLCPCB assembly catalog; order allocation and mechanical/process approval pending'
    return 'Exact catalog identity; allocation and assembly eligibility unconfirmed'


def build_bom(source, quantity, registry=None):
    require_single_hat(quantity)
    registry = load_registry() if registry is None else registry
    selections = resolve(source, registry)
    if registry.get('procurement_policy', {}).get('require_available_stock'):
        required = Counter(part['lcsc'] for part in selections.values())
        for part in registry['parts']:
            stock = part.get('stock_observation', {})
            available = stock.get('available_order_quantity')
            if (stock.get('status') != 'available_to_order'
                    or type(stock.get('minimum_quantity')) is not int
                    or stock['minimum_quantity'] != 1
                    or type(available) is not int or available < required[part['lcsc']]
                    or stock.get('source_url') != part['evidence_url']
                    or not stock.get('checked_at')):
                raise ValueError(f'In-stock / MOQ 1 procurement policy failed: {part["mpn"]}')
    grouped = defaultdict(list)
    for ref, part in selections.items():
        # Same physical component across different schematic functions is one
        # upload row. Original CAD footprints stay in the detailed review file.
        key = (part['manufacturer'], part['mpn'], part['package'], part['lcsc'])
        grouped[key].append(ref)
    bom, procurement = [], []
    sort_ref = lambda s: re.sub(r'\d+', lambda m: m[0].zfill(6), s)
    for (mfr, mpn, package, code), refs in sorted(grouped.items()):
        refs.sort(key=sort_ref)
        parts = [selections[ref] for ref in refs]
        description = '; '.join(sorted({p.get('assembly_description', p['source_value']) for p in parts}))
        # Comment is the exact MPN, not a bare value. The four primary fields
        # remain sufficient even when an importer ignores the extra columns.
        bom.append(dict(zip(UPLOAD_FIELDS, [mpn, ','.join(refs), package, code,
                                           mfr, mpn, description])))
        procurement.append(dict(Designator=','.join(refs), Manufacturer=mfr,
            MPN=mpn, Package=package, Per_HAT=len(refs), Requested_HATs=quantity,
            Installed_total=len(refs)*quantity,
            Purchase_quantity='TBD: MOQ 1 required; confirm assembly attrition / stock allocation',
            **{'JLCPCB Part #': code},
            Catalog_URL=parts[0]['evidence_url'],
            Sourcing_status='; '.join(sorted({sourcing_status(p) for p in parts})),
            Note='; '.join(sorted({p['sourcing_note'] for p in parts if p['sourcing_note']}))))
    return bom, procurement, selections


def check_upload_roundtrip(path, expected):
    """Check actual CSV quoting, column mapping and records after serialization."""
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != UPLOAD_FIELDS or list(reader) != expected:
            raise ValueError('JLCPCB BOM serialization mismatch')
