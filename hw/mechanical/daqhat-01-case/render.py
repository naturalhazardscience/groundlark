"""Render actual printed solids; electronics are clearly attributed references."""
import argparse,bpy,math,json,sys,hashlib
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'hw/releases/groundlark-case-r3'
CACHE=ROOT/'.local/case'
REF=CACHE/'reference'
config=json.loads(Path(__file__).with_name('parameters.json').read_text())
levels=json.loads((OUT/'evidence/levels.json').read_text())
hat_top=levels['hat_top'];cable_z=levels['cable_z']
stack_rotation=(Matrix.Translation((42.5,-28,0))@Matrix.Rotation(math.radians(config['stack_rotation_deg']),4,'Z')
                @Matrix.Translation((-42.5,28,0)))
assert stack_rotation.to_3x3().determinant()>0,'Reflected stack transform'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--view',default='all',choices=('all','assembly-open','assembly-closed','assembly-top','assembly-ports','assembly-power','assembly-gnss','assembly-gnss-open','cover-top','cover-interior'))
parser.add_argument('--material',default='teal',choices=('teal','clear-petg'))
parser.add_argument('--quality',default='preview',choices=('preview','high'))
parser.add_argument('--device',default='CPU',choices=('CPU','CUDA','OPTIX'))
parser.add_argument('--skip-glb',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
for site in (ROOT/'.local/case-venv/lib').glob('python*/site-packages'):sys.path.append(str(site))
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)

def mat(name,rgba,metal=0,rough=.4):
 m=bpy.data.materials.new(name);m.diffuse_color=(*rgba,1);m.use_nodes=True
 bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*rgba,1);bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=rough
 return m
materials={
 'base':mat('PETG deep teal',(.045,.17,.20),rough=.62),
 'cover':mat('PETG teal',(.07,.22,.25),rough=.62),
 'orange':mat('PETG clamp',(.95,.34,.07),rough=.62),
 'pcb':mat('PCB green',(.025,.25,.11)),
 'black':mat('IC and connector',(.025,.032,.04)),
 'metal':mat('Metal',(.55,.61,.65),.75,.28),
 'can':mat('Geophone can',(.48,.42,.23),.65,.3),
 'floor':mat('Studio',(.83,.87,.89)),
 'red':mat('Red wire',(.6,.018,.01)),
 'gold':mat('Contact gold',(.65,.40,.09),.8,.23),
}
if args.material=='clear-petg':
 for name in ('base','cover'):
  material=materials[name];nodes=material.node_tree.nodes;links=material.node_tree.links
  bs=nodes.get('Principled BSDF')
  bs.inputs['Base Color'].default_value=(.92,.95,.96,1)
  bs.inputs['Transmission Weight'].default_value=1
  bs.inputs['IOR'].default_value=1.57
  bs.inputs['Roughness'].default_value=.28
  # Approximate the layer texture and scattering of unpolished clear FDM PETG.
  pos=nodes.new('ShaderNodeNewGeometry');xyz=nodes.new('ShaderNodeSeparateXYZ')
  mult=nodes.new('ShaderNodeMath');mult.operation='MULTIPLY';mult.inputs[1].default_value=2*math.pi/.2
  wave=nodes.new('ShaderNodeMath');wave.operation='SINE'
  bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.02
  links.new(pos.outputs['Position'],xyz.inputs[0]);links.new(xyz.outputs['Z'],mult.inputs[0])
  links.new(mult.outputs[0],wave.inputs[0]);links.new(wave.outputs[0],bump.inputs['Height']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])
  volume=nodes.new('ShaderNodeVolumeScatter');volume.inputs['Density'].default_value=.035
  links.new(volume.outputs[0],nodes.get('Material Output').inputs['Volume'])

def stl(path,material):
 before=set(bpy.data.objects);bpy.ops.wm.stl_import(filepath=str(path))
 obj=next(o for o in bpy.data.objects if o not in before);obj.data.materials.clear();obj.data.materials.append(materials[material]);obj['cad_stl']=True;return obj

