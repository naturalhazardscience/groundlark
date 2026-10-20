"""Independent MAX-M10S pin and SMA drawing fixtures; no RF qualification."""
from hardware_require import require as _require_hardware
from collections import Counter
import math

PINS={('U21',str(n)):net for n,net in {
    1:'GND',4:'GNSS_PPS',5:'GND',7:'PI_3V3',8:'PI_3V3',10:'GND',
    11:'GNSS_RF',12:'GND',16:'PI_I2C_SDA',17:'PI_I2C_SCL'}.items()}
PINS.update({('J1','18'):'GNSS_PPS',('J140','1'):'GNSS_ANT',('J140','2'):'GND',
    ('C148','1'):'GNSS_ANT',('C148','2'):'GNSS_MATCH',
    ('L141','1'):'GNSS_MATCH',('L141','2'):'GNSS_RF',
    ('L140','1'):'GNSS_BIAS',('L140','2'):'GNSS_ANT',
    ('D140','1'):'GNSS_ANT',('D140','2'):'GND',
    ('U140','1'):'PI_5V',('U140','2'):'GND',('U140','5'):'GNSS_LDO',
    ('U141','1'):'GNSS_LDO',('U141','2'):'GND',('U141','3'):'GNSS_LDO',
    ('U141','5'):'GNSS_LDO',('U141','6'):'GNSS_BIAS',
    ('U43','1'):'SENS_3V3',('U43','2'):'I2C_SDA',('U43','3'):'I2C_SCL',
    ('U43','6'):'PI_I2C_SCL',('U43','7'):'PI_I2C_SDA',('U43','8'):'PI_3V3',
    ('C48','1'):'SENS_3V3',('C49','1'):'PI_3V3'})
NC=[('U21',str(n)) for n in (2,3,6,9,13,14,15,18)]+[('U140','3'),('U140','4'),('U141','4')]
for ref,net in [('C146','PI_3V3'),('C147','PI_3V3'),('C149','PI_5V'),('C150','GNSS_LDO'),('C151','GNSS_BIAS'),('C152','GNSS_LDO')]:
    PINS[ref,'1']=net;PINS[ref,'2']='GND'


def verify(pins):
    for key,net in PINS.items():
        if pins.get(key)!=net:raise ValueError(f'GNSS pin mismatch: {key}')
    degree=Counter(pins.values())
    for key in NC:
        if not pins.get(key) or degree[pins[key]]!=1:raise ValueError(f'GNSS no-connect: {key}')
    if degree['GNSS_PPS']!=2:raise ValueError('PPS must connect only U21 and BCM24')
    return len(PINS)


