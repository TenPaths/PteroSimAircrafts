"""Cut the hull GLB into the pieces that have to move, and rebuild the hull without them.

  python tools/cut_hull.py <the hull before it was cut> meshes

The input is the welded hull, which lives in this package's history rather than
next to the cut one: git show <the commit that added it>:ZLT-NT/meshes/zlt_nt_airframe.glb

The model arrives as one mesh with every fin and nacelle welded into it, so a
deflecting rudder or a swivelling nacelle has to be separated before Visual.xml can
hinge it. Nothing is modelled again here: triangles are moved from the hull into a
part, each part baked about its own hinge, and the hull written back without them.
Re-run it whenever the source model is updated, then check the hinge points below
still name the same seams.

glTF axes: ue_x = -z, ue_y = x, ue_z = y. The hull axis runs along z at y = 3.88,
which is how far the CG -- the origin everything is baked about -- hangs below it.
"""

import json, math, os, struct, sys

CT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

def load(path):
    b = open(path, 'rb').read()
    assert b[:4] == b'glTF', path
    off, js, bin_ = 12, None, None
    while off < len(b):
        ln, ty = struct.unpack_from('<II', b, off)
        chunk = b[off + 8: off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(chunk.decode('utf-8'))
        elif ty == 0x004E4942:
            bin_ = chunk
        off += 8 + ln + ((4 - ln % 4) % 4 if ln % 4 else 0)
    return js, bin_

def read(g, bin_, idx):
    a = g['accessors'][idx]
    bv = g['bufferViews'][a['bufferView']]
    fmt, n = CT[a['componentType']], NC[a['type']]
    size = struct.calcsize(fmt) * n
    stride = bv.get('byteStride') or size
    base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    out = []
    for i in range(a['count']):
        v = struct.unpack_from('<' + fmt * n, bin_, base + i * stride)
        out.append(v[0] if n == 1 else v)
    return out

import json, struct

def _pad(b, fill=b'\0'):
    return b + fill * ((4 - len(b) % 4) % 4)

def write_glb(path, prims, src_json, src_bin, node_name="part", translation=None):
    out_mats, mat_map, out_tex, out_img, out_smp, views, bin_ = [], {}, [], [], [], [], bytearray()

    def add_view(data, target=None):
        nonlocal bin_
        while len(bin_) % 4:
            bin_ += b'\0'
        v = {"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data)}
        if target:
            v["target"] = target
        bin_ += data
        views.append(v)
        return len(views) - 1

    def add_image(i):
        img = dict(src_json['images'][i])
        bv = src_json['bufferViews'][img['bufferView']]
        off, ln = bv.get('byteOffset', 0), bv['byteLength']
        img['bufferView'] = add_view(src_bin[off:off + ln])
        out_img.append(img)
        return len(out_img) - 1

    def add_texture(t):
        tex = dict(src_json['textures'][t])
        if 'source' in tex:
            tex['source'] = add_image(tex['source'])
        if 'sampler' in tex:
            out_smp.append(dict(src_json['samplers'][tex['sampler']]))
            tex['sampler'] = len(out_smp) - 1
        out_tex.append(tex)
        return len(out_tex) - 1

    def add_material(m):
        if m in mat_map:
            return mat_map[m]
        mat = json.loads(json.dumps(src_json['materials'][m]))
        stack = [mat]
        while stack:                                   # every *Texture holds an index into textures
            node = stack.pop()
            for k, v in list(node.items()):
                if isinstance(v, dict):
                    if k.endswith('Texture') and 'index' in v:
                        v['index'] = add_texture(v['index'])
                    stack.append(v)
        out_mats.append(mat)
        mat_map[m] = len(out_mats) - 1
        return mat_map[m]

    accessors, out_prims = [], []
    for p in prims:
        pos, nrm, uv, tris = p['pos'], p['nrm'], p['uv'], p['tris']
        idx_fmt, idx_ct = ('<H', 5123) if len(pos) < 65536 else ('<I', 5125)
        a0 = len(accessors)
        for data, n, ty, mn, mx in (
                (pos, 3, 'VEC3', [min(v[i] for v in pos) for i in range(3)], [max(v[i] for v in pos) for i in range(3)]),
                (nrm, 3, 'VEC3', None, None),
                (uv, 2, 'VEC2', None, None)):
            raw = b''.join(struct.pack('<' + 'f' * n, *v) for v in data)
            acc = {"bufferView": add_view(raw, 34962), "componentType": 5126, "count": len(data), "type": ty}
            if mn:
                acc["min"], acc["max"] = mn, mx
            accessors.append(acc)
        raw = b''.join(struct.pack(idx_fmt, i) for t in tris for i in t)
        accessors.append({"bufferView": add_view(raw, 34963), "componentType": idx_ct,
                          "count": len(tris) * 3, "type": "SCALAR"})
        out_prims.append({"attributes": {"POSITION": a0, "NORMAL": a0 + 1, "TEXCOORD_0": a0 + 2},
                          "indices": a0 + 3, "material": add_material(p['material'])})

    node = {"mesh": 0, "name": node_name}
    if translation:
        node["translation"] = list(translation)
    g = {"asset": {"version": "2.0", "generator": "PteroSim ZLT-NT part cutter"},
         "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
         "meshes": [{"name": node_name, "primitives": out_prims}],
         "accessors": accessors, "bufferViews": views,
         "buffers": [{"byteLength": len(bin_)}], "materials": out_mats}
    for key, val in (("textures", out_tex), ("images", out_img), ("samplers", out_smp)):
        if val:
            g[key] = val
    js = _pad(json.dumps(g, separators=(',', ':')).encode('utf-8'), b' ')
    bn = _pad(bytes(bin_))
    blob = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bn))
    blob += struct.pack('<II', len(js), 0x4E4F534A) + js
    blob += struct.pack('<II', len(bn), 0x004E4942) + bn
    open(path, 'wb').write(blob)
    return len(blob)

