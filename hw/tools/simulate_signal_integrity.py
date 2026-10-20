"""Read-only native geometry -> electrostatic extraction -> circuit scenarios."""
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
# Thousands of small ladder solves do not benefit from a large default BLAS
# thread pool. Preserve an explicitly configured thread count.
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from field_solver import microstrip, broadside, C0, EPS0
from coupled_line import step
from project_paths import board_dir

# Project allocation for this modeled coupling mechanism, not a universal
# receiver noise margin. Reserve the remaining static margin for other effects.
CROSSTALK_LIMIT_V = .2


def coupling_acceptance(rows):
    if not rows:raise ValueError('No adjacent-layer coupling cases evaluated')
    failed=[]
    for row in rows:
        value=row['worst']['peak_V']
        if not math.isfinite(value) or value<0 or value>CROSSTALK_LIMIT_V:
            failed.append(dict(nets=row['nets'],peak_V=value))
    return dict(maximum_excursion_V=CROSSTALK_LIMIT_V,all_pairs_meet_target=not failed,
                failed_pairs=failed,basis='Project allocation for one modeled aggressor; not receiver or physical qualification')


def require_acceptance(result):
    failures=[]
    if not result['rf']['all_corners_meet_targets']:failures.append('RF design envelope failed')
    if not result['coupling']['acceptance']['all_pairs_meet_target']:
        failures.append('Adjacent-layer crosstalk allocation failed')
    if failures:raise ValueError('; '.join(failures))


def transmission(z,epsilon,length_mm,frequency):
    angle=2*np.pi*frequency*np.sqrt(epsilon)*length_mm*1e-3/C0
    return np.array([[np.cos(angle),1j*z*np.sin(angle)],
                     [1j*np.sin(angle)/z,np.cos(angle)]])


def series(z):return np.array([[1,z],[0,1]],complex)
def shunt(y):return np.array([[1,0],[y,1]],complex)


def scattering(matrix,reference=50):
    a,b,c,d=matrix.ravel();den=a+b/reference+c*reference+d
    return (a+b/reference-c*reference-d)/den,2/den


def terminated_line(z, epsilon, length_mm, frequency, load):
    a,b,c,d=transmission(z,epsilon,length_mm,frequency).ravel()
    return (a*load+b)/(c*load+d)


def inductor_impedance(frequency, nominal_nh, srf_ghz, q, dcr_ohm):
    """Series RL shunted by winding capacitance; a sensitivity surrogate.

    None SRF omits winding capacitance; None Q omits AC loss but retains DCR.
    Q at GNSS frequencies is an engineering assumption, not the datasheet Q
    measured at 200/250 MHz. This is not a fitted Murata S-parameter model.
    """
    w=2*np.pi*frequency;l=nominal_nh*1e-9
    resistance=dcr_ohm+(w*l/q if q is not None else 0)
    capacitance=1/((2*np.pi*srf_ghz*1e9)**2*l) if srf_ghz is not None else 0
    return 1/(1/(resistance+1j*w*l)+1j*w*capacitance)


def choke_impedance(frequency, nominal_nh=56, srf_ghz=2.9, q=30):
    return inductor_impedance(frequency,nominal_nh,srf_ghz,q,.996)