def cube(name,lo,hi,material):
 bpy.ops.mesh.primitive_cube_add(size=1,location=tuple((a+b)/2 for a,b in zip(lo,hi)));o=bpy.context.object;o.name=name;o.dimensions=tuple(b-a for a,b in zip(lo,hi));bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(materials[material]);return o

def cyl(name,xy,z,r,h,material):
 bpy.ops.mesh.primitive_cylinder_add(vertices=128,radius=r,depth=h,location=(*xy,z+h/2));o=bpy.context.object;o.name=name;o.data.materials.append(materials[material]);o['round_sides']=True;return o

def cut(obj,tool):
 bpy.context.view_layer.objects.active=obj
 modifier=obj.modifiers.new('Machined recess','BOOLEAN');modifier.operation='DIFFERENCE';modifier.object=tool
 bpy.ops.object.modifier_apply(modifier=modifier.name);bpy.data.objects.remove(tool,do_unlink=True)

def edge_highlight(obj,width=.12):
 modifier=obj.modifiers.new('Small edge highlight','BEVEL');modifier.width=width;modifier.segments=3
 modifier.limit_method='ANGLE'

def screw(name,xy,z,r=2.75,h=2.5):
 obj=cyl(name,xy,z,r,h,'metal')
 bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=1.3,depth=1.3,location=(*xy,z+h-.4))
 cut(obj,bpy.context.object);edge_highlight(obj,.1);return obj

def wire(name,pts,material,r=.6):
 curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=20;curve.bevel_depth=r;curve.bevel_resolution=3
 s=curve.splines.new('BEZIER');s.bezier_points.add(len(pts)-1)
 for p,v in zip(s.bezier_points,pts):p.co=v;p.handle_left_type='AUTO';p.handle_right_type='AUTO'
 o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o);o.data.materials.append(materials[material]);return o

def glb(path,transform):
 assert transform.to_3x3().determinant()>0,'Physical component import must not mirror'
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
 objects=[o for o in bpy.data.objects if o not in before]
 world={o:o.matrix_world.copy() for o in objects}
 for obj in objects:obj.parent=None;obj.matrix_world=transform@world[obj]
 return objects

base=stl(REF/'base-assembled.stl','base');cover=stl(REF/'cover-assembled.stl','cover')
stl(REF/'geophone-jaw-assembled.stl','orange');stl(REF/'cable-clamp-assembled.stl','orange')
for path in REF.glob('reference-*.stl'):
 name=path.stem[10:]
 if name in ('hat','fpga','geophone_terminals','geophone_header','geophone_plug','fpga_heatsink','j83','u80','c89','sw80','j130','u132','c135','infrasound','gnss','gnss_sma','pi','gpio_stack') or (name.startswith('pi_') and not name.startswith('pi_spacer_')):continue
 material='pcb' if name=='pi' else ('can' if name=='geophone' else 'black' if name=='gpio_stack' else 'metal')
 obj=stl(path,material)
 if name=='geophone':obj['round_sides']=True
# Physical, right-handed models. Reference STL parts already have the case pose.
extra_stack_before=set(bpy.data.objects)
pi_objects=glb(ROOT/'hw/shared/models/raspberrypi4/raspberry-pi-4b.glb',Matrix.Translation((0,0,levels['pi_bottom']+1.7)))
for obj in pi_objects:
 if obj.type!='MESH':continue
 index=int(obj.name.rsplit('-',1)[-1].split('.')[0])
 # The STEP supplies geometry and a few face colors; neutral faces need
 # presentation materials. Preserve its PCB mask and connector insulators.
 kind=('pcb' if index==0 else 'black' if index in (32,39,56,73,74,76,85,87,88)
       else 'gold' if index in range(40,55) or index in range(57,72) or index in range(77,85) else 'metal')
 material=materials[kind].copy();material.name=f'Pi4 component {index} {kind}'
 if index==0 or 9<=index<=29:
  bs=material.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(1,1,1,1)
  attribute=material.node_tree.nodes.new('ShaderNodeVertexColor');attribute.layer_name=obj.data.color_attributes[0].name
  material.node_tree.links.new(attribute.outputs['Color'],bs.inputs['Base Color'])
 obj.data.materials.clear();obj.data.materials.append(material)
