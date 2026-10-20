"""Read-only native geometry -> electrostatic extraction -> circuit scenarios."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np
from field_solver import microstrip, broadside, C0, EPS0
from coupled_line import step
from project_paths import board_dir


def transmission(z,epsilon,length_mm,frequency):
    angle=2*np.pi*frequency*np.sqrt(epsilon)*length_mm*1e-3/C0
    return np.array([[np.cos(angle),1j*z*np.sin(angle)],
                     [1j*np.sin(angle)/z,np.cos(angle)]])


def series(z):return np.array([[1,z],[0,1]],complex)
def shunt(y):return np.array([[1,0],[y,1]],complex)


def scattering(matrix,reference=50):
    a,b,c,d=matrix.ravel();den=a+b/reference+c*reference+d
    return (a+b/reference-c*reference-d)/den,2/den


def rf_network(frequency,z,epsilon,lengths,pad_pf,diode_pf=.55,choke_nh=27,
               choke_srf_ghz=3.5,series_cap_pf=47,connector_nh=.8,
               connector_pf=.3,cap_esl_nh=.2,bypass_esl_nh=1):
    w=2*np.pi*frequency
    # L140 is a parallel self-capacitance around a series-loss inductor.
    cp=1/((2*np.pi*choke_srf_ghz*1e9)**2*choke_nh*1e-9)
    choke=1/(1/(2+1j*w*choke_nh*1e-9)+1j*w*cp)
    bypass=.1+1j*w*bypass_esl_nh*1e-9+1/(1j*w*10e-9)
    block=.1+1j*w*cap_esl_nh*1e-9+1/(1j*w*series_cap_pf*1e-12)
    network=series(1j*w*connector_nh*1e-9)@shunt(1j*w*connector_pf*1e-12)
    network=network@transmission(z,epsilon,lengths['GNSS_ANT'],frequency)
    network=network@shunt(1j*w*(pad_pf['GNSS_ANT']+diode_pf)*1e-12+1/(choke+bypass))
    network=network@series(block)@transmission(z,epsilon,lengths['GNSS_RF'],frequency)
    network=network@shunt(1j*w*pad_pf['GNSS_RF']*1e-12)
    s11,s21=scattering(network)
    return dict(return_loss_db=-20*math.log10(max(abs(s11),1e-15)),
                insertion_loss_db=-20*math.log10(max(abs(s21),1e-15)))


def rf_review(board):
    import pcbnew as p
    from gnss_checks import rf_geometry
    values={f.GetReference():f.GetValue() for f in board.GetFootprints()}
    expected={'C148':'47p C0G','L140':'27n','D140':'PESD5V0F1BL','C151':'10n'}
    for ref,value in expected.items():
        if values.get(ref)!=value:raise ValueError(f'RF circuit model does not match native {ref}: {values.get(ref)}')
    native=rf_geometry(board);h=native['dielectric_mm'];width=native['tracks'][0]['width_mm']
    lengths={net:sum(t['length_mm'] for t in native['tracks'] if t['net']==net) for net in ('GNSS_ANT','GNSS_RF')}
    areas={net:sum(p.ToMM(q.GetSize().x)*p.ToMM(q.GetSize().y)
                   for f in board.GetFootprints() if f.GetReference()!='J140'
                   for q in f.Pads() if q.GetNetname()==net) for net in lengths}
    pads={net:area*1e-6*EPS0*native['epsilon_r']/(h*1e-3)*1e12 for net,area in areas.items()}
    nominal=microstrip(width=width,height=h,thickness=native['copper_mm'])
    nominal_network=rf_network(1.57542e9,nominal['z_ohm'],nominal['epsilon_effective'],lengths,pads,diode_pf=.4)
    field=[]
    # Engineering sensitivity envelope, not a promise from the board supplier.
    for dw,dh,er,mask in itertools.product((-.02,.02),(.9,1.1),(3.8,4.6),(0,.025)):
        f=microstrip(width=width+dw,height=h*dh,thickness=native['copper_mm'],er=er,mask=mask,pitch=.01)
        field.append(dict(width_mm=width+dw,height_mm=h*dh,er=er,mask_mm=mask,**f))
    cases=[]
    for f,frequency,pad_scale,connector_nh,diode in itertools.product(field,(1.559e9,1.57542e9,1.61e9),(.8,1.3),(.3,1.5),(.3,.55)):
        cases.append(dict(frequency_hz=frequency,**rf_network(frequency,f['z_ohm'],f['epsilon_effective'],lengths,
                    {net:value*pad_scale for net,value in pads.items()},connector_nh=connector_nh,diode_pf=diode)))
    worst_rl=min(cases,key=lambda r:r['return_loss_db']);worst_il=max(cases,key=lambda r:r['insertion_loss_db'])
    return dict(native=native,components={ref:values[ref] for ref in expected},nominal_masked=nominal,nominal_network=nominal_network,field_corners=field,pad_area_mm2=areas,
                pad_parallel_plate_pf=pads,circuit_cases=len(cases),
                worst_return_loss=worst_rl,worst_insertion_loss=worst_il,
                design_targets=dict(minimum_return_loss_db=10,maximum_insertion_loss_db=1),
                all_corners_meet_targets=worst_rl['return_loss_db']>=10 and worst_il['insertion_loss_db']<=1,
                assumptions=dict(ports_ohm=50,pad_capacitance_multiplier=[.8,1.3],connector_nh=[.3,1.5],
                                 connector_pf=.3,block_esl_nh=.2,bypass_esl_nh=1,choke_srf_ghz=3.5),
                scope='2-D quasi-TEM traces and lumped pads/components; no 3-D connector or antenna model',
                limitations=['Mask is bounded by bare copper and planar filled mask; not a conformal-mask mesh.',
                             'Nearby coplanar metal is omitted; pad area is a lumped parallel-plate estimate.',
                             'Material/etch/connector bounds are assumptions, not verified manufacturing tolerances.',
                             'A false all_corners_meet_targets is an open design finding, never a release PASS.'])


def coupling_review(board):
    import pcbnew as p
    from layer_coupling import review
    from copper_resistance import stackup
    native=review(board);stack=stackup(board.GetFileName())
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    models={};pairs={}
    for row in native['segment_pairs']:
        widths=[p.ToMM(tracks[row[k]].GetWidth()) for k in ('first','second')]
        # Round displacement toward zero to 25 um; include a 20 um etch-width
        # sensitivity and 10% thinner central dielectric in this stress model.
        offset=math.floor(row['center_gap_mm']/.025)*.025
        key=(*widths,offset)
        if key not in models:
            models[key]=broadside(width1=widths[0]+.02,width2=widths[1]+.02,
                gap=native['dielectric_mm']*.9,outer_gap=stack[1]['dielectric_to_next_mm'],
                thickness=stack[2]['thickness_mm'],er=4.6,offset=offset,pitch=.02)
        f=models[key];pair=tuple(row['nets']);length=row['length_mm']
        if pair not in pairs:pairs[pair]=[0,np.zeros((2,2)),np.zeros((2,2))]
        pairs[pair][0]+=length
        # Preserve the ordered signal identity across sections.
        order=[0,1] if tracks[row['first']].GetNetname()==pair[0] else [1,0]
        for index,name in ((1,'capacitance_F_m'),(2,'inductance_H_m')):
            pairs[pair][index]+=f[name][np.ix_(order,order)]*length
    rows=[]
    for pair,(length,c,l) in pairs.items():
        c/=length;l/=length
        cases=[]
        for drive,victim,rise,load in itertools.product((20,100),(20,4700),(.5,2),(2,10)):
            value=step(c,l,length,driver_ohm=drive,victim_ohm=victim,rise_ns=rise,load_pf=load)
            cases.append(dict(driver_ohm=drive,victim_ohm=victim,rise_ns=rise,load_pf=load,
                              peak_V=max(value.values()),**value))
        rows.append(dict(nets=list(pair),parallel_mm=length,mutual_pf=float(-c[0,1]*length*1e-3*1e12),
                         mutual_nh=float(l[0,1]*length*1e-3*1e9),worst=max(cases,key=lambda c:c['peak_V'])))
    return dict(pairs=sorted(rows,key=lambda r:-r['worst']['peak_V']),field_sections=len(models),
                worst_pi_pair=max((r for r in rows if any(n.startswith('PI_') for n in r['nets'])),key=lambda r:r['worst']['peak_V']),
                cases_per_pair=16,rail_step_V=3.465,
                scope='Adjacent In2/In3 parallel regions collapsed into coherent equivalent coupled lines',
                limitations=['Corners are sensitivity scenarios, not vendor-guaranteed transistor/stackup bounds.',
                             'Receiver load and output resistance are swept; no IBIS clamp or nonlinear pad model.',
                             'Crossings, vias, same-layer coupling, whole-net reflections and simultaneous aggressors are excluded.'])


def report():
    import pcbnew as p
    path=board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb'
    before=path.read_bytes();board=p.LoadBoard(str(path))
    result=dict(board_sha256=hashlib.sha256(before).hexdigest(),rf=rf_review(board),coupling=coupling_review(board))
    if path.read_bytes()!=before:raise RuntimeError('simulation changed authored CAD')
    return result


if __name__=='__main__':
    output=Path('hw/groundlark-fpga-hat/simulation/signal-integrity.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    result=report();output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(rf_return_loss=result['rf']['worst_return_loss'],
                         rf_insertion_loss=result['rf']['worst_insertion_loss'],
                         coupling_worst=result['coupling']['pairs'][:3]),indent=2))
