"""KiCad drawing and review-schematic helpers. No electrical circuit definition."""
from pathlib import Path
import json,math,uuid,tempfile
import pcbnew as pcb
NS=uuid.UUID('7418c0d1-4a75-4f9d-8db1-7c1f7c75a001')
def uid(s): return str(uuid.uuid5(NS,s))
def unique_ids(board):
    # Atomic footprint copies retain child UUIDs. Mutate only duplicate IDs;
    # numeric pins, nets, placements and all copper remain unchanged.
    seen=set()
    for fp in board.GetFootprints():
        for item in [fp,fp.Reference(),fp.Value(),*fp.Pads(),*fp.GraphicalItems()]:
            while item.m_Uuid.AsString() in seen:item.m_Uuid.Increment()
            seen.add(item.m_Uuid.AsString())
    for item in [*board.GetTracks(),*board.GetDrawings(),*board.Zones()]:
        while item.m_Uuid.AsString() in seen:item.m_Uuid.Increment()
        seen.add(item.m_Uuid.AsString())

def save_board(path, board):
    """Atomically replace CAD and leave the checked project rules untouched.

    Saving directly can fail on a Windows-mounted workspace. KiCad also writes
    a standalone .kicad_pro, so isolate that side effect in the temporary tree.
    Never report success or replace existing CAD after a failed serialization.
    """
    target = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix='.kicad-save-', dir=target.parent) as tmp:
        pending = Path(tmp) / target.name
        if not pcb.SaveBoard(str(pending), board):
            raise OSError(f'KiCad could not serialize {target.name}')
        pending.replace(target)
    return True


def q(s): return json.dumps(str(s),ensure_ascii=False)
def v(x,y): return pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y))
def add_shape(board,x1,y1,x2,y2,layer,width=.15):
    line=pcb.PCB_SHAPE();line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(v(x1,y1));line.SetEnd(v(x2,y2));line.SetLayer(layer);line.SetWidth(pcb.FromMM(width));board.Add(line)

def add_text(board,text,x,y,size=1,layer=pcb.F_SilkS):
    t=pcb.PCB_TEXT(board);t.SetText(text);t.SetPosition(v(x,y));t.SetTextSize(v(size,size));t.SetTextThickness(pcb.FromMM(.12));t.SetLayer(layer);board.Add(t)

def pin_type(num,part):
    name=part.names.get(num,'')
    if name in ('VDD','VDDIO','VCC','VCC_IO','V_BCKP','VSS','GND','AVSS','DVSS','DVIO','EMC_GND','VDDA','VDDB','AVDD','DVDD'): return 'power_in'
    if name in ('MISO','SDO'): return 'tri_state'
    if name in ('INT1','TIMEPULSE','DRDY'): return 'output'
    if name in ('SCLK','SCK','CS','CSB','SDI','MOSI','EN','WP','I2C_ADDR'): return 'input'
    return 'passive'

def libsym(part):
    nums=list(part.pins);N=len(nums);half=math.ceil(N/2);height=max(5.08,(half+1)*2.54)
    name='Part_'+part.ref
    pins=[];coords={}
    for i,num in enumerate(nums):
        side=0 if i<half else 1; row=i if side==0 else i-half
        x=-15.24 if not side else 15.24;y=height/2-2.54*(row+1);angle=0 if not side else 180
        coords[num]=(x,-y,side)
        label=part.names.get(num,num)
        pins.append(f'(pin {pin_type(num,part)} line (at {x} {y} {angle}) (length 2.54) (name {q(label)} (effects (font (size 1.0 1.0)))) (number {q(num)} (effects (font (size 1.0 1.0)))))')
    s=f'''(symbol "Groundlark:{name}" (pin_names (offset 0.6)) (in_bom yes) (on_board yes)
      (property "Reference" "{part.ref[0]}" (id 0) (at 0 {height/2+2.54} 0) (effects (font (size 1.27 1.27))))
      (property "Value" {q(part.value)} (id 1) (at 0 {-height/2-2.54} 0) (effects (font (size 1.27 1.27))))
      (symbol "{name}_0_1" (rectangle (start -12.7 {height/2}) (end 12.7 {-height/2}) (stroke (width 0.254) (type default)) (fill (type background))))
      (symbol "{name}_1_1" {' '.join(pins)}))'''
    return s,coords,height

