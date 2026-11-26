# Uso: python3 dxf_a_planta.py Planta_3D.dxf planta.json   (requiere: pip install ezdxf)
# Convierte Planta_3D.dxf a datos compactos para three.js (coordenadas de mundo de la escena).
# mundo: x = dx - 69 ; z = 205 - dy ; y = dz - terreno_dxf(dx,dy) (+ ajustes por capa)
import sys,json,base64,struct,collections,ezdxf
SRC,OUT=sys.argv[1],sys.argv[2]
doc=ezdxf.readfile(SRC);msp=doc.modelspace()
OX,OY=69,205
# --- terreno del plano (para apoyar cada objeto en el suelo plano de la escena) ---
T=[e for e in msp if e.dxftype()=='MESH' and e.dxf.layer=='3D_TERRENO'][0]
TV=[tuple(v) for v in T.vertices];TF=[list(f) for f in T.faces]
tris=[]
for f in TF:
    for k in range(1,len(f)-1):tris.append((TV[f[0]],TV[f[k]],TV[f[k+1]]))
def tz(x,y):
    best=None
    for a,b,c in tris:
        d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(d)<1e-9:continue
        l1=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d;l2=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d;l3=1-l1-l2
        if min(l1,l2,l3)>=-1e-6:return l1*a[2]+l2*b[2]+l3*c[2]
    return 0.0
def W(p,dy=0.0,ground=None):
    g=tz(p[0],p[1]) if ground is None else ground
    return (p[0]-OX, p[2]-g+dy, OY-p[1])
# --- clasificación ---
def cls_eq(cx,cy):
    if 165<=cx<=250 and 55<=cy<=95:return 'EQ_CHANCADO'
    if 250<=cx<=280 and 120<=cy<=140:return 'EQ_TAMBOR'
    if 520<=cx<=595 and 212<=cy<=235:return 'EQ_SX'
    if 520<=cx<=595 and 235<=cy<=242:return 'EQ_BOMBAS'
    if 520<=cx<=595 and 195<=cy<=212:return 'EQ_TK_SX'
    if 615<=cx<=670 and 125<=cy<=150:return 'EQ_CATODOS'
    if 540<=cx<=590 and 85<=cy<=98:return 'EQ_BIORREACTOR'
    return 'EQ_OTROS'
groups=collections.defaultdict(lambda:{'p':[],'i':[]})
heaps=[];stock=[]
def add(name,verts,faces,dy=0.0,ground=None):
    G=groups[name];base=len(G['p'])
    if ground=='min':ground=min(tz(v[0],v[1]) for v in verts)
    for v in verts:G['p'].append(W(v,dy,ground))
    for f in faces:
        for k in range(1,len(f)-1):G['i'].extend([base+f[0],base+f[k],base+f[k+1]])
for e in msp:
    if e.dxftype()!='MESH':continue
    L=e.dxf.layer;V=[tuple(v) for v in e.vertices];F=[list(f) for f in e.faces]
    xs=[v[0] for v in V];ys=[v[1] for v in V];zs=[v[2] for v in V];cx=(min(xs)+max(xs))/2;cy=(min(ys)+max(ys))/2
    if L=='3D_TERRENO':continue
    if L=='3D_PILAS':
        g=tz(cx,cy)
        if max(xs)-min(xs)>30:   # módulos de lixiviación (70 x 60 m)
            heaps.append({'x':round(cx-OX,2),'z':round(OY-cy,2),'w':round(max(xs)-min(xs),2),'d':round(max(ys)-min(ys),2),'h':round(max(zs)-min(zs),2)})
        else: stock.append({'x':round(cx-OX,2),'z':round(OY-cy,2),'r':round((max(xs)-min(xs))/2,2),'h':round(max(zs)-g,2)})
        continue
    if L=='3D_EQUIPOS':add(cls_eq(cx,cy),V,F,ground='min');continue
    if L=='3D_PISCINAS_LINER':
        if cy>280:add('LINER_PILAS',V,F,ground='min');continue  # carpeta HDPE bajo cada módulo
        add('LINER_PISCINAS',V,F,dy=4.4);continue               # piscinas sobre el terreno (bermas)
    if L.startswith('3D_SOLUCION'):add(L.replace('3D_',''),V,F,dy=4.4);continue
    if L in('3D_CELDAS_EW','3D_NAVE_EW','3D_TECHOS','3D_EDIFICIOS','3D_ESTANQUES_ACIDO','3D_ESTANQUES_AGUA','3D_SOPLADORES','3D_CORREAS','3D_RIPIOS','3D_CAMINOS'):
        add(L.replace('3D_',''),V,F,ground=('min' if L not in('3D_CAMINOS','3D_CORREAS') else None));continue
    print('sin usar',L)
# tuberías (polilíneas 3D) por tipo de solución
pipes=collections.defaultdict(list)
for e in msp:
    if e.dxftype()=='POLYLINE' and e.dxf.layer.startswith('3D_SOLUCION'):
        pts=[W(tuple(p.dxf.location)) for p in e.vertices]
        pipes[e.dxf.layer.replace('3D_SOLUCION_','')].append([[round(a,2) for a in p] for p in pts])
# textos 3D (para etiquetas)
labels=[{'t':e.dxf.text,'p':[round(a,1) for a in W(tuple(e.dxf.insert),ground=0.0)]} for e in msp if e.dxftype()=='TEXT']
def b64(fmt,arr):return base64.b64encode(struct.pack('<%d%s'%(len(arr),fmt),*arr)).decode()
out={'g':{},'heaps':heaps,'stock':stock,'pipes':pipes}
for k,G in groups.items():
    P=[int(round(c*10)) for p in G['p'] for c in p]
    assert all(-32768<=v<32768 for v in P),k
    out['g'][k]={'p':b64('h',P),'i':b64('H',G['i'])}
json.dump(out,open(OUT,'w'),separators=(',',':'),ensure_ascii=False)
json.dump(labels,open(OUT.replace('.json','-labels.json'),'w'),ensure_ascii=False,indent=0)
print('grupos',{k:(len(G['p']),len(G['i'])//3) for k,G in groups.items()})
print('módulos',len(heaps),heaps[:2]);print('acopios',len(stock),stock[:2]);print('tuberías',{k:len(v) for k,v in pipes.items()})
import os;print('tamaño',os.path.getsize(OUT),'bytes')
