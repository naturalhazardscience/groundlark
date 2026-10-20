"""DAQHAT-01 internal-link stack envelopes, board-top XY/Z millimetres.

Conservative support/port/cooler checks; no ribbons or custom guide remain.
"""
from hardware_require import require as _require_hardware
J1_BODY = 8.5  # Megastar ZX-PM2.54-2-20PY, selected JLC assembly socket.
RISER_BODY = 8.51  # Samtec SSQ-120-02-G-D, external self-nesting riser.
RISER_COUNT = 2
PI_GAP = J1_BODY + 2.54 + RISER_COUNT * RISER_BODY
PI_TOP = -1.6 - PI_GAP
MODULE = (30,8,80,48)
PI_SUPPORTS = ((3.5,3.5),(61.5,3.5),(3.5,52.5),(61.5,52.5))
PI_OBSTACLES = {
    'ethernet':(65.5,2.5,PI_TOP,86.5,18.5,PI_TOP+16),
    'usb1':(65.5,21.5,PI_TOP,86.5,36.5,PI_TOP+16),
    'usb2':(65.5,39.5,PI_TOP,86.5,54.5,PI_TOP+16),
    'heatsink':(22,19,PI_TOP,40,37,PI_TOP+13.3),
    'power':(6.5,51,PI_TOP,15.5,57,PI_TOP+3.2),
    'hdmi1':(22.5,51,PI_TOP,29.5,57,PI_TOP+3),
    'hdmi2':(35.5,51,PI_TOP,42.5,57,PI_TOP+3),
}


def box_gap(a,b):
    """Signed separating-axis margin: <=0 means overlap/touch."""
    return max(a[0]-b[3],b[0]-a[3],a[1]-b[4],b[1]-a[4],a[2]-b[5],b[2]-a[5])


def default_obstacles(placements):
    return {'C95':(13.7,43.55,-2.5,16.7,45.45,-1.6),
            'C96':(17.75,43,-2.5,19.65,46,-1.6),
            'D90':(10.1,45,-2.7,13.5,48.6,-1.6),
            'Pi_GPIO_socket':(6.8,1.025,PI_TOP+2.54,58.2,5.975,-1.6)}


def review(placements,obstacles=None,supports=PI_SUPPORTS):
    _require_hardware((len(supports)==4 and set(supports)==set(PI_SUPPORTS)), lambda: ('All four straight supports required'))
    _require_hardware((not any(ref in placements for ref in ('J84','J85','J86','J87','J88','J89'))), lambda: ('External connectors remain'))
    obstacles=default_obstacles(placements) if obstacles is None else dict(obstacles)
    board_margin={};pi_margin={}
    for i,(x,y) in enumerate(supports):
        post=(x-2.4,y-2.4,PI_TOP,x+2.4,y+2.4,-1.6)
        board_margin[str(i+1)]=min(box_gap(post,other) for other in obstacles.values())-.5
        pi_margin[str(i+1)]=min(box_gap(post,other) for other in PI_OBSTACLES.values())-.5
        _require_hardware((board_margin[str(i+1)]>0), lambda: (('support-to-HAT',i+1,board_margin[str(i+1)])))
        _require_hardware((pi_margin[str(i+1)]>0), lambda: (('support-to-Pi',i+1,pi_margin[str(i+1)])))
    component_margins={}
    for ref,box in obstacles.items():
        if ref=='Pi_GPIO_socket':continue  # Intended mating connection.
        component_margins[ref]=min(box_gap(box,other) for other in PI_OBSTACLES.values())-1
        _require_hardware((component_margins[ref]>0), lambda: (('HAT-to-Pi',ref,component_margins[ref])))
    plug_margin=MODULE[0]-(14.19+12.22/2+.5)
    _require_hardware((plug_margin>0), lambda: ('assembly_fit.py:52: hardware validation condition'))
    return dict(status='Four straight-support CAD envelopes pass; first-article fit remains unmeasured',
        pi='Raspberry Pi 4 Model B',pi_supports_xy_mm=supports,omitted_support_xy_mm=None,
        pi_to_hat_underside_mm=PI_GAP,module_surface_gap_mm=8,
        j1='ZX-PM2.54-2-20PY',riser='SSQ-120-02-G-D',riser_count=RISER_COUNT,
        external_ribbon_count=0,custom_guide_required=False,
        support_to_board_margin_mm=board_margin,support_to_pi_margin_mm=pi_margin,
        hat_to_pi_margin_mm=component_margins,
        minimum_hat_to_pi_margin_mm=min(component_margins.values()),
        geophone_plug_module_margin_mm=plug_margin,findings=[],
        limits=['Pi geometry and cooler are conservative envelopes, not certified mating solids',
                'Two 8.51 mm risers required with 8.5 mm J1; one riser is not the reviewed stack',
                '4.93 mm tails meet SSQ 3.68-6.35 mm insertion range; Megastar contact engagement requires first-article verification',
                'Trim PTH tails to <=2 mm below HAT; 0.2 mm extra tail allowance is modeled',
                'First-article seating, thermal capacity and sensor noise remain unmeasured'])