def rf_geometry(board):
    import pcbnew as p
    from copper_resistance import stackup
    from daqhat_01_engineering import microstrip
    stack=stackup(board.GetFileName());outer=stack[-1];reference=stack[-2]
    height=reference['dielectric_to_next_mm'];er=reference['dielectric_er']
    rows=[];paths={}
    fps={f.GetReference():f for f in board.GetFootprints()}
    def position(ref,n):return next(q.GetPosition() for q in fps[ref].Pads() if q.GetNumber()==str(n))
    # Every RF segment is assigned to a physical branch. Do not silently drop
    # bias/ESD stubs or sum a branched net as if it were a single series line.
    endpoints={
        'GNSS_ANT':(position('J140',1),position('C148',1)),
        'GNSS_MATCH':(position('C148',2),position('L141',1)),
        'GNSS_RF':(position('L141',2),position('U21',11)),
        'BIAS':(position('J140',1),position('L140',2)),
        'ESD':(position('J140',1),position('D140',1))}
    layer=board.GetLayerID(reference['name'])
    zones=[z for z in board.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(layer) and not z.GetIsRuleArea()]
    planes=[z.GetFilledPolysList(layer) for z in zones]
    if not planes:raise ValueError('GNSS RF reference plane missing')
    center=position('J140',1)
    signal_pad=next(q for q in fps['J140'].Pads() if q.GetNumber()=='1')
    # Bound the intentional PTH antipad using authored geometry, not an
    # arbitrary exemption around the connector. Do not let a larger clearance
    # silently enlarge the accepted unreferenced launch.
    clearance=max(p.ToMM(signal_pad.GetOwnClearance(layer)),max(p.ToMM(z.GetLocalClearance()) for z in zones))
    if clearance>.2 or signal_pad.GetShape()!=p.PAD_SHAPE_CIRCLE:
        raise ValueError('GNSS SMA antipad geometry changed')
    error=p.ToMM(board.GetDesignSettings().m_MaxError)
    if error>.005:raise ValueError('GNSS reference polygon accuracy changed')
    antipad=p.ToMM(signal_pad.GetSize().x)/2+clearance+4*error
    if antipad>1.12+1e-9:raise ValueError('GNSS SMA antipad too large')
    # Check the surrounding return plane even for branches wholly inside the
    # antipad. A short unreferenced branch is reported explicitly below.
    annulus_checks=0
    for radial in range(11):
        radius=antipad+.005+radial*.02
        for degree in range(0,360,2):
            angle=math.radians(degree)
            v=center+p.VECTOR2I(p.FromMM(radius*math.cos(angle)),p.FromMM(radius*math.sin(angle)))
            if not any(poly.Contains(v) for poly in planes):raise ValueError('GNSS SMA return annulus void')
            annulus_checks+=1
    for track in board.GetTracks():
        if track.GetNetname() not in ('GNSS_RF','GNSS_ANT','GNSS_MATCH'):continue
        if isinstance(track,p.PCB_VIA) or track.GetLayer()!=p.B_Cu:raise ValueError('RF path changes layers')
        pair=(track.GetStart(),track.GetEnd())
        close=lambda a,b:p.ToMM((a-b).EuclideanNorm())<.001
        roles=[role for role,(a,b) in endpoints.items()
               if (close(pair[0],a) and close(pair[1],b)) or (close(pair[0],b) and close(pair[1],a))]
        if len(roles)!=1 or roles[0] in paths:raise ValueError('Unmodeled RF branch or segment')
        role=roles[0];paths[role]=p.ToMM(track.GetLength())
        width=p.ToMM(track.GetWidth());impedance,_=microstrip(width,height,outer['thickness_mm'],er)
        if not 47.5<=impedance<=52.5:raise ValueError(f'GNSS native RF geometry is {impedance:.2f} ohm')
        a,z=track.GetStart(),track.GetEnd()
        samples=max(1,math.ceil(paths[role]/.025));checked=0;inside=0
        dx=p.ToMM(z.x-a.x);dy=p.ToMM(z.y-a.y)
        normal=(-dy/paths[role],dx/paths[role])
        for j in range(samples+1):
            for side in (-.5,0,.5):
                v=p.VECTOR2I(round(a.x+(z.x-a.x)*j/samples)+p.FromMM(normal[0]*width*side),
                             round(a.y+(z.y-a.y)*j/samples)+p.FromMM(normal[1]*width*side))
                if p.ToMM((center-v).EuclideanNorm())<=antipad:
                    inside+=1;continue
                checked+=1
                if not any(poly.Contains(v) for poly in planes):raise ValueError('GNSS RF reference plane void')
        launch=min(paths[role],antipad) if role in ('GNSS_ANT','BIAS','ESD') else 0
        rows.append(dict(net=track.GetNetname(),role=role,width_mm=width,length_mm=paths[role],estimated_ohm=impedance,
                         reference_samples_checked=checked,antipad_samples=inside,unreferenced_launch_mm=launch,
                         fully_inside_antipad=checked==0))
    if set(paths)!=set(endpoints):raise ValueError('GNSS RF branch missing')
    if max(paths['BIAS'],paths['ESD'])>1.5:raise ValueError('GNSS shunt branch too long')
    return dict(tracks=rows,path_lengths_mm=paths,dielectric_mm=height,copper_mm=outer['thickness_mm'],epsilon_r=er,
                sma_antipad_radius_mm=antipad,sma_return_annulus_samples=annulus_checks,
                reference_sampling_pitch_mm=.025,
                model='Uncoated Hammerstad-Jensen microstrip; mask, coplanar copper and pads require supplier field-solver review',qualified=False)


