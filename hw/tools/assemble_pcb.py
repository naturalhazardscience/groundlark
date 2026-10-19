"""Place atopile's compiled KiCad footprints; never reconstruct electrical nets.

Each product's layout/placement.json contains mechanical placement/BOM presentation only. Connectivity
is read exclusively from the compiled .ato board. Derived schematics are for
review; electrical changes must be made in hw/<product>/elec/*.ato and rebuilt.
"""
from pathlib import Path
from project_paths import board_dir, compiled_dir, load_layout
import json,csv,re,types,shutil,sys,sexpdata as sx
from kicad_support import save_board
import pcbnew as p
from kicad_support import add_shape,add_text,schematic,uid,v,unique_ids
from restore_keepouts import restore
from silkscreen import add_logo, MODEL_CENTER
ROOT=Path(__file__).resolve().parents[2]

def export_dsn(b,path,signal_via_mm=(.6,.3),ground_layers=None,track_mm=.15,clearance_mm=.15):
    layers=b.GetCopperLayerCount()
    ground_layers=ground_layers or ['In1.Cu',f'In{layers-2}.Cu']
    # Model the same GND planes that import_routes fills in the native board.
    # Without plane records the router wastes signal layers joining every GND pad.
    temporary=[];box=b.GetBoardEdgesBoundingBox()
    for layer in [b.GetLayerID(name) for name in ground_layers]:
        if any(not z.GetIsRuleArea() and z.GetLayer()==layer and z.GetNetname()=='GND' for z in b.Zones()):continue
        z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.GetNetsByName()['GND']);z.Outline().NewOutline()
        x0,y0=p.ToMM(box.GetLeft())+.4,p.ToMM(box.GetTop())+.4
        x1,y1=p.ToMM(box.GetRight())-.4,p.ToMM(box.GetBottom())-.4
        for x,y in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]:z.Outline().Append(v(x,y))
        b.Add(z);temporary.append(z)
    try:p.ExportSpecctraDSN(b,str(path))
    finally:
        for z in temporary:b.Delete(z)
    data=path.read_text()
    for layer in ground_layers:
        data=data.replace(f'(layer {layer}\n      (type signal)',f'(layer {layer}\n      (type power)')
        data=re.sub(r'    \(wire_keepout "" \(polygon '+re.escape(layer)+r'[^)]*\)\)\n','',data)
    width=round(track_mm*1000);clearance=round(clearance_mm*1000)
    data=data.replace('(width 200)',f'(width {width})').replace('(clearance 200.1',f'(clearance {clearance+.1}')
    data=data.replace('(clearance 200)', f'(clearance {clearance})')
    # Specctra treats brackets as part of bare names; sexpdata treats them
    # as list delimiters. Preserve these tokens losslessly while editing.
    tree=sx.loads(data.replace('(string_quote ")','(string_quote quote)').replace('[','__LB__').replace(']','__RB__'))
    network=next(x for x in tree if isinstance(x,list) and str(x[0])=='network')
    default=next(x for x in network if isinstance(x,list) and str(x[0])=='class')
    power=[x for x in default[2:] if not isinstance(x,list) and str(x) in {'PI_5V','PI_3V3','SENS_3V3','EXT_3V3','EXT_12V','FUSED_12V','PROTECTED_12V','FPGA_VIN','FPGA_3V3','USB_VBUS','USB_5V','V3_SENSOR','V3'}]
    default[:]=[x for x in default if isinstance(x,list) or x not in power]
    # Fine escapes route first; widen_power.py subsequently retains wider
    # power copper wherever actual KiCad DRC allows it.
    network.append([sx.Symbol('class'),'Power',*power,[sx.Symbol('circuit'),[sx.Symbol('use_via'),f'Via[0-{layers-1}]_600:300_um']],[sx.Symbol('rule'),[sx.Symbol('width'),width],[sx.Symbol('clearance'),clearance]]])
    if tuple(signal_via_mm)!=(.6,.3):
        import copy
        diameter,drill=[round(x*1000) for x in signal_via_mm]
        assert diameter>=450 and drill>=200 and diameter-drill>=150
        library=next(x for x in tree if isinstance(x,list) and str(x[0])=='library')
        name=f'Via__LB__0-{layers-1}__RB___{diameter}:{drill}_um'
        if not any(isinstance(x,list) and str(x[0])=='padstack' and str(x[1])==name for x in library):
            original=next(x for x in library if isinstance(x,list) and str(x[0])=='padstack' and '600:300' in str(x[1]))
            stack=copy.deepcopy(original);stack[1]=name
            for x in stack:
                if isinstance(x,list) and str(x[0])=='shape':x[1][2]=diameter
            library.append(stack)
        structure=next(x for x in tree if isinstance(x,list) and str(x[0])=='structure')
        via=next(x for x in structure if isinstance(x,list) and str(x[0])=='via')
        if name not in map(str,via):via.append(name)
        default.append([sx.Symbol('circuit'),[sx.Symbol('use_via'),name]])
    path.write_text(sx.dumps(tree).replace('(string_quote quote)','(string_quote ")').replace('__LB__','[').replace('__RB__',']'))

