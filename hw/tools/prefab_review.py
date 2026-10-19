"""Read-only pre-fab calculations and routed-board measurements.

Reports model limits explicitly. No CAD mutation, rerouting, or physical PASS.
"""
from pathlib import Path
import csv
import hashlib
import heapq
import itertools
import json
import math

ROOT=Path(__file__).resolve().parents[2]
BOARD=ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01'


def response(hz, f0=4.5, sensitivity=23.4, damping=.7, coil=395,
             series=1000, differential=100e-9, common=1e-9, bias=1e6):
    w=2*math.pi*hz;wn=2*math.pi*f0
    mechanical=(1j*w)**2/((1j*w)**2+2*damping*wn*1j*w+wn**2)
    resistance=coil+2*series
    electrical=1/(1+resistance/(2*bias)+1j*w*resistance*(differential+common/2))
    return sensitivity*mechanical*electrical


def analog_review():
    # All combinations, rather than pairing only low/low and high/high values.
    # The symmetric differential model does not model common-mode mismatch.
    corners=list(itertools.product((4,5),(21.06,25.74),(.63,.77),(375.25,414.75),
                                  (990,1010),(95e-9,105e-9),(.95e-9,1.05e-9),(.99e6,1.01e6)))
    frequencies=(.5,1,4,4.5,5,10,20,40,80,150.1,256_000)
    rows=[]
    for hz in frequencies:
        values=[abs(response(hz,*corner)) for corner in corners]
        rows.append(dict(hz=hz,nominal_v_per_m_s=abs(response(hz)),
                         minimum_v_per_m_s=min(values),maximum_v_per_m_s=max(values)))
    # Thermal noise of the complete passive differential Thevenin resistance.
    # Integrating its one-pole RC across ALL frequencies is conservative for a
    # downstream ADC filter. ADC's typical integrated noise is added separately.
    passive=math.sqrt(1.380649e-23*298.15/(100e-9+.5e-9))
    fmod=256_000
    attenuation=1/math.sqrt(1+(2*math.pi*fmod*2395*100.5e-9)**2)
    period=3116/1_024_000
    # Full-scale common-mode bounds using TI equation 7 (gain >4).
    margins=[]
    for rail,top,bottom,load in itertools.product((3.135,3.465),(9900,10100),(9900,10100),(.0003,.001)):
        avdd=(rail-22*load)/(1+22/(top+bottom))
        vcm=avdd*bottom/(top+bottom)
        limit=.2+.032*(64-4)/8
        margins.append(min(vcm-.016-limit,avdd-limit-(vcm+.016)))
    return dict(corner_count=len(corners),frequency_cases=len(corners)*len(frequencies),response=rows,
        passive_noise_25c_rms_v=passive,adc_typical_rms_v=.50e-6,
        combined_typical_rms_v=math.hypot(passive,.50e-6),
        tvs_opposite_10na_leakage_differential_bound_v=20e-9*395/2,
        tvs_same_direction_10na_common_mode_shift_v=10e-9*(1e6+1000+10000),
        minimum_full_scale_common_mode_margin_v=min(margins),
        nominal_conversion_period_s=period,nominal_actual_sps=1/period,
        oscillator_2pct_sps_range=[.98/period,1.02/period],
        digital_filter=dict(type='vendor linear-phase FIR, one-cycle settling',minus3db_hz=150.1,
            coefficients_available=False,exact_alias_rejection_qualified=False),
        modulator_image=dict(hz=fmod,passive_attenuation_db=20*math.log10(attenuation),
            input_sine_rms_for_0_5uv_output_v=.5e-6/attenuation),
        startup_vcm=dict(nominal_tau_s=.05,maximum_assumed_tau_s=.0606,
            residual_fraction_after_300ms=math.exp(-.3/.0606)),
        limits=['Symmetric RC corners omit coil inductance, parasitics and common-mode conversion',
                'ADC noise is typical, not a guaranteed assembled-board bound',
                'TVS bound assumes specified leakage at its test bias; ADC bias and contamination need measurement',
                'No invented FIR coefficients or quantitative credit for digital stopband rejection',
                'ADC overload recovery is unspecified here; passive settling does not prove ADC recovery'])


def separation(a,b):
    """Distance between axis-aligned XY envelopes, in mm (zero on overlap)."""
    return math.hypot(max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))


