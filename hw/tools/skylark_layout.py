"""Place the Skylark compiled circuit and export an unrouted DSN.

Explicit authoring command: never run as a validation step. Connectivity comes
only from atopile. It replaces this product's routed board, not other products.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
import collections, csv, json
import pcbnew as p
from project_paths import ROOT, board_dir, compiled_dir, load_layout
from kicad_support import v, add_shape, add_text, unique_ids, save_board
from assemble_pcb import export_dsn
from silkscreen import add_logo

NAME = 'skylark-usb'

def main():
    spec = load_layout(NAME)[NAME]
    folder = board_dir(NAME)
    folder.mkdir(parents=True, exist_ok=True)
    b = p.LoadBoard(str(compiled_dir('skylark')/'skylark.kicad_pcb'))
    _require_hardware(({f.GetReference() for f in b.GetFootprints()} == {x['ref'] for x in spec['parts'] if not x['ref'].startswith('H')}), lambda: ('Build the authored circuit first'))
    b.SetCopperLayerCount(4)
    for item in [*b.GetTracks(), *b.GetDrawings(), *b.Zones()]:
        b.Delete(item)
    old = {f.GetReference(): f for f in b.GetFootprints()}
    parts = []
    library = ROOT/'hw/shared/elec/skylark'
    for entry in spec['parts']:
        meta = dict(entry)
        ref = meta['ref']
        source = old.get(ref)
        pins = {x.GetNumber(): x.GetNet() for x in source.Pads() if x.GetNumber()} if source else {}
        fp = p.FootprintLoad(str(library), Path(meta['local_fp']).stem)
        _require_hardware((fp), lambda: (meta['local_fp']))
        _require_hardware(({x.GetNumber() for x in fp.Pads() if x.GetNumber()} == set(pins)), lambda: (ref))
        fp.SetReference(ref)
        fp.SetValue(meta['value'])
        fp.SetFPID(p.LIB_ID('Skylark', Path(meta['local_fp']).stem))
        b.Add(fp)
        for pad in fp.Pads():
            if pad.GetNumber():
                pad.SetNet(pins[pad.GetNumber()])
        if source:
            b.Delete(source)
        fp.SetPosition(v(50+meta['xy'][0], 50+meta['xy'][1]))
        if meta['side'] == 'back':
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(meta['angle'])
        fp.Reference().SetLayer(p.B_Fab if fp.IsFlipped() else p.F_Fab)
        fp.Reference().SetTextSize(v(.8,.8))
        fp.Value().SetVisible(False)
        fp.Models().clear()
        meta['pins'] = {x.GetNumber(): x.GetNetname() for x in fp.Pads() if x.GetNumber()}
        parts.append(meta)
    # Bottom-edge open slot leaves a 9 mm wide environmental-sensor finger.
    outline = [(0,0),(90,0),(90,100),(81,100),(81,88),(80,88),(80,100),(0,100)]
    for a,c in zip(outline, outline[1:]+outline[:1]):
        add_shape(b,50+a[0],50+a[1],50+c[0],50+c[1],p.Edge_Cuts,.05)
    # Inner layers are return planes. Keep all copper off the temperature
    # finger except its four narrow top-layer connections and local bypass.
    for layer in (p.In1_Cu,p.In2_Cu):
        z=p.ZONE(b);z.SetLayer(layer);z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(False)
        z.SetDoNotAllowCopperPour(False);z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False);z.Outline().NewOutline()
        for x,y in [(50,50),(140,50),(140,150),(50,150)]:z.Outline().Append(v(x,y))
        b.Add(z)
    for layer in (p.In1_Cu,p.In2_Cu,p.B_Cu):
        z=p.ZONE(b);z.SetLayer(layer);z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True);z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False);z.Outline().NewOutline()
        for x,y in [(131,139),(140,139),(140,150),(131,150)]:z.Outline().Append(v(x,y))
        b.Add(z)
    for text,x,y,size in [('SKYLARK USB',45,10,2),('REV A / ENGINEERING PROTOTYPE',45,14,1),('SO2',24,47,1.2),('H2S',66,47,1.2),('USB',25,85,1),('PMS5003',73,97.5,1),('AIR',85,98.5,.8)]:
        add_text(b,text,50+x,50+y,size)
    add_logo(b, center=(95,54.5))
    ds=b.GetDesignSettings()
    ds.m_CopperEdgeClearance=p.FromMM(.3)
    ds.m_MinClearance=p.FromMM(.15)
    ds.m_TrackMinWidth=p.FromMM(.15)
    ds.m_ViasMinSize=p.FromMM(.6)
    ds.m_MinThroughDrill=p.FromMM(.3)
    title=p.TITLE_BLOCK();title.SetTitle('Skylark USB environmental monitor')
    title.SetRevision('A PROTOTYPE');title.SetDate('2026-09-26');b.SetTitleBlock(title)
    path=folder/(NAME+'.kicad_pcb')
    unique_ids(b);save_board(str(path),b)
    project={'meta':{'filename':NAME+'.kicad_pro','version':1},
      'board':{'design_settings':{'rules':{'min_clearance':.15,'min_track_width':.15,'min_via_diameter':.6,'min_through_hole_diameter':.3,'min_copper_edge_clearance':.3}}},
      'net_settings':{'classes':[{'name':'Default','clearance':.15,'track_width':.15,'via_diameter':.6,'via_drill':.3,'diff_pair_width':.2,'diff_pair_gap':.2}],'meta':{'version':3}}}
    path.with_suffix('.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
    (folder/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Skylark") (type "KiCad") (uri "${KIPRJMOD}/../../../shared/elec/skylark") (options "") (descr "Skylark atomic footprints")))\n')
    (folder/'electrical.json').write_text(json.dumps({'source':'atopile compiled PCB; do not edit','size_mm':spec['size'],'copper_layers':4,'ground_layers':spec['ground_layers'],'fabrication':spec['fabrication'],'parts':parts},indent=2)+'\n')
    with (folder/'bom.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['Reference','Value','MPN','Footprint','DNP','Note'])
        for x in parts:w.writerow([x[k] for k in ['ref','value','mpn','local_fp','dnp','note']])
        w.writerow(['GS1/GS2 sockets (8)','1 mm cell sockets','0322-0-15-15-34-27-10-0','SGX7_AQ_Socket',False,'Install sockets before inserting cells'])
        w.writerow(['External PM module','PMS5003','PMS5003','Enclosure cradle',False,'Separate cable, not soldered on this PCB'])
    from stackup import apply_stackup
    apply_stackup(path,spec)
    export_dsn(b,folder/(NAME+'.dsn'),(.6,.3),spec['ground_layers'])
    print(NAME,len(parts),'placed parts; routing must be rerun explicitly')

if __name__ == '__main__':
    main()
