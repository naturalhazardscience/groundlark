"""Author the direct USB pair and the four-wire environmental-sensor finger.

Run on the placed board before routing remaining signals. All coordinates are
relative to the outline origin. Native DRC remains required after routing.
"""
from hardware_require import require as _require_hardware
import pcbnew as p
from project_paths import board_dir
from kicad_support import v, save_board
from assemble_pcb import export_dsn

def main():
    folder=board_dir('skylark-usb');path=folder/'skylark-usb.kicad_pcb'
    b=p.LoadBoard(str(path));nets=b.GetNetsByName()
    _require_hardware((not b.GetTracks()), lambda: ('Apply fixed routes before routing other signals'))
    def route(net,pts,width=.15):
        for a,z in zip(pts,pts[1:]):
            t=p.PCB_TRACK(b);t.SetStart(v(a[0]+50,a[1]+50));t.SetEnd(v(z[0]+50,z[1]+50));t.SetWidth(p.FromMM(width));t.SetLayer(p.F_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t)
    def via(net,x,y,diam=.6,drill=.3):
        t=p.PCB_VIA(b);t.SetPosition(v(x+50,y+50));t.SetWidth(p.FromMM(diam));t.SetDrill(p.FromMM(drill));t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t)
    route('USB_DP',[(35.25,79.1625),(35.25,84.3),(35.95,85.0),(35.95,85.8625),(35.95,88.1375),(35.95,90),(35.25,90.7),(35.25,91.9),(35.75,92.4),(35.75,93.42)])
    route('USB_DM',[(34.75,79.1625),(34.75,84.3),(34.05,85.0),(34.05,85.8625),(34.05,88.1375),(34.05,90),(34.75,90.7),(34.75,91.9),(35.25,92.4),(35.25,93.42)])
    route('USB_DP',[(34.75,93.42),(34.75,94.55),(35.75,94.55),(35.75,93.42)])
    route('USB_DM',[(34.25,93.42),(34.25,92.4),(35.25,92.4)])
    route('GND',[(35,85.8625),(35,86.95)])
    via('GND',35,86.95,.6,.3)
    # One-layer wiring on the thermal finger. Vias stay above its neck.
    route('SDA',[(84.3,95.6),(83.5,95.6),(83.5,86)])
    route('SCL',[(84.3,96.4),(82.6,96.4),(82.6,85.8)])
    route('V3',[(85.7,96.4),(87,96.4),(87,92.225),(85.775,91),(85.775,87)])
    route('GND',[(85.7,95.6),(86.2,95.6),(86.2,93.5),(84.225,91.525),(84.225,91),(84.225,87)])
    for net,x,y in [('SDA',83.5,86),('SCL',82.6,85.8),('V3',85.775,87),('GND',84.225,87)]:via(net,x,y)
    save_board(str(path),b)
    export_dsn(b,folder/'skylark-usb.dsn',(.6,.3),['In1.Cu','In2.Cu'])
    print('Skylark fixed USB and environmental routes authored')

if __name__=='__main__':main()