# Two socket risers and the HAT socket: individual contact openings and tails.
for z,height,label in [(levels['pi_top']+2.54,8.51,'SSQ lower riser'),(levels['pi_top']+11.05,8.51,'SSQ upper riser'),(levels['hat_bottom']-8.5,8.5,'Megastar HAT socket')]:
 body=cube(label,(6.8,-5.975,z),(58.2,-1.025,z+height),'black')
 for i in range(20):
  for y in (-2.23,-4.77):
   x=8.38+i*2.54
   cut(body,cube('Contact opening',(x-.65,y-.65,z+height-1.8),(x+.65,y+.65,z+height+.1),'black'))
   cube('Gold socket contact',(x-.23,y-.23,z+height-1.6),(x+.23,y+.23,z+height-1.2),'gold')
 edge_highlight(body,.08)
for x,y,n,vertical in [(55,-12,50,False),(55,-44,50,False),(34,-28,30,True)]:
 before=set(bpy.data.objects);length=(n-1)*.5+5.7
 cube('LSHM housing',(x-length/2,y-2.3,hat_top),(x+length/2,y+2.3,hat_top+3.5),'black')
 cube('LSHM mating channel',(x-length/2+1,y-.65,hat_top+3.5),(x+length/2-1,y+.65,hat_top+4),'black')
 for i in range(n):
  xx=x+(i-(n-1)/2)*.5
  for sign in (-1,1):
   yy=y+sign*1.95
   cube('LSHM contact',(xx-.1,yy-.3,hat_top+.1),(xx+.1,yy+.3,hat_top+.45),'gold')
 if vertical:
  turn=Matrix.Translation((x,y,0))@Matrix.Rotation(math.pi/2,4,'Z')@Matrix.Translation((-x,-y,0))
  for obj in set(bpy.data.objects)-before:obj.matrix_world=turn@obj.matrix_world
# Actual generated HAT model. glTF Y-up becomes Blender Z-up on import.
transform=Matrix(((1000,0,0,-50),(0,1000,0,50),(0,0,1000,hat_top-1.4684),(0,0,0,1)))
glb(ROOT/'sw/ui/assets/daqhat-01.glb',transform)
# KiCad GLB omits local VRML: explicit conservative custom body envelopes.
jack=cube('PJ-102AH body',(90.5,-14.6,hat_top),(99.5,-.2,hat_top+11),'black')
bore=cyl('Barrel opening',(95,-.2),hat_top+6.5,2.8,3,'black')
bore.rotation_euler.x=math.pi/2
bore.location=(95,-1.5,hat_top+6.5)
cut(jack,bore)
pin=cyl('Center positive pin',(95,-.2),hat_top+6.5,1,2,'metal')
pin.rotation_euler.x=math.pi/2;pin.location=(95,-1.4,hat_top+6.5)
cube('TPSM53603 FPGA envelope',(92.5,-34.75,hat_top),(97.5,-29.25,hat_top+4),'black')
cube('TPSM53603 Pi envelope',(121.5,-30.75,hat_top),(126.5,-25.25,hat_top+4),'black')
cube('SDP32 envelope',(1.75,-31.75,hat_top),(10.25,-26.25,hat_top+2.2),'black')
for x in (3.85,8.15):cyl('SDP32 port',(x,-28.35),hat_top+2.2,1,2.2,'black')
# Manufacturer TE0712 geometry, individually tessellated and approximately colored.
for item in json.loads((CACHE/'fpga-bodies.json').read_text()):stl(CACHE/(item['name']+'.stl'),item['color'])
# Illustrative molded details stay inside the conservative plug fit envelope.
# They are presentation geometry, not a substitute for manufacturer mating CAD.
plug=cube('1803581 plug reference',(8.08,-75,hat_top),(20.3,-58.9,hat_top+11.1),'pcb')
for x in (10.38,14.19,18):
 cut(plug,cyl('Screw well',(x,-69),hat_top+7.9,1.55,3.5,'black'))
 head=cyl('Terminal screw',(x,-69),hat_top+7.95,1.3,.75,'metal')
 cut(head,cube('Screw slot',(x-1.4,-69.24,hat_top+8.4),(x+1.4,-68.76,hat_top+8.9),'black'))
 cut(plug,cube('Wire entry',(x-1.35,-75.1,hat_top+1.5),(x+1.35,-71.5,hat_top+5.7),'black'))
