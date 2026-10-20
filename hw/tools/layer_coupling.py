"""Geometric broadside-proximity screen, not a crosstalk voltage simulation."""
import math
from collections import Counter


def overlaps(first,second,dielectric_mm):
    import numpy as np
    def geometry(rows):
        a=np.array([r['a'] for r in rows]);z=np.array([r['z'] for r in rows]);delta=z-a
        length=np.linalg.norm(delta,axis=1)
        if np.any(length<=0):raise ValueError('Zero-length coupling segment')
        return a,delta/length[:,None],length
    if not first or not second:return []
    aa,uu,ll=geometry(first);bb,vv,mm=geometry(second)
    widths=np.array([r['width'] for r in second]);result=[]
    for index,row in enumerate(first):
        offset=bb-aa[index];u=uu[index];direction=vv@u
        parallel=np.abs(u[0]*vv[:,1]-u[1]*vv[:,0])<.01
        gap=np.abs(offset[:,0]*u[1]-offset[:,1]*u[0]);projection=offset@u
        end=projection+mm*direction
        length=np.minimum(ll[index],np.maximum(projection,end))-np.maximum(0,np.minimum(projection,end))
        close=gap<=(row['width']+widths)/2+3*dielectric_mm
        for j in np.where(parallel&close&(length>.1))[0]:
            if row['net']==second[j]['net']:continue
            result.append(dict(nets=sorted([row['net'],second[j]['net']]),length_mm=float(length[j]),
                               center_gap_mm=float(gap[j]),first=row['id'],second=second[j]['id']))
    return result


def verify(rows,limit_mm=5):
    totals=Counter()
    for row in rows:totals[tuple(row['nets'])]+=row['length_mm']
    failed={pair:round(length,4) for pair,length in totals.items() if length>limit_mm}
    if failed:raise ValueError(f'Adjacent-layer parallel signal screen exceeds {limit_mm} mm: {failed}')
    return [dict(nets=list(pair),total_parallel_mm=length) for pair,length in totals.most_common()]


def review(board):
    import pcbnew as p
    from copper_resistance import stackup
    stack=stackup(board.GetFileName());gap=stack[2]['dielectric_to_next_mm']
    supply={'GND','PI_3V3','PI_5V','PI_RAW_5V','SENS_3V3','FPGA_VIN','FPGA_3V3',
            'EXT_12V','FUSED_12V','PROTECTED_12V','BAT_INPUT','BAT_FUSED','BAT_PROTECTED',
            'SUP_3V3','SUP_CORE','GNSS_LDO','GNSS_BIAS','GEO_AVDD'}
    layers=[]
    for layer in ('In2.Cu','In3.Cu'):
        layers.append([dict(net=t.GetNetname(),id=t.m_Uuid.AsString(),
                            a=[p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)],
                            z=[p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y)],width=p.ToMM(t.GetWidth()))
                       for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                       and t.GetLayer()==board.GetLayerID(layer) and t.GetNetname() not in supply])
    rows=overlaps(*layers,gap);pairs=verify(rows)
    return dict(dielectric_mm=gap,edge_proximity_mm=3*gap,parallel_tolerance_sine=.01,
                pair_limit_mm=5,signal_pair_totals=pairs,segment_pairs=rows,
                method='Parallel segment projection with edge separation <=3 dielectric heights; pair-wise lengths may overlap',
                qualified=False,limitations='Geometric screen only. Crossings, vias, planes, edge rates and receiver thresholds require SI qualification.')