def geometry_review(board):
    import pcbnew as p
    fps={f.GetReference():f for f in board.GetFootprints()}
    def xy(v): return [p.ToMM(v.x)-50,p.ToMM(v.y)-50]
    def courtyard(ref):
        points=[xy(v) for g in fps[ref].GraphicalItems() if g.GetLayer() in (p.F_CrtYd,p.B_CrtYd) for v in (g.GetStart(),g.GetEnd())]
        return [min(a[0] for a in points),min(a[1] for a in points),max(a[0] for a in points),max(a[1] for a in points)]
    def pad(ref,num): return next(q for q in fps[ref].Pads() if q.GetNumber()==num)
    def route_length(a,b):
        start,finish=pad(*a),pad(*b);net=start.GetNetname();assert net==finish.GetNetname()
        graph={};positions={}
        def node(v,layer):
            key=(v.x,v.y,layer);positions[key]=v;return key
        def link(a,b,length):
            graph.setdefault(a,[]).append((b,length));graph.setdefault(b,[]).append((a,length))
        for t in board.GetTracks():
            if t.GetNetname()!=net: continue
            if isinstance(t,p.PCB_VIA):
                layers=[layer for layer in board.GetEnabledLayers().CuStack() if t.IsOnLayer(layer)]
                for l,r in zip(layers,layers[1:]):link(node(t.GetPosition(),l),node(t.GetPosition(),r),0)
            else:link(node(t.GetStart(),t.GetLayer()),node(t.GetEnd(),t.GetLayer()),p.ToMM(t.GetLength()))
        sources=[k for k,v in positions.items() if start.IsOnLayer(k[2]) and start.HitTest(v)]
        goals={k for k,v in positions.items() if finish.IsOnLayer(k[2]) and finish.HitTest(v)}
        queue=[(0,k) for k in sources];heapq.heapify(queue);seen=set()
        while queue:
            distance,key=heapq.heappop(queue)
            if key in seen:continue
            if key in goals:return distance
            seen.add(key)
            for nxt,length in graph[key]:heapq.heappush(queue,(distance+length,nxt))
        raise ValueError(f'No copper-only path for {a} -> {b}')
    pairs=[(('U22','12'),('C95','1')),(('U22','13'),('C96','1')),
           (('U22','11'),('C90','1')),(('U22','10'),('C90','2')),
           (('J90','1'),('D90','1')),(('J90','2'),('D90','2'))]
    paths=[dict(start=list(a),end=list(b),xy_copper_length_mm=route_length(a,b)) for a,b in pairs]
    ground_returns=[]
    for ref,num in [('C95','2'),('C96','2'),('D90','3')]:
        q=pad(ref,num)
        distance=min(p.ToMM((q.GetPosition()-t.GetPosition()).EuclideanNorm())
                     for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND')
        assert distance<=1.5,(ref,'ground stitching too far',distance)
        ground_returns.append(dict(reference=ref,nearest_ground_via_mm=distance))
    planes={board.GetLayerName(z.GetLayer()):z.GetFilledPolysList(z.GetLayer()) for z in board.Zones() if z.GetNetname()=='GND'}
    coverage={}
    for net in ('GEO_P','GEO_N','GEO_AIN_P','GEO_AIN_N'):
        samples=0;hits={name:0 for name in planes};layers=set()
        for t in board.GetTracks():
            if isinstance(t,p.PCB_VIA) or t.GetNetname()!=net:continue
            layers.add(board.GetLayerName(t.GetLayer()))
            a,b=t.GetStart(),t.GetEnd();steps=max(1,math.ceil(p.ToMM(t.GetLength())/.1))
            for i in range(steps+1):
                q=p.VECTOR2I(round(a.x+(b.x-a.x)*i/steps),round(a.y+(b.y-a.y)*i/steps))
                samples+=1
                for name,plane in planes.items():hits[name]+=plane.Contains(q)
        coverage[net]=dict(samples=samples,over_ground_by_plane=hits,signal_layers=sorted(layers))
    module=[30,8,80,48]
    fit={ref:dict(courtyard_mm=courtyard(ref),module_xy_separation_mm=separation(courtyard(ref),module)) for ref in ('J90','J83')}
    from geophone_checks import verify_connector
    connector=fps['J90']
    verify_connector({q.GetNumber():(*xy(q.GetPosition()),p.ToMM(q.GetDrillSize().x)) for q in connector.Pads()},
                     (connector.GetOrientationDegrees(),connector.IsFlipped()),str(connector.GetFPID().GetLibItemName()))
    fit['J90'].update(header_mpn='1803280',header_installed_height_mm=7.25,plug_mpn='1803581',
                      plug_dimensions_mm=[12.22,16.1,11.1],
                      mating_axis='+Y, parallel to PCB',
                      cable_service_envelope_verified=False)
    drill=[p.ToMM(q.GetDrillSize().x) for q in fps['J90'].Pads()]
    assert drill==[1.2]*3,drill
    assert fit['J90']['module_xy_separation_mm']>8
    findings=[]
    # Project review goals, NOT manufacturer absolute limits or noise guarantees.
    for path in paths:
        target=5 if path['start'][0]=='J90' else 3
        if path['xy_copper_length_mm']>target:
            findings.append(dict(code='analog_path_review',start=path['start'],end=path['end'],
                measured_mm=path['xy_copper_length_mm'],review_target_mm=target,
                disposition='shorten protection paths / put final filter at ADC before layout freeze'))
    assert not findings, findings
    from assembly_fit import review
    from assembly_fit import default_obstacles
    placements={ref:(*xy(fp.GetPosition()),fp.GetOrientationDegrees(),
                    'back' if fp.IsFlipped() else 'front') for ref,fp in fps.items()}
    obstacles=default_obstacles(placements)
    for ref,fp in fps.items():
        if fp.IsFlipped():
            height=1.2 if ref.startswith('U10') else (1.1 if ref=='D90' else .9)
            x0,y0,x1,y1=courtyard(ref)
            obstacles[ref]=(x0,y0,-1.6-height,x1,y1,-1.6)
        for q in fp.Pads():
            if q.GetAttribute()!=p.PAD_ATTRIB_PTH or ref=='J1':continue
            x,y=xy(q.GetPosition());size=q.GetSize();rx=p.ToMM(max(size.x,size.y))/2
            # Entire plated pad area plus 0.2 mm tail/trim tolerance.
            depth=2.2
            obstacles[ref+'_tail_'+q.GetNumber()+'_'+str(round(x,3))+','+str(round(y,3))]=(x-rx,y-rx,-1.6-depth,x+rx,y+rx,-1.6)
    for ref in ('H80','H81','H82','H83'):
        x,y=xy(fps[ref].GetPosition())
        obstacles[ref+'_screw_head']=(x-2.75,y-2.75,-3.6,x+2.75,y+2.75,-1.6)
    assembly=review(placements,obstacles)
    return dict(paths=paths,findings=findings,analog_reference_plane_samples=coverage,connectors=fit,
        local_ground_stitches=ground_returns,
        selected_assembly=assembly,
        module_xy_envelope_mm=module,module_surface_gap_mm=8,
        pi_to_hat_underside_mm=assembly['pi_to_hat_underside_mm'],pi_assumed_obstruction_mm=16,
        limits=['Copper path lengths omit pad interiors and via barrel length',
                'Ground centerline samples are a screen for voids, not field-solver signoff',
                'Plug dimensions are manufacturer data; connectors are bounded envelopes, not supplier mated solids',
                'Selected Pi/heatsink/plug and four straight supports checked; first-article fit remains unmeasured'])


def main():
    import pcbnew as p
    path=BOARD/(BOARD.name+'.kicad_pcb')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    board=p.LoadBoard(str(path))
    from geophone_checks import verify
    pins={(f.GetReference(),q.GetNumber()):q.GetNetname() for f in board.GetFootprints() for q in f.Pads()}
    pin_checks=verify(pins,{f.GetReference():(f.GetOrientationDegrees(),f.IsFlipped()) for f in board.GetFootprints()})
    # Independent purchasing/package fixtures for the newly introduced ICs and header.
    rows={r['Reference']:r for r in csv.DictReader((BOARD/'bom.csv').open())}
    packages={'U22':('ADS122C04IPWR','Package_SO__TSSOP-16_4.4x5mm_P0.65mm'),
              'D90':('TPD2E2U06QDCKRQ1','Package_TO_SOT_SMD__SOT-323_SC-70'),
              'J90':('1803280','Connector_Phoenix_MC__PhoenixContact_MC_1,5_3-G-3.81_1x03_P3.81mm_Horizontal'),
              'C90':('C3216C0G1H104J160AA','Capacitor_SMD__C_1206_3216Metric'),
              'C91':('C0603C102J5GACTU','Capacitor_SMD__C_0603_1608Metric'),
              'C92':('C0603C102J5GACTU','Capacitor_SMD__C_0603_1608Metric')}
    for refs,mpn,footprint in [
        (('R90','R91'),'RC0603FR-071KL','Resistor_SMD__R_0603_1608Metric'),
        (('R92','R93'),'RC0603FR-071ML','Resistor_SMD__R_0603_1608Metric'),
        (('R94','R95','R97'),'RC0603FR-0710KL','Resistor_SMD__R_0603_1608Metric'),
        (('R96',),'RC0603FR-0722RL','Resistor_SMD__R_0603_1608Metric'),
        (('C93','C94'),'GRM21BR61A106KE19L','Capacitor_SMD__C_0805_2012Metric'),
        (('C95','C96'),'GRM188R71H104KA93D','Capacitor_SMD__C_0603_1608Metric')]:
        for ref in refs:packages[ref]=(mpn,footprint)
    for ref,(mpn,footprint) in packages.items():
        assert rows[ref]['MPN']==mpn and rows[ref]['Footprint']==footprint,(ref,rows[ref])
    report=dict(scope='pre-fab engineering review; no physical qualification',
        disposition='analog and internal-link stack reviewed; physical power/noise/fit and link throughput remain unqualified',
        board_sha256=before,physical_pin_checks=pin_checks,purchasing_package_checks=len(packages),
        analog=analog_review(),layout_and_fit=geometry_review(board),
        imu_bypass=__import__('imu_layout').review(board),
        sensor_supply_layout=__import__('sensor_supply_layout').review(board))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    (BOARD/'prefab-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