def rf_network(frequency,z,epsilon,lengths,pad_pf,diode_pf=.55,choke_nh=56,
               choke_srf_ghz=2.9,series_cap_pf=47,connector_nh=.8,
               connector_pf=.3,cap_esl_nh=.2,bypass_esl_nh=1,
               match_nh=3.6,match_q=60,match_srf_ghz=10,
               branch_z=35.7,branch_epsilon=3.5,choke_q=30,
               diode_esl_nh=.2):
    w=2*np.pi*frequency
    choke=choke_impedance(frequency,choke_nh,choke_srf_ghz,choke_q)
    bypass=.1+1j*w*bypass_esl_nh*1e-9+1/(1j*w*10e-9)
    block=.1+1j*w*cap_esl_nh*1e-9+1/(1j*w*series_cap_pf*1e-12)
    bias_load=1/(1/(choke+bypass)+1j*w*pad_pf.get('BIAS',0)*1e-12)
    diode_load=1/(1/(1j*w*diode_esl_nh*1e-9+1/(1j*w*diode_pf*1e-12))+
                  1j*w*pad_pf.get('ESD',0)*1e-12)
    bias=terminated_line(branch_z,branch_epsilon,lengths.get('BIAS',0),frequency,bias_load)
    esd=terminated_line(branch_z,branch_epsilon,lengths.get('ESD',0),frequency,diode_load)
    network=series(1j*w*connector_nh*1e-9)@shunt(1j*w*connector_pf*1e-12+1/bias+1/esd)
    network=network@transmission(z,epsilon,lengths['GNSS_ANT'],frequency)
    network=network@shunt(1j*w*pad_pf['GNSS_ANT']*1e-12)@series(block)
    network=network@transmission(z,epsilon,lengths.get('GNSS_MATCH',0),frequency)
    network=network@shunt(1j*w*pad_pf.get('GNSS_MATCH',0)*1e-12)
    if match_nh:
        match=inductor_impedance(frequency,match_nh,match_srf_ghz,match_q,.03)
        network=network@series(match)
    network=network@transmission(z,epsilon,lengths['GNSS_RF'],frequency)
    network=network@shunt(1j*w*pad_pf['GNSS_RF']*1e-12)
    s11,s21=scattering(network)
    return dict(return_loss_db=-20*math.log10(max(abs(s11),1e-15)),
                insertion_loss_db=-20*math.log10(max(abs(s21),1e-15)),
                choke_impedance_ohm=float(abs(choke+bypass)))


