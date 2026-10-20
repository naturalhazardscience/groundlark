"""Geometric broadside-proximity screen, not a crosstalk voltage simulation."""
import math
from collections import Counter


def parallel_overlaps(first,second,dielectric_mm):
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


def _capsule_interval(a,u,length,b,v,other_length,radius):
    """Exact intersection of a line segment with a round-ended segment buffer."""
    dot=lambda x,y:sum(i*j for i,j in zip(x,y))
    sub=lambda x,y:tuple(i-j for i,j in zip(x,y))
    offset=sub(a,b);along=dot(offset,v);slope=dot(u,v)
    normal=(-v[1],v[0]);across=dot(offset,normal);cross_slope=dot(u,normal)
    intervals=[]
    lo,hi=0.,length
    for start,rate,lower,upper in ((along,slope,0.,other_length),(across,cross_slope,-radius,radius)):
        if abs(rate)<1e-12:
            if not lower<=start<=upper:hi=-1;break
        else:
            x,y=sorted(((lower-start)/rate,(upper-start)/rate));lo=max(lo,x);hi=min(hi,y)
    if hi>lo:intervals.append((lo,hi))
    for end in (b,tuple(b[i]+v[i]*other_length for i in range(2))):
        d=sub(a,end);projection=dot(d,u);disc=radius**2-dot(d,d)+projection**2
        if disc>=0:
            root=math.sqrt(max(0,disc));lo=max(0.,-projection-root);hi=min(length,-projection+root)
            if hi>lo:intervals.append((lo,hi))
    return (min(x for x,y in intervals),max(y for x,y in intervals)) if intervals else None


def overlaps(first,second,dielectric_mm):
    """Union of In2 path intervals within 3h edge distance of each In3 net.

    Includes bends, crossings and endpoints, without double-counting adjacent
    segments of the same opposing net. Length is measured along the first layer.
    """
    import numpy as np
    result=[]
    if not first or not second:return result
    bb=np.array([r['a'] for r in second]);zz=np.array([r['z'] for r in second])
    delta=zz-bb;ll=np.linalg.norm(delta,axis=1)
    if np.any(ll<=0):raise ValueError('Zero-length coupling segment')
    vv=delta/ll[:,None];widths=np.array([r['width'] for r in second])
    for row in first:
        a=np.array(row['a']);z=np.array(row['z']);length=float(np.linalg.norm(z-a))
        if length<=0:raise ValueError('Zero-length coupling segment')
        u=(z-a)/length;radius=(row['width']+widths)/2+3*dielectric_mm
        candidates=np.where(np.all(np.maximum(bb,zz)+radius[:,None]>=np.minimum(a,z),axis=1)&
                            np.all(np.minimum(bb,zz)-radius[:,None]<=np.maximum(a,z),axis=1))[0]
        by_net={}
        for j in candidates:
            other=second[j]
            if other['net']==row['net']:continue
            interval=_capsule_interval(a,u,length,bb[j],vv[j],ll[j],radius[j])
            if interval:by_net.setdefault(other['net'],[]).append((*interval,int(j)))
        for net,intervals in by_net.items():
            cuts={x for lo,hi,j in intervals for x in (lo,hi)}
            # Split at exact 25 um distance contours. The field approximation
            # must not change just because KiCad splits a straight track.
            for lo,hi,j in intervals:
                for index in range(1,math.ceil(radius[j]/.025)):
                    band=_capsule_interval(a,u,length,bb[j],vv[j],ll[j],index*.025)
                    if band:
                        cuts.update(x for x in band if lo<x<hi)
            cuts=sorted(cuts)
            for lo,hi in zip(cuts,cuts[1:]):
                if hi-lo<1e-9:continue
                active=[j for x,y,j in intervals if x<(lo+hi)/2<y]
                if not active:continue
                # All distance-contour crossings are cuts, so an interior
                # point identifies the conservative lower-distance bin.
                midpoint=a+u*((lo+hi)/2)
                def distance(j):
                    return float(np.linalg.norm(midpoint-(bb[j]+vv[j]*np.clip(np.dot(midpoint-bb[j],vv[j]),0,ll[j]))))
                j=min(active,key=distance)
                gap=distance(j)
                result.append(dict(nets=sorted((row['net'],net)),length_mm=hi-lo,
                    center_gap_mm=math.floor((gap+1e-10)/.025)*.025,first=row['id'],second=second[j]['id'],
                    first_interval_mm=[lo,hi]))
    return result


def verify(rows,limit_mm=5):
    totals=Counter()
    for row in rows:totals[tuple(row['nets'])]+=row['length_mm']
    failed={pair:round(length,4) for pair,length in totals.items() if length>limit_mm}
    if failed:raise ValueError(f'Adjacent-layer parallel signal screen exceeds {limit_mm} mm: {failed}')
    return [dict(nets=list(pair),total_parallel_mm=length) for pair,length in totals.most_common()]


def review(board,include_segments=True):
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
    parallel=verify(parallel_overlaps(*layers,gap))
    rows=overlaps(*layers,gap);totals=Counter()
    for row in rows:totals[tuple(row['nets'])]+=row['length_mm']
    pairs=[dict(nets=list(pair),proximity_mm=length) for pair,length in totals.most_common()]
    result=dict(dielectric_mm=gap,edge_proximity_mm=3*gap,parallel_tolerance_sine=.01,
                parallel_pair_limit_mm=5,parallel_pair_totals=parallel,signal_pair_totals=pairs,segment_pairs=rows,
                segment_interval_count=len(rows),
                method='Exact round-ended proximity intervals, unioned per In2 segment/opposing net; includes angled crossings and endpoints',
                qualified=False,limitations='In2 path length, not a voltage margin. Electrical acceptance is enforced by simulate_signal_integrity.py; vias and whole-net effects remain unmodeled.')
    if not include_segments:
        del result['segment_pairs']
        result['segment_pair_evidence']='signal-integrity.json coupling.native.segment_pairs in the same lab run'
    return result
