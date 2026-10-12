"""Render the native magnetometer and climate PCB without modifying its CAD."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct

import pcbnew
from burrowlark_checks import population
from project_paths import ROOT, board_dir


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = board_dir('groundlark-field-head')
    source = folder / 'groundlark-field-head.kicad_pcb'
    board = pcbnew.LoadBoard(str(source))
    population(fp.GetReference() for fp in board.GetFootprints())
    before = digest(source)
    models = {}
    for fp in board.GetFootprints():
        for model in fp.Models():
            if not model.m_Show:
                continue
            variables = {
                'KIPRJMOD': str(folder),
                'KICAD9_3DMODEL_DIR': os.environ.get('KICAD9_3DMODEL_DIR', '/usr/share/kicad/3dmodels'),
            }
            resolved = re.sub(r'\$\{([^}]+)\}', lambda m: variables.get(m[1], os.environ.get(m[1], m[0])), model.m_Filename)
            path = Path(resolved).resolve(strict=True)
            models[model.m_Filename] = digest(path)
    output = folder / '3d.png'
    command = ['kicad-cli', 'pcb', 'render', '--width', '2600', '--height', '1600',
               '--quality', 'high', '--background', 'opaque', '--side', 'top',
               '--rotate', '325,0,25', '--zoom', '0.9', '-o', str(output), str(source)]
    if os.name != 'nt' and not os.environ.get('DISPLAY'):
        if not shutil.which('xvfb-run'):
            raise RuntimeError('Install Xvfb for headless KiCad rendering')
        command = ['xvfb-run', '-a', *command]
    subprocess.run(command, check=True)
    if digest(source) != before:
        raise RuntimeError('Source PCB changed during rendering')
    provenance = {
        'renderer': subprocess.check_output(['kicad-cli', 'version'], text=True).strip(),
        'source_board': source.name, 'source_sha256': before,
        'generator': 'hw/tools/render_burrowlark.py',
        'generator_sha256': digest(Path(__file__)),
        'models_sha256': models,
        'images': [{'file': output.name, 'sha256': digest(output), 'side': 'top',
                    'rotation': '325,0,25', 'zoom': 0.9, 'size_px': list(struct.unpack('>II', output.read_bytes()[16:24]))}],
        'scope': 'Native 96 x 70 mm routed DAQUSB-01 B1 PCB with four aligned RM3100 modules and SHT45 U6/C10; U3/C5 absent. '
                 'PNI14190, PTC and SHT45 bodies are simplified dimensional envelopes. '
                 'No enclosure or cable shown; physical qualification remains pending.',
    }
    (folder / 'render-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(output.relative_to(ROOT))


if __name__ == '__main__':
    main()