def effects(size=1.0,justify=''): return f'(effects (font (size {size} {size}))'+(f' (justify {justify})' if justify else '')+')'

def schematic(name,spec,folder):
    root=uid(name); sections={s:[] for s in sorted(set(p.section for p in spec['parts']))}
    for part in spec['parts']:
        if part.pins: sections[part.section].append(part)
    rootbody=[];all_libs=[]
    for i,(section,parts) in enumerate(sections.items(),1):
        sid=uid(name+'/'+section);file=section+'.kicad_sch'
        rootbody.append(f'''(sheet (at {30+(i-1)%2*110} {45+(i-1)//2*50}) (size 95 30)
          (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) (uuid {sid})
          (property "Sheetname" {q(section)} (at {30+(i-1)%2*110} {43+(i-1)//2*50} 0) {effects(1.27,'left')})
          (property "Sheetfile" {q(file)} (at {30+(i-1)%2*110} {77+(i-1)//2*50} 0) {effects(1.27,'left')})
          (instances (project {q(name)} (path "/{root}" (page "{i+1}")))))''')
        start_x=50.8 if name=='groundlark-daqhat-01' else 45.72
        libs=[];body=[];x=start_x;y=35.56;row_height=0
        for idx,part in enumerate(parts):
            lib,coords,height=libsym(part);libs.append(lib)
            footprint=('Skylark:'+Path(part.local_fp).stem) if name=='skylark-usb' else ('Groundlark:'+part.local_fp)
            if idx and idx%4==0: x=start_x;y+=row_height+22.86;row_height=0
            row_height=max(row_height,height)
            cy=y+height/2; puid=uid(name+'/'+part.ref)
            body.append(f'''(symbol (lib_id "Groundlark:Part_{part.ref}") (at {x} {cy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp {'yes' if part.dnp else 'no'}) (uuid {puid})
              (property "Reference" {q(part.ref)} (at {x} {y-4} 0) {effects(1.27)})
              (property "Value" {q(part.value)} (at {x} {y-1.5} 0) {effects(1.0)})
              (property "Footprint" {q(footprint)} (at {x} {cy} 0) (effects (font (size 1 1)) hide))
              (property "MPN" {q(part.mpn)} (at {x} {cy} 0) (effects (font (size 1 1)) hide))
              (instances (project {q(name)} (path "/{root}/{sid}" (reference {q(part.ref)}) (unit 1)))))''')
            for num,(px,py,side) in coords.items():
                xx,yy=round(x+px,3),round(cy+py,3);net=part.pins[num]
                if net is None:
                    body.append(f'(no_connect (at {xx} {yy}) (uuid {uid(name+part.ref+num+"nc")}))');continue
                end=round(xx+(-5.08 if not side else 5.08),3)
                body.append(f'(wire (pts (xy {xx} {yy}) (xy {end} {yy})) (stroke (width 0) (type default)) (uuid {uid(name+part.ref+num+"w")}))')
                # Global labels connect across the functional sheets.
                body.append(f'(global_label {q(net)} (shape bidirectional) (at {end} {yy} {0 if side else 180}) {effects(.9,"left" if side else "right")} (uuid {uid(name+part.ref+num+"l")}))')
            x+=96.52
        if i==1:
            lib='(symbol "Groundlark:PWR_FLAG" (pin_names (offset 0)) (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 0 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at 0 0 0) (effects (font (size 1 1)) hide)) (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 -2.54) (xy 1.27 -1.27) (xy 0 0)) (stroke (width 0.1524) (type default)) (fill (type none)))) (symbol "PWR_FLAG_1_1" (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))'
            libs.append(lib)
            rails=['GND','PI_3V3','PI_5V','SENS_3V3','FPGA_3V3'] if name.endswith('-hat') or name=='groundlark-daqhat-01' else ['GND','USB_VBUS','USB_5V','V3','V3_SENSOR']
            # GEO_AVDD is powered through R96; ERC cannot propagate power through a resistor.
            if name=="groundlark-daqhat-01": rails.extend(["GEO_AVDD", "SUP_3V3"])
            if name=='skylark-usb': rails=['GND','USB_VBUS','USB_5V','V3','VA','PM_5V']
            for k,net in enumerate(rails):
                xx=35.56+50.8*k; yy=274.32; reference=f'#FLG{k+1:02d}'
                body.append(f'(symbol (lib_id "Groundlark:PWR_FLAG") (at {xx} {yy} 0) (unit 1) (in_bom no) (on_board no) (uuid {uid(name+reference)}) (property "Reference" "{reference}" (at {xx} {yy} 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at {xx} {yy} 0) (effects (font (size 1 1)) hide)) (instances (project {q(name)} (path "/{root}/{sid}" (reference "{reference}") (unit 1)))))')
                body.append(f'(global_label {q(net)} (shape input) (at {xx} {yy} 0) {effects(1.0,"left")} (uuid {uid(name+reference+"label")}))')
        all_libs.extend(libs)
        revision='DAQHAT-01' if name=='groundlark-daqhat-01' else 'A2 PROTOTYPE'
        date='2026-09-30' if name=='groundlark-daqhat-01' else '2026-09-23'
        if name=='groundlark-field-head': revision,date='B1 PROTOTYPE','2026-10-12'
        if name=='skylark-usb': revision,date='A PROTOTYPE','2026-09-26'
        header=f'(kicad_sch (version 20230121) (generator eeschema) (uuid {sid}) (paper "A3") (title_block (title {q(("Groundlark DAQHAT-01" if name=="groundlark-daqhat-01" else name)+" / "+section)}) (date {q(date)}) (rev {q(revision)}))'
        (folder/file).write_text(header+'\n(lib_symbols\n'+'\n'.join(libs)+')\n'+'\n'.join(body)+'\n)',encoding='utf-8')
    note='Atopile-derived review schematic - prototype, not released.\nThe Pi hosts acquisition; the USB head has a local MCU.\nGlobal net labels connect functional sheets.'
    if name=='groundlark-daqhat-01':
        note='Atopile-derived review schematic - prototype, not released.\nPi sensor acquisition; independent FPGA adapter and configurable TI Pi supervisor.\nMCU firmware and physical power qualification pending. Global labels connect sheets.'
    if name=='skylark-usb':
        note='Atopile-derived review schematic - Skylark USB Rev A prototype, not released.\nPMS5003 / SGX SO2 and H2S / SHT40 / BMP390. Firmware and physical qualification pending.\nGlobal net labels connect functional sheets; raw working and auxiliary electrodes are acquired separately.'
    if name=='groundlark-daqhat-01':
        note='Atopile-derived review schematic - DAQHAT-01 geophone / internal-link prototype, not released.\nPi sensor acquisition; SPI6 / quad wiring, UART and switched Pi JTAG.\nGlobal net labels connect functional sheets.'
    rootbody.append(f'(text {q(note)} (at 30 25 0) {effects(1.5,"left")} (uuid {uid(name+"note")}))')
    (folder/(name+'.kicad_sch')).write_text(f'(kicad_sch (version 20230121) (generator eeschema) (uuid {root}) (paper "A1") (lib_symbols)\n'+'\n'.join(rootbody)+f'\n(sheet_instances (path "/" (page "1"))))',encoding='utf-8')

    external=[symbol.replace('"Groundlark:Part_', '"Part_').replace('"Groundlark:PWR_FLAG"','"PWR_FLAG"') for symbol in all_libs]
    (folder/'Groundlark.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "Groundlark")\n'+'\n'.join(external)+'\n)')
    (folder/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "Groundlark") (type "KiCad") (uri "${KIPRJMOD}/Groundlark.kicad_sym") (options "") (descr "Atopile-derived physical pin maps")))')
