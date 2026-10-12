"""Merge native KiCad GLB with the existing PNI/PTC/SHT45 dimensional envelopes."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import trimesh
import re

ROOT = Path(__file__).resolve().parents[2]


def models(text):
    for line in text.splitlines():
        if not line or line.startswith('#'): continue
        color = [float(v) for v in re.search(r'diffuseColor ([\d. ]+)', line)[1].split()]
        if 'geometry Box' in line:
            size = [float(v)*2.54 for v in re.search(r'size ([\d.eE+ -]+)', line)[1].split()]
            offset = [float(v)*2.54 for v in re.search(r'translation ([\d.eE+ -]+)', line)[1].split()]
            mesh = trimesh.creation.box(extents=size);mesh.apply_translation(offset)
        elif 'geometry IndexedFaceSet' in line:
            points = np.fromstring(re.search(r'point \[ (.*?) \]', line)[1].replace(',', ' '), sep=' ').reshape(-1, 3)*2.54
            indices = [int(v) for v in re.search(r'coordIndex \[ (.*?)\]', line)[1].replace(',', ' ').split()]
            face, triangles = [], []
            for i in indices:
                if i == -1:
                    triangles.extend((face[0], face[j], face[j+1]) for j in range(1, len(face)-1));face=[]
                else: face.append(i)
            assert not face
            mesh = trimesh.Trimesh(points, triangles, process=False)
        else: raise ValueError('Unsupported VRML shape')
        mesh.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=[round(c*255) for c in color]+[255], metallicFactor=.25, roughnessFactor=.6))
        yield mesh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('native_glb', type=Path)
    args = parser.parse_args()
    scene = trimesh.load(args.native_glb, force='scene')
    placement = ROOT/'hw/burrowlark-usb/layout/placement.json'
    board = ROOT/'hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.kicad_pcb'
    inputs = [placement, board, Path(__file__)]
    for part in json.loads(placement.read_text())['groundlark-field-head']['parts']:
        name = {'U2': 'PNI14190', 'U7': 'PNI14190', 'U8': 'PNI14190', 'U9': 'PNI14190', 'F1': 'PTC1812', 'U6': 'SHT45'}.get(part['ref'])
        if name is None:
            continue
        model = ROOT/f'hw/shared/models/{name}.wrl'
        inputs.append(model)
        angle = math.radians(part['angle'])
        c, s = math.cos(angle), math.sin(angle)
        transform = np.array([[c,-s,0,50+part['xy'][0]], [0,0,1,1.6],
                              [-s,-c,0,50+part['xy'][1]], [0,0,0,1000]])/1000
        for index, mesh in enumerate(models(model.read_text())):
            mesh.apply_transform(transform)
            scene.add_geometry(mesh, node_name=f'{part["ref"]}-envelope-{index}')
    target = ROOT/'sw/ui/assets/burrowlark.glb'
    scene.export(target)
    inputs.append(target)
    manifest = dict(kicad='9.0.9', scope='Native routed board/stock models with existing simplified PNI/PTC/SHT45 envelopes; no physical qualification.',
                    sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    (target.parent/'burrowlark-provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Exported Burrowlark GLB', scene.bounds.tolist())


if __name__ == '__main__':
    main()