def main():
    names = ('groundlark-daqhat-01',) if '--trenz' in sys.argv else ('groundlark-field-head',)
    for name,spec in load_layout(*names).items():
        if len(sys.argv)>1 and '--trenz' not in sys.argv and name not in sys.argv[1:]:continue
        target=spec.get('target','field_head')
        ishat=target=='trenz_hat'
        folder=board_dir(name);folder.mkdir(parents=True,exist_ok=True)
        b=p.LoadBoard(str(compiled_dir(target)/(target+'.kicad_pcb')))
        assert b.GetFootprints(),'Run ato build first'
        layers=spec.get('copper_layers',6 if ishat else 4)
        ground_layers=spec.get('ground_layers',['In1.Cu',f'In{layers-2}.Cu'])
        assert layers in (4,6,8),layers
        b.SetCopperLayerCount(layers)
        signal_via=spec.get('signal_via_mm',[.6,.3])
        fab=spec.get('fabrication',{});track_mm=fab.get('min_track_mm',.15);clearance_mm=fab.get('min_clearance_mm',.15)
        ds=b.GetDesignSettings();ds.m_CopperEdgeClearance=p.FromMM(.3);ds.m_MinClearance=p.FromMM(.15);ds.m_TrackMinWidth=p.FromMM(.15);ds.m_ViasMinSize=p.FromMM(signal_via[0]);ds.m_MinThroughDrill=p.FromMM(signal_via[1])
        ds.m_MinClearance=p.FromMM(clearance_mm);ds.m_TrackMinWidth=p.FromMM(track_mm)
        for obj in list(b.GetTracks()):b.Delete(obj)
        for obj in list(b.GetDrawings()):b.Delete(obj)
        for i in range(b.GetAreaCount()-1,-1,-1):b.Delete(b.GetArea(i))
        fps={f.GetReference():f for f in b.GetFootprints()}
        parts=[]
        for meta in spec['parts']:
            meta=dict(meta);typ=meta.pop('type');ref=meta['ref']
            if ref not in fps:
                assert not typ,('Missing compiled component',ref)
                fp=p.FootprintLoad(str(ROOT/'hw/shared/elec'),meta['local_fp']);fp.SetReference(ref);b.Add(fp)
            else:fp=fps[ref]
            if (target=='field_head' and ref=='J1') or meta['local_fp'].startswith(('PWR_', 'SUP_')) or meta['local_fp']=='Groundlark__SDP32':
                # Restore the complete manufacturer footprint geometry after
                # compiler conversion, retaining each compiled physical pin net.
                old=fp;pin_nets={pad.GetNumber():pad.GetNet() for pad in old.Pads() if pad.GetNumber()}
                fp=p.FootprintLoad(str(ROOT/'hw/shared/elec'),meta['local_fp'])
                assert {pad.GetNumber() for pad in fp.Pads() if pad.GetNumber()}==set(pin_nets)
                fp.SetReference(ref);b.Add(fp)
                for pad in fp.Pads():
                    if pad.GetNumber():pad.SetNet(pin_nets[pad.GetNumber()])
                b.Delete(old)
            fp.SetPosition(v(50+meta['xy'][0],50+meta['xy'][1]))
            side=meta.get('side','front');assert side in ('front','back'),side
            if fp.IsFlipped() != (side=='back'):fp.Flip(fp.GetPosition(),False)
            fp.SetOrientationDegrees(meta['angle'])
            fp.SetValue(meta['value']);fp.SetDNP(meta['dnp'])
            fp.Reference().SetVisible(True);fp.Reference().SetTextSize(v(.8,.8));fp.Reference().SetTextThickness(p.FromMM(.12));fp.Reference().SetPosition(v(50+meta['xy'][0],46.5+meta['xy'][1]));fp.Reference().SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T))
            fp.Reference().SetLayer(p.B_Fab if fp.IsFlipped() else p.F_Fab)
            fp.Value().SetVisible(False)
            # Set native schematic linkage for the derived review schematic.
            fp.SetPath(p.KIID_PATH('/'+uid(name)+'/'+uid(name+'/'+meta['section'])+'/'+uid(name+'/'+ref)))
            fp.SetFPID(p.LIB_ID('Groundlark',meta['local_fp']))
            pads={pad.GetNumber():pad.GetNetname() or None for pad in fp.Pads() if pad.GetNumber()}
            # Atopile creates unique singleton nets for intentionally open pins.
            meta['pins']=pads
            parts.append(types.SimpleNamespace(**meta))
        w,h=spec['size']
        for a,c in [((0,0),(w,0)),((w,0),(w,h)),((w,h),(0,h)),((0,h),(0,0))]:add_shape(b,50+a[0],50+a[1],50+c[0],50+c[1],p.Edge_Cuts,.05)
        for layer in [b.GetLayerID(name) for name in ground_layers]:
            z=p.ZONE(b);z.SetLayer(layer);z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(False);z.SetDoNotAllowCopperPour(False);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.Outline().NewOutline()
            for x,y in [(50,50),(50+w,50),(50+w,50+h),(50,50+h)]:z.Outline().Append(v(x,y))
            b.Add(z)
        if ishat:
            z=p.ZONE(b);z.SetLayer(p.F_Cu);z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowCopperPour(True);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.Outline().NewOutline()
            tiltbox=[(92.2,73.7),(97.8,73.7),(97.8,82.3),(92.2,82.3)]
            for x,y in tiltbox:z.Outline().Append(v(x,y))
            if any(part.ref == "U20" for part in parts): b.Add(z)
            # Raised module envelope on assembly layer. Components beneath must
            # clear the 3mm mating stack; no tall parts under this rectangle.
            outline=[(30,8),(80,8),(80,48),(30,48)]
            for a,c in zip(outline,outline[1:]+outline[:1]):add_shape(b,50+a[0],50+a[1],50+c[0],50+c[1],p.Dwgs_User,.12)
            if target=='trenz_hat':
                add_text(b,'Groundlark DAQHAT-01 / 200T',*MODEL_CENTER,.8)
                add_logo(b)
                add_text(b,'12V DC / CENTER +',145,102,.8)
                add_text(b,'FPGA ON/OFF',155,65,.8)
                add_text(b,'FPGA POWER',146,93,.9)
                add_text(b,'PI BAT 8-18V',183,54,.8)
                add_text(b,'+    GND',167.9,64,.8)
        else:
            add_text(b,'4x RM3100 / XYZ',83,53,.8)
        title=p.TITLE_BLOCK();title.SetTitle(name+' / atopile prototype');title.SetRevision('DAQHAT-01 6L' if target=='trenz_hat' else spec['silkscreen']['revision']);title.SetDate('2026-09-25' if target=='trenz_hat' else '2026-10-12');b.SetTitleBlock(title)
        if target == 'field_head':
            from burrowlark_silkscreen import apply
            apply(b, spec)
        restore(b)
        if target=='trenz_hat':
            for fp in b.GetFootprints():
                for zone in fp.Zones():
                    if fp.GetReference() != 'U23':zone.SetLayerSet(p.LSET.AllCuMask())
        # Stock models are resolved by KiCad 9. Portable custom models are added
        # by hw/tools/models.py after routing, without changing connectivity.
        path=folder/(name+'.kicad_pcb');unique_ids(b);save_board(str(path),b)
        lib=ROOT/'hw/shared/libraries'/'Groundlark.pretty';lib.mkdir(exist_ok=True)
        for fpfile in (ROOT/'hw/shared/elec').glob('*.kicad_mod'):shutil.copyfile(fpfile,lib/fpfile.name)
        derived={'size':spec['size'],'parts':parts};schematic(name,derived,folder)
        for sch in folder.glob('*.kicad_sch'):
            s=sch.read_text().replace('A0 DRAFT',('A2' if ishat else spec['silkscreen']['revision'])+' PROTOTYPE').replace('Engineering draft - module interface and fabrication release on hold.','Atopile-derived circuit review schematic - prototype, not released.')
            sch.write_text(s)
        (folder/'electrical.json').write_text(json.dumps({'source':'atopile compiled PCB; do not edit','size_mm':spec['size'],'copper_layers':layers,'ground_layers':ground_layers,'stackup':spec.get('stackup'),'fabrication':fab,'parts':[vars(x) for x in parts]},indent=2))
        with open(folder/'bom.csv','w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['Reference','Value','MPN','Footprint','DNP','Note'])
            for x in parts:writer.writerow([x.ref,x.value,x.mpn,x.local_fp,x.dnp,x.note])
        (folder/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Groundlark") (type "KiCad") (uri "${KIPRJMOD}/../../../shared/libraries/Groundlark.pretty") (options "") (descr "Atopile atomic parts")))')
        project={'meta':{'filename':name+'.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.15,'min_track_width':.15,'min_via_diameter':signal_via[0],'min_through_hole_diameter':signal_via[1],'min_copper_edge_clearance':.3,'min_microvia_diameter':.3,'min_microvia_drill':.1}}},'net_settings':{'classes':[{'name':'Default','clearance':.15,'track_width':.15,'via_diameter':signal_via[0],'via_drill':signal_via[1],'microvia_diameter':.3,'microvia_drill':.1,'diff_pair_width':.2,'diff_pair_gap':.2,'diff_pair_via_gap':.25}],'meta':{'version':3}}}
        project['board']['design_settings']['rules'].update(fab.get('rules',{}))
        project['net_settings']['classes'][0].update(clearance=clearance_mm,track_width=track_mm)
        (folder/(name+'.kicad_pro')).write_text(json.dumps(project,indent=2))
        if fab.get('custom_rules'):
            (folder/(name+'.kicad_dru')).write_text(fab['custom_rules'],encoding='utf8')
        from stackup import apply_stackup
        apply_stackup(path,spec)
        export_dsn(b,folder/(name+'.dsn'),signal_via,ground_layers,track_mm,clearance_mm)
        print(name,len(parts),'placed compiled parts')

if __name__=='__main__':main()