def rf_review(board):
    import pcbnew as p
    from gnss_checks import rf_geometry
    from rf_substitution import review as substitution_review
    substitution=substitution_review(board)
    values={f.GetReference():f.GetValue() for f in board.GetFootprints()}
    expected={'C148':'47p C0G','L140':'56n','L141':'3.6n','D140':'PESD5V0F1BL','C151':'10n'}
    for ref,value in expected.items():
        if values.get(ref)!=value:raise ValueError(f'RF circuit model does not match native {ref}: {values.get(ref)}')
    from jlcpcb_bom import load_registry
    selected={ref:part['mpn'] for part in load_registry()['parts'] for ref in part['designators']}
    for ref,mpn in {'L140':'LQW15AN56NG80D','L141':'LQW15AN3N6G80D',
                    'C148':'GRM1555C1H470JA01D','D140':'PESD5V0F1BL,315'}.items():
        if selected.get(ref)!=mpn:raise ValueError(f'RF model does not match assembly selection {ref}')
    native=rf_geometry(board);h=native['dielectric_mm'];width=native['tracks'][0]['width_mm']
    lengths=native['path_lengths_mm']
    nodes={'GNSS_ANT':[('C148','1')],'GNSS_MATCH':[('C148','2'),('L141','1')],
           'GNSS_RF':[('L141','2'),('U21','11')],'BIAS':[('L140','2')],'ESD':[('D140','1')]}
    areas={node:sum(p.ToMM(q.GetSize().x)*p.ToMM(q.GetSize().y)
                   for f in board.GetFootprints() for q in f.Pads()
                   if (f.GetReference(),q.GetNumber()) in pins) for node,pins in nodes.items()}
    pads={net:area*1e-6*EPS0*native['epsilon_r']/(h*1e-3)*1e12 for net,area in areas.items()}
    nominal=microstrip(width=width,height=h,thickness=native['copper_mm'])
    nominal_network=rf_network(1.57542e9,nominal['z_ohm'],nominal['epsilon_effective'],lengths,pads,diode_pf=.4,
                               branch_z=nominal['z_ohm'],branch_epsilon=nominal['epsilon_effective'])
    field=[]
    # Engineering sensitivity envelope, not a promise from the board supplier.
    for dw,dh,er,mask in itertools.product((-.02,.02),(.9,1.1),(3.8,4.6),(0,.025)):
        f=microstrip(width=width+dw,height=h*dh,thickness=native['copper_mm'],er=er,mask=mask,pitch=.01)
        field.append(dict(width_mm=width+dw,height_mm=h*dh,er=er,mask_mm=mask,**f))
    extrema={};count=0
    component_corners=list(itertools.product((.93,1.07),(.93,1.07),(2.9,None),(.95,1.05),(.1,.3),(10,None),(10,None),(10,None)))
    for f,frequency,pad_scale,connector_nh,diode,connector_pf in itertools.product(
            field,(1.559e9,1.57542e9,1.61e9),(.8,1.3),(.3,1.5),(.3,.55),(.15,.45)):
        for match_tol,choke_tol,srf,cap_tol,esl,match_srf,choke_q,match_q in component_corners:
            inputs=dict(connector_nh=connector_nh,connector_pf=connector_pf,diode_pf=diode,
                match_nh=3.6*match_tol,match_q=match_q,match_srf_ghz=match_srf,
                choke_nh=56*choke_tol,choke_srf_ghz=srf,choke_q=choke_q,
                series_cap_pf=47*cap_tol,cap_esl_nh=esl,
                branch_z=f['z_ohm'],branch_epsilon=f['epsilon_effective'])
            row=dict(frequency_hz=frequency,field={k:f[k] for k in ('width_mm','height_mm','er','mask_mm')},
                pad_multiplier=pad_scale,inputs=inputs,
                **rf_network(frequency,f['z_ohm'],f['epsilon_effective'],lengths,
                             {net:value*pad_scale for net,value in pads.items()},**inputs))
            count+=1
            for key,maximum in (('return_loss_db',False),('insertion_loss_db',True),('choke_impedance_ohm',False)):
                if key not in extrema or (row[key]>extrema[key][key] if maximum else row[key]<extrema[key][key]):extrema[key]=row
    worst_rl=extrema['return_loss_db'];worst_il=extrema['insertion_loss_db']
    # Check between the band endpoints at every identified worst-case corner.
    dense=[]
    for worst in extrema.values():
        f=next(f for f in field if all(f[k]==v for k,v in worst['field'].items()))
        for frequency in np.linspace(1.559e9,1.61e9,257):
            dense.append(rf_network(frequency,f['z_ohm'],f['epsilon_effective'],lengths,
                {net:value*worst['pad_multiplier'] for net,value in pads.items()},**worst['inputs']))
    dense_pass=all(row['return_loss_db']>=10 and row['insertion_loss_db']<=1 and row['choke_impedance_ohm']>=500 for row in dense)
    return dict(native=native,components={ref:values[ref] for ref in expected},assembly_mpns={ref:selected[ref] for ref in ('L140','L141')},substitution_lands=substitution,nominal_masked=nominal,nominal_network=nominal_network,field_corners=field,pad_area_mm2=areas,
                pad_parallel_plate_pf=pads,circuit_cases=count,
                worst_return_loss=worst_rl,worst_insertion_loss=worst_il,
                worst_choke_isolation=extrema['choke_impedance_ohm'],
                dense_frequency_cases=len(dense),dense_frequency_sweep_pass=dense_pass,
                design_targets=dict(minimum_return_loss_db=10,maximum_insertion_loss_db=1,minimum_choke_impedance_ohm=500),
                all_corners_meet_targets=dense_pass and worst_rl['return_loss_db']>=10 and worst_il['insertion_loss_db']<=1 and extrema['choke_impedance_ohm']['choke_impedance_ohm']>=500,
                assumptions=dict(ports_ohm=50,pad_capacitance_multiplier=[.8,1.3],connector_nh=[.3,1.5],
                    connector_pf=[.15,.45],block_esl_nh=[.1,.3],bypass_esl_nh=1,
                    inductance_multiplier=[.93,1.07],block_cap_multiplier=[.95,1.05],
                    match_q=[10,None],choke_q=[10,None],match_srf_ghz=[10,None],choke_srf_ghz=[2.9,None],
                    null_endpoint='No winding capacitance / no AC resistance; DCR retained',
                    manufacturer_reference='https://search.murata.co.jp/Ceramy/image/img/P02/JELF243A-0100.pdf',
                    manufacturer_specification='JELF243A_0100K-01 pp3,8,9',
                    reference_case='Minimum specified SRF, assumed Q 30/60; not a measured typical prediction'),
                scope='2-D quasi-TEM traces and lumped pads/components; no 3-D connector or antenna model',
                limitations=['Mask is bounded by bare copper and planar filled mask; not a conformal-mask mesh.',
                             'Nearby coplanar metal is omitted; pad area is a lumped parallel-plate estimate.',
                             'The SMA antipad leaves bias/ESD branches unreferenced. Their transmission-line surrogate plus connector parasitics is not a 3-D launch solution.',
                             'L141 is a VNA tuning position; 3.6 nH is provisional and depends on modeled pad capacitance.',
                             'Murata Q minima are specified at 200/250 MHz, not GNSS L1. Q >=10 at L1 and the single-resonance surrogate remain unqualified assumptions; no vendor S-parameters were used.',
                             'Material/etch/connector bounds are assumptions, not verified manufacturing tolerances.',
                             'A false all_corners_meet_targets fails the simulation profile.'])


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
        offset=math.floor(row['center_gap_mm']/.025+1e-8)*.025
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
        for direction,drive,victim,rise,load in itertools.product((0,1),(20,100),(20,4700),(.5,2),(2,10)):
            order=[direction,1-direction]
            value=step(c[np.ix_(order,order)],l[np.ix_(order,order)],length,
                       driver_ohm=drive,victim_ohm=victim,rise_ns=rise,load_pf=load)
            cases.append(dict(driver_ohm=drive,victim_ohm=victim,rise_ns=rise,load_pf=load,
                              aggressor=pair[direction],victim=pair[1-direction],peak_V=max(value.values()),**value))
        rows.append(dict(nets=list(pair),proximity_mm=length,mutual_pf=float(-c[0,1]*length*1e-3*1e12),
                         mutual_nh=float(l[0,1]*length*1e-3*1e9),worst=max(cases,key=lambda c:c['peak_V'])))
    return dict(pairs=sorted(rows,key=lambda r:-r['worst']['peak_V']),field_sections=len(models),
                worst_pi_pair=max((r for r in rows if any(n.startswith('PI_') for n in r['nets'])),key=lambda r:r['worst']['peak_V'],default=None),
                cases_per_pair=32,rail_step_V=3.465,acceptance=coupling_acceptance(rows),
                native=native,
                scope='Adjacent In2/In3 proximity regions collapsed into coherent equivalent coupled lines; angled regions modeled parallel at minimum separation',
                limitations=['Corners are sensitivity scenarios, not vendor-guaranteed transistor/stackup bounds.',
                             'Receiver load and output resistance are swept; no IBIS clamp or nonlinear pad model.',
                             'Crossings use a parallel surrogate, not a 3-D field solution.',
                             'Vias, same-layer coupling, whole-net reflections and simultaneous aggressors are excluded.'])


def report():
    import pcbnew as p
    path=board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb'
    before=path.read_bytes();board=p.LoadBoard(str(path))
    result=dict(board_sha256=hashlib.sha256(before).hexdigest(),rf=rf_review(board),coupling=coupling_review(board))
    if path.read_bytes()!=before:raise RuntimeError('simulation changed authored CAD')
    return result


def save_report(result,output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    require_acceptance(result)


if __name__=='__main__':
    output=Path('hw/groundlark-fpga-hat/simulation/signal-integrity.json')
    result=report()
    print(json.dumps(dict(rf_return_loss=result['rf']['worst_return_loss'],
                         rf_insertion_loss=result['rf']['worst_insertion_loss'],
                         coupling_worst=result['coupling']['pairs'][:3]),indent=2))
    try:save_report(result,output)
    except ValueError as error:raise SystemExit(str(error)) from error
