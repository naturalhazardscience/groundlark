"""Manufacturer terminal-envelope screen for the selected Murata RF inductors.

JELF243A_0100K-01 p8: length 1.0 +/-0.1, width 0.6 +/-0.1,
height 0.5 +/-0.1 and end termination 0.2 +/-0.1 mm. This checks
centered contact overlap, not supplier numbered pads or assembly process yield.
"""
import itertools
import math


def terminal_overlap(pitch, pad_length, pad_width):
    if not all(math.isfinite(v) and v>0 for v in (pitch,pad_length,pad_width)):
        raise ValueError('Invalid RF land dimensions')
    inner=(pitch-pad_length)/2;outer=(pitch+pad_length)/2
    overlaps=[max(0,min(outer,length/2)-max(inner,length/2-terminal))
              for length,terminal in itertools.product((.9,1.1),(.1,.3))]
    # At least the complete minimum 0.1 mm end termination and the minimum
    # 0.5 mm body width must overlap when centered. No placement allowance.
    if inner<=0 or min(overlaps)<.1-1e-7 or pad_width<.5:
        raise ValueError('Murata RF terminal envelope does not fit routed lands')
    return dict(minimum_axial_overlap_mm=min(overlaps),minimum_width_overlap_mm=min(.5,pad_width),
                centered_only=True,manufacturer_recommended_gap_mm=.6,
                actual_gap_mm=2*inner,manufacturer_recommended_pad_width_mm=.66,
                actual_pad_width_mm=pad_width,supplier_placement_verified=False,
                process_note='Existing lands differ from recommended lands; assembly process review remains open')


def review(board):
    import pcbnew as p
    fps={f.GetReference():f for f in board.GetFootprints()};result={}
    for ref in ('L140','L141'):
        pads=sorted(fps[ref].Pads(),key=lambda q:q.GetNumber())
        if [q.GetNumber() for q in pads]!=['1','2']:raise ValueError('RF terminal numbering')
        sizes=[tuple(p.ToMM(q.GetSize())) for q in pads]
        if sizes[0]!=sizes[1]:raise ValueError('RF lands are asymmetric')
        pitch=math.dist(p.ToMM(pads[0].GetPosition()),p.ToMM(pads[1].GetPosition()))
        result[ref]=terminal_overlap(pitch,*sizes[0])
    return result