edge_highlight(plug,.12)
# Reference meshes already have the case pose; place the additional native
# HAT/vendor meshes and connector bodies using the same physical rotation.
for obj in set(bpy.data.objects)-extra_stack_before:obj.matrix_world=stack_rotation@obj.matrix_world
# Bare geophone terminals and wiring are illustrative within the reserved envelope.
cyl('Geophone top',(42,25),40.8,12.4,.7,'black')
for x in (37,47):
 cyl('Terminal insulator',(x,25),41.5,1.5,.8,'black')
 cyl('Geophone terminal',(x,25),41.5,.7,5,'metal')
wire('Geophone positive',[(37,25,46),(48,29,48),(54,26,cable_z+.5)],'red',.55)
wire('Geophone negative',[(47,25,46),(51,25,47),(54,26,cable_z-.5)],'black',.55)
lead=([(54,26,cable_z),(62,26,cable_z),(69,25,cable_z),(70.81,19,cable_z)] if config['stack_rotation_deg']==180
      else [(54,26,cable_z),(70,35,cable_z),(90,0,cable_z),(90,-65,cable_z),(14.19,-75,cable_z)])
wire('Shielded lead to J90',lead,'black',1.6)
# Captive nut/screw representations; not printable components.
for yy in (43.2,6.8):
 o=cyl('M3 geophone screw',(0,0),0,2.75,3,'metal');o.rotation_euler[1]=math.pi/2;o.location=(33.5,yy,19)
for x,y in [(x,-y) for x,y in config['leveling_feet']]:cyl('Metal leveling contact',(x,y),-5,3.5,5,'metal')
for y in (31.2,20.8):screw('Cable clamp screw',(59,y),cable_z+5)
# Render settings.
# Preserve planar CAD faces; smooth STL normals create swollen edges and waves.
for obj in bpy.context.scene.objects:
 if obj.type=='MESH' and (obj.get('cad_stl') or obj.get('round_sides')):
  for face in obj.data.polygons:face.use_smooth=bool(obj.get('round_sides') and abs(face.normal.z)<.5)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=40;scene.cycles.use_denoising=True
if args.material=='clear-petg':
 scene.cycles.samples=96;scene.cycles.transmission_bounces=8;scene.cycles.volume_bounces=2
scene.render.resolution_x=1500;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
if args.quality=='high':
 scene.render.resolution_x=4000;scene.render.resolution_y=2933
 scene.cycles.samples=384;scene.cycles.adaptive_threshold=.01
 scene.cycles.max_bounces=16;scene.cycles.transmission_bounces=12
 scene.render.image_settings.color_depth='8';scene.render.image_settings.compression=70
if args.device!='CPU':
 preferences=bpy.context.preferences.addons['cycles'].preferences
 preferences.compute_device_type=args.device;preferences.get_devices()
 enabled=[d for d in preferences.devices if d.type==args.device]
 if not enabled:raise RuntimeError(f'No {args.device} rendering device available')
 for device in preferences.devices:device.use=device in enabled
 scene.cycles.device='GPU'
scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.75,.80,.85,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
cube('Studio floor',(-400,-400,-6),(500,400,-5.7),'floor')
for name,pos,power,size in [('Key',(30,-130,250),650000,180),('Fill',(-140,70,180),350000,150),('Rim',(250,100,190),500000,130)]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((60,0,25))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';scene.camera=cam

