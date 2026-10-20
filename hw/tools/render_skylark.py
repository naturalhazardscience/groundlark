"""Render the native PCB with KiCad, recording exact input hashes."""
from hardware_require import require as _require_hardware
import hashlib, json, os, shutil, subprocess
from project_paths import board_dir

def main():
    folder=board_dir('skylark-usb');board=folder/'skylark-usb.kicad_pcb';outputs=[]
    for name,side,angle in [('front','top','325,0,20'),('back','bottom','35,0,-20')]:
        output=folder/f'skylark-{name}.png'
        cmd=['kicad-cli','pcb','render','--width','1600','--height','1400','--quality','high','--background','opaque','--side',side,'--rotate',angle,'--zoom','0.85','-o',str(output),str(board)]
        if os.name!='nt' and not os.environ.get('DISPLAY'):
            _require_hardware((shutil.which('xvfb-run')), lambda: ('Install Xvfb in the rendering environment'))
            cmd=['xvfb-run','-a',*cmd]
        subprocess.run(cmd,check=True)
        outputs.append({'file':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'side':side,'rotation':angle})
    (folder/'render-provenance.json').write_text(json.dumps({'renderer':subprocess.check_output(['kicad-cli','version'],text=True).strip(),'source_board':board.name,'source_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'model_provenance':'../../models/provenance.json','images':outputs,'scope':'Native routed PCB; simplified package/cell envelopes. No enclosure or external PMS5003 shown.'},indent=2)+'\n')

if __name__=='__main__':main()