def verify_board(board):
    import pcbnew as p
    fps={f.GetReference():f for f in board.GetFootprints()}
    pins={(f.GetReference(),q.GetNumber()):q.GetNetname() for f in fps.values() for q in f.Pads() if q.GetNumber()}
    checks=verify(pins)
    sma=fps['J140'];xy=lambda q:(p.ToMM(q.x),p.ToMM(q.y))
    _require_hardware((not sma.IsFlipped() and sma.GetOrientationDegrees()%360==0), lambda: ('SMA must face native -X wall'))
    _require_hardware((math.dist(xy(sma.GetPosition()),(54,65.8))<.001), lambda: ('SMA enclosure position'))
    grounds=[]
    for pad in sma.Pads():
        local=(p.ToMM(pad.GetPosition().x)-54,p.ToMM(pad.GetPosition().y)-65.8)
        if pad.GetNumber()=='1':
            _require_hardware((math.hypot(*local)<.001 and abs(p.ToMM(pad.GetDrillSize().x)-1.2)<.001), lambda: ('gnss_checks.py:45: hardware validation condition'))
        else:
            grounds.append(tuple(round(x,2) for x in local))
            _require_hardware((abs(p.ToMM(pad.GetDrillSize().x)-1.5)<.001), lambda: ('gnss_checks.py:48: hardware validation condition'))
    _require_hardware((set(grounds)=={(-2.55,-2.55),(-2.55,2.55),(2.55,-2.55),(2.55,2.55)}), lambda: ('SMA drawing pad pitch'))
    _require_hardware((fps['U21'].IsFlipped()), lambda: ('GNSS underside clearance'))
    _require_hardware((fps['U21'].GetValue()=='MAX-M10S-00B'), lambda: ('gnss_checks.py:51: hardware validation condition'))
    _require_hardware((fps['D140'].GetValue()=='PESD5V0F1BL'), lambda: ('gnss_checks.py:52: hardware validation condition'))
    rf=[t for t in board.GetTracks() if t.GetNetname()=='GNSS_RF']
    _require_hardware((rf and all(not isinstance(t,p.PCB_VIA) and t.GetLayer()==p.B_Cu for t in rf)), lambda: ('RF path must stay on B.Cu'))
    _require_hardware((sum(p.ToMM(t.GetLength()) for t in rf)<3), lambda: ('RF input stub too long'))
    # TI TPS2553 DBV top-view terminal drawing: FAULT=4, ILIM=5.
    limiter=fps['U141'];_require_hardware((not limiter.IsFlipped() and limiter.GetOrientationDegrees()%360==0), lambda: ('gnss_checks.py:57: hardware validation condition'))
    _require_hardware((limiter.GetValue()=='TPS2553'), lambda: ('gnss_checks.py:58: hardware validation condition'))
    for number,(x,y) in {'1':(-1.1375,-.95),'2':(-1.1375,0),'3':(-1.1375,.95),
                         '4':(1.1375,.95),'5':(1.1375,0),'6':(1.1375,-.95)}.items():
        q=next(q for q in limiter.Pads() if q.GetNumber()==number)
        pos=q.GetPosition()-limiter.GetPosition()
        _require_hardware((math.dist(xy(pos),(x,y))<.001), lambda: ('TPS2553 DBV numbered pads'))
    from imu_layout import Copper
    def pad(ref,num):return next(q for q in fps[ref].Pads() if q.GetNumber()==str(num))
    _require_hardware((fps['C151'].GetValue()=='10n' and not fps['C151'].IsDNP()), lambda: ('gnss_checks.py:66: hardware validation condition'))
    _require_hardware((fps['C152'].GetValue()=='100n' and not fps['C152'].IsDNP()), lambda: ('gnss_checks.py:67: hardware validation condition'))
    bypass=Copper(board,'GNSS_BIAS').between(pad('L140',1),pad('C151',1))
    _require_hardware((bypass<=2), lambda: ('L140 RF bypass must be local'))
    input_bypass=Copper(board,'GNSS_LDO').between(pad('U141',1),pad('C152',1))
    _require_hardware((input_bypass<=6), lambda: ('TPS2553 input bypass path too long'))
    layer=board.GetLayerID('In1.Cu')
    planes=[z.GetFilledPolysList(layer) for z in board.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(layer)]
    stitches=[t.GetPosition() for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND'
              and t.IsOnLayer(layer) and any(poly.Contains(t.GetPosition()) for poly in planes)]
    ground_path=Copper(board,'GND').to_stitch(pad('C151',2),stitches)
    _require_hardware((ground_path<=2), lambda: ('C151 ground return must reach a local connected plane stitch'))
    return dict(pin_checks=checks,deliberate_no_connects=len(NC),pps_bcm=24,
        antenna='3.3 V active SMA, <=20 mA; 50 ohm connector',sample_timing_qualified=False,
        sustained_short_limit_mA=[50,100],choke_rated_mA=340,choke_derated_at_125C_mA=170,
        rf_bypass_path_mm=bypass,rf_bypass_ground_path_mm=ground_path,input_bypass_path_mm=input_bypass,
        rf_geometry=rf_geometry(board),
        host_bus_low_margin_scenario=dict(host_rail_minimum_assumed_V=3.135,input_low_fraction=.2,
            isolator_output_low_maximum_assumed_V=.4,calculated_V=3.135*.2-.4,
            measured=False,note='Static datasheet allocation; actual rail, sink current and bus waveforms require qualification'),
        rf_qualified=False,receiver_peak_allocation_mA=100,antenna_allocation_mA=20)
