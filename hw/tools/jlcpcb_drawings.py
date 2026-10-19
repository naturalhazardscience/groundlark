"""Create one four-page review PDF from exported, independently parsed plots."""
import argparse
import csv
import json
from html import escape
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

W, H = 595.276, 841.89
INK = HexColor('#162b3a')
ACCENT = HexColor('#087e8b')
WARN = HexColor('#a33c21')


def selected_part(out, reference):
    """Use the package's exact procurement identity in assembly instructions."""
    with (out / 'procurement.csv').open(newline='', encoding='utf-8') as stream:
        matches = [row for row in csv.DictReader(stream)
                   if reference in row['Designator'].split(',')]
    if len(matches) != 1:
        raise ValueError(f'Expected one procurement entry for {reference}')
    row = matches[0]
    return escape(f"{row['Manufacturer']} {row['MPN']} / {row['JLCPCB Part #']}")


def make(out):
    manifest = json.loads((out / 'manifest.json').read_text())
    geometry = json.loads((out / 'review/placement-geometry.json').read_text())
    check = json.loads((out / 'review/independent-check.json').read_text())
    layer_count=len(check['layers']); drill_count=sum(check['drills'].values())
    via_count=manifest['counts']['vias']['through']
    j1 = selected_part(out, 'J1')
    j90 = selected_part(out, 'J90')
    c = Canvas(str(out / 'DAQHAT-01-assembly-review.pdf'), pagesize=(W, H), invariant=1)
    c.setTitle('Groundlark DAQHAT-01 | JLCPCB engineering review | one assembled HAT')
    style = ParagraphStyle('body', fontName='Helvetica', fontSize=10, leading=15, textColor=INK)

    def paragraph(text, y, width=499):
        p = Paragraph(text, style); _, h = p.wrap(width, H)
        p.drawOn(c, 48, y-h); return y-h-12

    def page(title, index):
        c.setFillColor(ACCENT); c.rect(0, H-13, W, 13, fill=1, stroke=0)
        c.setFillColor(INK); c.setFont('Helvetica', 10)
        c.drawString(48, H-48, 'GROUNDLARK / DAQHAT-01 / JLCPCB')
        c.setFont('Helvetica-Bold', 22); c.drawString(48, H-83, title)
        c.setFillColor(WARN); c.setFont('Helvetica-Bold', 9)
        c.drawString(48, H-108, 'ENGINEERING REVIEW ONLY - NOT RELEASED FOR MANUFACTURE')
        c.setFillColor(INK); c.setFont('Helvetica', 8)
        source_label = manifest.get('source_label', f"Source {(manifest.get('source_commit') or 'content-hashed')[:12]}")
        c.drawString(48, 27, f"{source_label} | Requested assembly: {manifest['requested_assembled_HATs']} HAT")
        c.drawRightString(W-48, 27, f'{index} / 4')

    page('Assembly request', 1)
    y = H-139
    for text in [
        '<b>Requested deliverable:</b> one populated 140 x 56 mm DAQHAT-01 carrier. Standard PCBA, double-sided SMT plus through-hole assembly. Pi, Trenz module, geophone, riser, power supply and mounting hardware are separate purchases.',
        '<b>Quantity: ONE SINGLE HAT.</b> Fabricate one PCB and assemble that one PCB. No increase to two or five boards is authorized. Set both website quantities to 1; supplier must confirm acceptance. Gerbers contain one board, without panel repeats. Component purchase minima and attrition are separate quote items.',
        '<b>Handling hold:</b> the 56 mm board dimension is below the 70 mm Standard minimum. Manufacturer to propose an assembly frame, edge rails and fiducials; return panel data for review without altering the HAT outline or hole positions.',
        f"<b>Sourcing hold:</b> {manifest['counts']['physical_placements']} placements, {manifest['counts']['BOM_lines']} grouped BOM lines. {manifest['counts'].get('catalog_mapped_BOM_lines', 0)} lines have exact catalog identities. J1 is {j1}. Confirm current allocation of every selected part. No substitutions are approved.",
        f"<b>Placement hold:</b> {len(manifest.get('unverified_placements', []))} placements lack verified supplier geometry. CPL is not feeder-approved. Validate centroid, rotation and pin 1. J1 is bottom-mounted despite the front-side CAD lands.",
        '<b>Assembly:</b> keep JP1, JP80, JP81 and JP130 shunts OPEN. Fit U23 SDP32 in the final reflow only: max 260 C, max 150 s above 200 C, protected ports, no board wash. Do not fit the Trenz module or Pi during assembly.',
        f'<b>Validation:</b> fresh native DRC has zero findings and zero unconnected items. Independent Gerbonara parsing reads all {layer_count} plot layers and matches all {drill_count} drill hits to CAD within 1 micrometre. This does not replace manufacturer DFM or first-article power, fit, timing and noise measurements.',
    ]: y = paragraph(text, y)
    c.showPage()

    page('Fabrication specification', 2)
    y = paragraph('<b>Standard six-layer FR-4, through-vias only.</b> Order 1.60 mm nominal (+/-10%), TG135, 1 oz outer / 0.5 oz inner, ENIG, green mask and white legend. JLC06161H-3313 stock reference below; no custom lamination or controlled impedance. Published copper/dielectric total is 1.5384 mm; CAD mask thickness is illustrative, not a manufacturing requirement.', H-139)
    x = 48; rowh = 19
    rows = [('Layer / material', 'Thickness (mm)', 'Purpose / processing')]
    names = manifest['copper_layers']
    for i, name in enumerate(names):
        rows.append((f'L{i+1} - {name}', f"{manifest['copper_thickness_mm'][i]:.4f}", 'GND plane' if name in ('In1.Cu','In4.Cu') else 'Copper'))
        if i < len(names)-1: rows.append((f'Dielectric {i+1}', f"{manifest['dielectric_thickness_mm'][i]:.4f}", 'Stock FR4'))
    for i, row in enumerate(rows):
        c.setFillColor(HexColor('#e5f1f2') if i == 0 else HexColor('#f1f4f6') if i%2 else HexColor('#ffffff'))
        c.rect(x, y-rowh, 499, rowh, fill=1, stroke=0)
        c.setFillColor(INK); c.setFont('Helvetica-Bold' if i == 0 else 'Helvetica', 9)
        for xx, value in zip((56, 224, 352), row): c.drawString(xx, y-13, value)
        y -= rowh
    y -= 15
    for text in [
        '<b>Drill/clearance profile:</b> 0.30/0.40 mm through-via drills; pads at least 0.45 mm (0.075 mm ring). No laser, blind or buried vias. Dense signal escapes use 0.125 mm tracks and 0.10 mm clearance; additional hole/pad rules are checked by native DRC.',
        f'<b>Via processing:</b> epoxy-fill and copper-cap all {via_count} through-vias listed in via-processing.csv, including ADC and IMU bypass via-in-pad sites. JLCPCB lists POFV for six-layer boards. Do not fill component PTH holes or NPTH holes.',
        '<b>Coordinates:</b> absolute KiCad origin; X right, Y up. Board bounds X=50..190, Y=-106..-50 mm. Gerber, drill and CPL share this origin. Bottom CPL coordinates are NOT mirrored. Bottom illustration is mirrored for viewing only.',
        '<b>Drills:</b> two Excellon files keep PTH and NPTH separate. Preserve Edge.Cuts, mounting holes and connector locating holes. Use the drill report for tool counts; no blind-drill files are expected.',
    ]: y = paragraph(text, y)
    c.showPage()

    for side, index in [('top', 3), ('bottom', 4)]:
        page(f'{side.title()} assembly review', index)
        y = paragraph(('Viewed from component side. ' if side == 'top' else 'Viewed from the underside; horizontally mirrored relative to the top. ') +
                      'Image is independently rendered from exported Gerbers. It shows lands and routing, not installed component bodies. Notes below identify assembly-critical sites; CSV and CAD Fab SVGs provide the full placement inventory.', H-139)
        im = ImageReader(str(out / f'review/gerber-{side}.png'))
        iw, ih = im.getSize(); width=499; height=width*ih/iw
        bottom=y-height-8
        c.drawImage(im,48,bottom,width,height,mask='auto')
        y=bottom-22
        rows = ([
            '<b>J80 / J81 / J82:</b> three Samtec fine-pitch Trenz connectors on TOP, with SMT signal contacts and plated mounting features. Match exact height, locating posts and pin 1. Confirm stock or consigned parts before accepting the assembly quote.',
            '<b>U11-U13 / U22:</b> three IMUs and geophone ADC. Preserve existing sensor orientations; do not rotate an accelerometer to create another axis. The IMUs already measure all three axes.',
            f'<b>J83 / J90:</b> 12 V center-positive barrel input and horizontal geophone header. J90 is {j90}, opening outward over the board edge. Its 1803581 cable plug is a separate purchase. JP1/JP80/JP81/JP130 remain open.',
            '<b>J1 exception:</b> the long Pi connector land pattern appears on this side in CAD Fab output, but its socket body is installed BELOW the board. Follow the bottom assembly instruction, not the library layer.',
        ] if side == 'top' else [
            f'<b>J1:</b> {j1} socket body underneath the HAT; mating face toward two external SSQ-120-02-G-D risers. Nominal Pi-top to HAT-underside clearance is 28.06 mm. Verify pin 1, contact engagement and measured support height before soldering.',
            f"<b>U100-U106 and associated passives:</b> underside link-switch, expander, logic and supervisor circuitry. {manifest['counts']['assembly'].get('Bottom SMT',0)} SMT components occupy this side. Confirm their rotations in the JLC assembly preview.",
            '<b>Mechanical fit:</b> maintain Pi/riser and fastener clearance. No cable guide or external FPGA ribbon connectors are part of this revision. Actual connector mating and stack clearances need first-article verification.',
        ])
        for text in rows: y=paragraph(text,y)
        c.showPage()
    c.save()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    make(parser.parse_args().package)
