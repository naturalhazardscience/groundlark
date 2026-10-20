"""Read-only DC sheet/barrel model of the filled native board.

Four-neighbour square finite differences; no thermal or field-solver claim.
Pad/via interiors are idealized solid copper. Barrel plating is an explicit
minimum process assumption. Mesh refinement and an uncertainty reserve are
required; connector/contact resistance remains a separate measured quantity.
"""
import math
from pathlib import Path
from stackup import block_span


def stackup(path):
    import sexpdata as sx
    text=Path(path).read_text(encoding='utf-8');a,z=block_span(text,'(stackup')
    rows=sx.loads(text[a:z]);layers=[];depth=0.
    for row in rows[1:]:
        if not isinstance(row,list) or str(row[0])!='layer':continue
        fields={str(x[0]):x[1] for x in row[2:] if isinstance(x,list) and len(x)>1}
        name=str(row[1]);thickness=float(fields.get('thickness',0))
        if name.endswith('.Cu'):
            layers.append(dict(name=name,thickness_mm=thickness,center_mm=depth+thickness/2))
        elif name.startswith('dielectric ') and layers:
            layers[-1]['dielectric_to_next_mm']=thickness
            layers[-1]['dielectric_er']=float(fields['epsilon_r'])
        if name.endswith('.Cu') or name.startswith('dielectric '):depth+=thickness
    if len(layers)!=6 or any(x['thickness_mm']<=0 for x in layers):
        raise ValueError('DC extraction requires the recorded six-layer copper stack')
    return layers


def resistivity(temperature_c):
    if not math.isfinite(temperature_c) or not -40<=temperature_c<=125:
        raise ValueError('Copper temperature outside modeled range')
    return 1.724e-5*(1+.00393*(temperature_c-20))  # ohm mm