SRC = sys.argv[1]
OUT = sys.argv[2]
YAX = 3.88
HINGE_Z = 29.9      # the fin sheet doubles here: forward of it the fixed fin, aft of it the rudder
FIN_R = 3.4
ARM = 8.05          # a point on each hinge line, mid-span

g, b = load(SRC)
mesh = g['meshes'][0]

def bearing(x, y):
    return math.degrees(math.atan2(x, y - YAX))

def in_fin(lo, hi):
    def f(p):
        x, y, z = p
        return z >= HINGE_Z and math.hypot(x, y - YAX) > FIN_R and lo < bearing(x, y) < hi
    return f

def side_nacelle(sign):
    """The swivelling gear housing: outboard of the hull, below its axis, at the engine station."""
    def f(p):
        x, y, z = p
        return x * sign > 7.0 and y < 2.0 and -9.6 < z < -6.2
    return f

def aft_nacelle(p):
    x, y, z = p
    return z >= 39.11 and math.hypot(x, y - YAX) < 2.0

PARTS = [
    # name, predicate, hinge point in glTF coordinates
    ("rudder_upper", in_fin(-12, 12), (0.0, YAX + ARM, HINGE_Z)),
    ("rudder_port", in_fin(-128, -100), (ARM * math.sin(math.radians(-112)), YAX + ARM * math.cos(math.radians(-112)), HINGE_Z)),
    ("rudder_stbd", in_fin(100, 128), (ARM * math.sin(math.radians(112)), YAX + ARM * math.cos(math.radians(112)), HINGE_Z)),
    # Hinged where JSBSim swings the thrust, so the blade the core hangs off this mesh lands on its shaft.
    ("nacelle_port", side_nacelle(-1), (-8.0, 0.38, -8.87)),
    ("nacelle_stbd", side_nacelle(1), (8.0, 0.38, -8.87)),
    ("nacelle_aft", aft_nacelle, (0.0, YAX, 40.53)),
]

prims = []
for pr in mesh['primitives']:
    prims.append({
        'pos': read(g, b, pr['attributes']['POSITION']),
        'nrm': read(g, b, pr['attributes']['NORMAL']),
        'uv': read(g, b, pr['attributes']['TEXCOORD_0']),
        'idx': read(g, b, pr['indices']),
        'material': pr['material'],
    })

def compact(src, tris, shift=(0.0, 0.0, 0.0)):
    """Keep only the vertices these triangles use, renumbered, moved onto the hinge."""
    seen, pos, nrm, uv, out = {}, [], [], [], []
    for t in tris:
        nt = []
        for i in t:
            if i not in seen:
                seen[i] = len(pos)
                p = src['pos'][i]
                pos.append((p[0] - shift[0], p[1] - shift[1], p[2] - shift[2]))
                nrm.append(src['nrm'][i])
                uv.append(src['uv'][i])
            nt.append(seen[i])
        out.append(tuple(nt))
    return {'pos': pos, 'nrm': nrm, 'uv': uv, 'tris': out, 'material': src['material']}

taken = {name: [] for name, _, _ in PARTS}
hull = []
for pi, src in enumerate(prims):
    idx = src['idx']
    kept = []
    for k in range(0, len(idx), 3):
        t = (idx[k], idx[k + 1], idx[k + 2])
        where = None
        for name, pred, _ in PARTS:
            if all(pred(src['pos'][i]) for i in t):
                where = name
                break
        (taken[where] if where else kept).append(t)
    if kept:
        hull.append((pi, kept))

os.makedirs(OUT, exist_ok=True)
for name, _, hinge in PARTS:
    tris = taken[name]
    src = prims[12]
    size = write_glb(os.path.join(OUT, "zlt_nt_%s.glb" % name), [compact(src, tris, hinge)], g, b, name)
    print("%-14s %5d tris  hinge gltf=(%.2f %.2f %.2f)  ue=(%.2f %.2f %.2f)  %d bytes"
          % (name, len(tris), hinge[0], hinge[1], hinge[2], -hinge[2], hinge[0], hinge[1], size))

body = [compact(prims[pi], tris) for pi, tris in hull]
size = write_glb(os.path.join(OUT, "zlt_nt_airframe.glb"), body, g, b, "body")
print("hull           %5d tris  %d bytes" % (sum(len(t['tris']) for t in body), size))