def render(name,pos,target,scale):
 if args.view!='all' and name!=args.view+'.png':return
 cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
 suffix='-clear-petg' if args.material=='clear-petg' else ''
 if args.quality=='high':suffix+='-4k'
 scene.render.filepath=str(OUT/'preview'/(Path(name).stem+suffix+'.png'));bpy.ops.render.render(write_still=True)
 inputs=[Path(__file__),Path(__file__).with_name('parameters.json'),Path(__file__).with_name('case.py'),
         Path(__file__).with_name('prepare_preview.py'),ROOT/'sw/ui/assets/daqhat-01.glb',
         ROOT/'hw/shared/models/trenz/STP-TE0712-03-No Variations.step',
         ROOT/'hw/shared/models/raspberrypi4/raspberry-pi-4b.glb',ROOT/'hw/shared/models/raspberrypi4/provenance.json',
         ROOT/'hw/shared/models/raspberrypi4/mesh-provenance.json',Path(__file__).with_name('prepare_components.py'),
         ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb',
         OUT/'evidence/levels.json',CACHE/'fpga-bodies.json',*sorted(REF.glob('*.stl'))]
 inputs += [CACHE/(item['name']+'.stl') for item in json.loads((CACHE/'fpga-bodies.json').read_text())]
 digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 provenance=dict(renderer='Blender '+bpy.app.version_string,engine='Cycles',device=args.device,
     resolution=[scene.render.resolution_x,scene.render.resolution_y],samples=scene.cycles.samples,
     material=args.material,view=Path(name).stem,camera=dict(position=pos,target=target,orthographic_scale=scale),
     image_sha256=digest(Path(scene.render.filepath)),
     source_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in inputs},
     scope='R3 physical enclosure CAD, native routed HAT, manufacturer Trenz STEP and detailed attributed Pi 4 component CAD. Risers include individual contact cavities; cable plugs, geophone terminals and fasteners remain authored reference geometry.',
     handedness=dict(physical_frame='Z up, board Y down converted once to physical -Y',hat_import_determinant=transform.to_3x3().determinant(),stack_rotation_determinant=stack_rotation.to_3x3().determinant()),
     attribution='Pi 4B model: integrated-circuit / FreeCAD community library, CC-BY-3.0; see hw/shared/models/raspberrypi4/provenance.json. Trenz geometry: Trenz Electronic. KiCad component library attribution retained.',
     limitations='Clear PETG is an approximate unpolished FDM material. Plug details and lead dressing are illustrative. Physical fit and print transparency remain unqualified.')
 Path(scene.render.filepath).with_suffix('.json').write_text(json.dumps(provenance,indent=2)+'\n')
cover.location.x=-190
render('assembly-gnss-open.png',(250,-300,275),(-65,-6,28),390)
render('assembly-open.png',(-230,300,250),(-65,-4,29),410)
render('assembly-top.png',(-65,-7,350),(-65,-7,0),380)
cover.hide_render=True
render('assembly-ports.png',(-170,205,150),(30,-8,27),210)
cover.hide_render=False
cover.location.x=0
render('assembly-gnss.png',(220,-215,210),(20,-6,32),230)
render('assembly-power.png',(-175,-240,180),(25,-10,37),235)
render('assembly-closed.png',(-175,240,205),(42,-6,37),235)
# Save an interactive assembly model without studio elements/lights/camera.
for o in bpy.context.selected_objects:o.select_set(False)
for o in scene.objects:
 if o.type=='MESH' and o.name!='Studio floor':o.select_set(True)
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.001
if not args.skip_glb:
 bpy.ops.export_scene.gltf(filepath=str(OUT/'preview'/('case-assembly'+('-clear-petg' if args.material=='clear-petg' else '')+'.glb')),use_selection=True,export_format='GLB')
# A lid-only top view makes the mark and the space between vents easy to inspect.
for obj in scene.objects:
 if obj.type in ('MESH','CURVE') and obj!=cover and obj.name!='Studio floor':obj.hide_render=True
render('cover-top.png',(43,-7,300),(43,-7,0),180)
cover.matrix_world=Matrix.Translation((0,-14,75))@Matrix.Rotation(math.pi,4,'X')
render('cover-interior.png',(230,250,280),(43,-7,35),235)
print('Rendered physical CAD views'+('' if args.skip_glb else ' and exported interactive assembly'))