def network_resistance(count,a,b,conductance,sources,sinks):
    """Solve a connected passive network with unit terminal voltage."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import spsolve
    a,b,g=map(np.asarray,(a,b,conductance));sources=np.unique(sources);sinks=np.unique(sinks)
    if not len(sources) or not len(sinks) or np.intersect1d(sources,sinks).size:
        raise ValueError('Missing or shorted extraction terminals')
    if np.any(~np.isfinite(g)) or np.any(g<=0):raise ValueError('Invalid conductance')
    adjacency=coo_matrix((np.ones(2*len(a)),(np.r_[a,b],np.r_[b,a])),shape=(count,count)).tocsr()
    _,component=connected_components(adjacency)
    active=np.isin(component,component[sources])
    if not active[sinks].all():raise ValueError('Disconnected copper extraction terminal')
    # Sources and sinks may include multiple contact cells; external terminal
    # tying joins them. Omit floating islands, never ground them artificially.
    fixed=np.zeros(count,dtype=bool);fixed[sources]=True;fixed[sinks]=True
    voltage=np.zeros(count);voltage[sources]=1;free=np.where(active&~fixed)[0]
    matrix=coo_matrix((np.r_[g,g,-g,-g],(np.r_[a,b,a,b],np.r_[a,b,b,a])),shape=(count,count)).tocsr()
    voltage[free]=spsolve(matrix[free][:,free],-(matrix@voltage)[free])
    current=(matrix@voltage)[sources].sum()
    if not math.isfinite(current) or current<=0:raise ValueError('DC solve did not converge')
    return 1/float(current)


def extract(board,net,sources,sinks,stack,grid_mm=.1,temperature_c=85,plating_mm=.020):
    import pcbnew as p
    import numpy as np
    from PIL import Image,ImageDraw
    if not .025<=grid_mm<=.2 or plating_mm<=0:raise ValueError('Invalid copper mesh/process parameters')
    layers=[board.GetLayerID(row['name']) for row in stack]
    rho=resistivity(temperature_c)
    box=board.GetBoardEdgesBoundingBox();origin=(p.ToMM(box.GetLeft()),p.ToMM(box.GetTop()))
    width=math.ceil(p.ToMM(box.GetWidth())/grid_mm);height=math.ceil(p.ToMM(box.GetHeight())/grid_mm)
    def xy(v):return ((p.ToMM(v.x)-origin[0])/grid_mm-.5,(p.ToMM(v.y)-origin[1])/grid_mm-.5)
    def polygon(draw,shape):
        for i in range(shape.OutlineCount()):
            ring=shape.COutline(i)
            draw.polygon([xy(ring.CPoint(j)) for j in range(ring.PointCount())],fill=1)
            for h in range(shape.HoleCount(i)):
                hole=shape.CHole(i,h)
                draw.polygon([xy(hole.CPoint(j)) for j in range(hole.PointCount())],fill=0)
    images=[Image.new('1',(width,height)) for _ in layers];draws=[ImageDraw.Draw(im) for im in images]
    for zone in board.Zones():
        if zone.GetNetname()==net and not zone.GetIsRuleArea():
            for i,layer in enumerate(layers):
                if zone.IsOnLayer(layer):polygon(draws[i],zone.GetFilledPolysList(layer))
    footprints={f.GetReference():f for f in board.GetFootprints()}
    pads=[pad for f in footprints.values() for pad in f.Pads()]
    objects=[t for t in board.GetTracks() if t.GetNetname()==net]+[q for q in pads if q.GetNetname()==net]
    for obj in objects:
        for i,layer in enumerate(layers):
            if obj.IsOnLayer(layer):
                shape=p.SHAPE_POLY_SET();obj.TransformShapeToPolygon(shape,layer,0,p.FromMM(.005),p.ERROR_INSIDE)
                polygon(draws[i],shape)
    mask=np.stack([np.asarray(im) for im in images]);ids=np.full(mask.shape,-1,dtype=np.int32)
    count=int(mask.sum());ids[mask]=np.arange(count);aa=[];bb=[];gg=[]
    def edges(a,b,g):
        a=np.asarray(a).ravel();b=np.asarray(b).ravel();valid=(a>=0)&(b>=0)&(a!=b)
        aa.extend(a[valid]);bb.extend(b[valid]);gg.extend(np.broadcast_to(g,a.shape)[valid])
    for i,row in enumerate(stack):
        conductance=row['thickness_mm']/rho
        edges(ids[i,:,:-1],ids[i,:,1:],conductance);edges(ids[i,:-1,:],ids[i,1:,:],conductance)
    for obj in objects:
        via=isinstance(obj,p.PCB_VIA)
        if not via and (not isinstance(obj,p.PAD) or obj.GetAttribute()!=p.PAD_ATTRIB_PTH):continue
        x,y=map(round,xy(obj.GetPosition()))
        if not 0<=x<width or not 0<=y<height:raise ValueError('Barrel outside board mesh')
        drill=p.ToMM(obj.GetDrillValue() if via else min(obj.GetDrillSize()))
        for i in range(len(layers)-1):
            if obj.IsOnLayer(layers[i]) and obj.IsOnLayer(layers[i+1]):
                length=stack[i+1]['center_mm']-stack[i]['center_mm']
                edges([ids[i,y,x]],[ids[i+1,y,x]],math.pi*drill*plating_mm/(rho*length))
    def terminal(refs):
        cells=[]
        for ref,number in refs:
            pad=next(q for q in footprints[ref].Pads() if q.GetNumber()==str(number))
            if pad.GetNetname()!=net:raise ValueError(f'Terminal {ref}.{number} is not on {net}')
            for i,layer in enumerate(layers):
                if not pad.IsOnLayer(layer):continue
                im=Image.new('1',(width,height));draw=ImageDraw.Draw(im);shape=p.SHAPE_POLY_SET()
                pad.TransformShapeToPolygon(shape,layer,0,p.FromMM(.005),p.ERROR_INSIDE);polygon(draw,shape)
                cells.extend(ids[i,np.asarray(im)].tolist())
        return np.unique([n for n in cells if n>=0])
    result=network_resistance(count,aa,bb,gg,terminal(sources),terminal(sinks))
    return dict(net=net,resistance_ohm=result,grid_mm=grid_mm,nodes=count,
                conductor_temperature_C=temperature_c,barrel_plating_mm=plating_mm)


def pi_loop(board,path,grid_mm=.1):
    stack=stackup(path)
    paths=[('PI_RAW_5V',[('U132',7),('U132',8)],[('U133',1),('U133',2),('U133',3)]),
           ('PI_5V',[('U133',9),('U133',10)],[('J1',2),('J1',4)]),
           ('GND',[('U132',15)],[('J1',n) for n in (6,9,14,20,25,30,34,39)])]
    rows=[extract(board,net,start,end,stack,grid_mm) for net,start,end in paths]
    nominal=sum(row['resistance_ohm'] for row in rows)
    # Reserve for discretization, via/land spreading and process variation.
    # This is an allocation, not a statistically established confidence bound.
    conservative=nominal*1.20
    if conservative>.035:raise ValueError(f'Pi copper estimate plus 20% reserve exceeds 35 mOhm: {conservative:.6f} ohm')
    return dict(paths=rows,estimated_copper_loop_ohm=nominal,model_reserve_fraction=.20,
                copper_with_reserve_ohm=conservative,remaining_of_50mohm_for_contacts=.050-conservative,
                contacts_measured=False,thermal_qualified=False,
                method='DC finite-difference native filled copper at 85 C; idealized pad/via interiors; 20 um barrel plating')


def fpga_loop(board,path,grid_mm=.1):
    stack=stackup(path)
    power=[('J80',n) for n in (2,4,6,14,16)]+[('J81',n) for n in (1,3,5,7)]
    ground=[(f.GetReference(),q.GetNumber()) for f in board.GetFootprints()
            if f.GetReference() in ('J80','J81','J82') for q in f.Pads() if q.GetNetname()=='GND']
    rows=[extract(board,'FPGA_VIN',[('U80',7),('U80',8)],power,stack,grid_mm),
          extract(board,'GND',[('U80',15)],ground,stack,grid_mm)]
    copper=sum(row['resistance_ohm'] for row in rows)*1.20
    if copper>.010:raise ValueError(f'FPGA copper plus reserve exceeds 10 mOhm: {copper:.6f} ohm')
    return dict(paths=rows,copper_with_reserve_ohm=copper,model_reserve_fraction=.20,
                contact_allocation_ohm=.005,contacts_measured=False,thermal_qualified=False)
