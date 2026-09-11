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

def write_glb(path, prims, src_json, src_bin, node_name="part", translation=None, paint=None):
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

    painted = {}

    def add_painted(png, wrap=10497):
        """One copy of the sheet per file, however many materials wear it."""
        if (png, wrap) not in painted:
            out_img.append({"mimeType": "image/png", "bufferView": add_view(open(png, 'rb').read())})
            out_smp.append({"magFilter": 9729, "minFilter": 9987, "wrapS": wrap, "wrapT": wrap})
            out_tex.append({"source": len(out_img) - 1, "sampler": len(out_smp) - 1})
            painted[(png, wrap)] = len(out_tex) - 1
        return painted[(png, wrap)]

    def add_material(m, paint_as=None):
        key = (m, paint_as[0] if paint_as else None)
        if key in mat_map:
            return mat_map[key]
        mat = json.loads(json.dumps(src_json['materials'][m]))
        png = (paint or {}).get(mat.get('name'))
        if png or paint_as:
            # Painted over below, so the model's own base colour texture is dropped before the
            # walk that would embed it: carried across and then replaced, it sat in the file as
            # an image nothing referenced.
            mat.get('pbrMetallicRoughness', {}).pop('baseColorTexture', None)
        stack = [mat]
        while stack:                                   # every *Texture holds an index into textures
            node = stack.pop()
            for k, v in list(node.items()):
                if isinstance(v, dict):
                    if k.endswith('Texture') and 'index' in v:
                        v['index'] = add_texture(v['index'])
                    stack.append(v)
        if png and not paint_as:
            # The sheet replaces whatever the model shipped: these materials carried a
            # 169-byte placeholder or nothing at all, and a white hull is not a livery.
            pbr = mat.setdefault('pbrMetallicRoughness', {})
            pbr['baseColorTexture'] = {"index": add_painted(png)}
            pbr.pop('baseColorFactor', None)
        if paint_as:
            # The same material under another name: wearing its own sheet (the fin's), or none
            # at all (the pods, which the envelope sheet had painted with the stripe).
            mat['name'] = paint_as[0]
            pbr = mat.setdefault('pbrMetallicRoughness', {})
            pbr.pop('baseColorFactor', None)
            pbr.pop('baseColorTexture', None)
            if paint_as[1]:
                pbr['baseColorTexture'] = {"index": add_painted(paint_as[1], paint_as[2])}
            else:
                pbr['baseColorFactor'] = [0.98, 0.98, 0.97, 1.0]
        out_mats.append(mat)
        mat_map[key] = len(out_mats) - 1
        return mat_map[key]

    accessors, out_prims = [], []
    for p in prims:
        pos, nrm, uv, tris = p['pos'], p['nrm'], p['uv'], p['tris']
        idx_fmt, idx_ct = ('<H', 5123) if len(pos) < 65536 else ('<I', 5125)
        a0 = len(accessors)
        for data, n, ty, bounded in ((pos, 3, 'VEC3', True), (nrm, 3, 'VEC3', False), (uv, 2, 'VEC2', False)):
            raw = b''.join(struct.pack('<' + 'f' * n, *v) for v in data)
            mn = mx = None
            if bounded:
                # Bounds taken from what was written, not from the doubles: a min a hair below the
                # float32 the file holds is what a validator flags as an accessor out of its bounds.
                stored = struct.unpack('<' + 'f' * (n * len(data)), raw)
                mn = [min(stored[i::n]) for i in range(n)]
                mx = [max(stored[i::n]) for i in range(n)]
            acc = {"bufferView": add_view(raw, 34962), "componentType": 5126, "count": len(data), "type": ty}
            if mn:
                acc["min"], acc["max"] = mn, mx
            accessors.append(acc)
        raw = b''.join(struct.pack(idx_fmt, i) for t in tris for i in t)
        accessors.append({"bufferView": add_view(raw, 34963), "componentType": idx_ct,
                          "count": len(tris) * 3, "type": "SCALAR"})
        out_prims.append({"attributes": {"POSITION": a0, "NORMAL": a0 + 1, "TEXCOORD_0": a0 + 2},
                          "indices": a0 + 3, "material": add_material(p['material'], p.get('paint_as'))})

    node = {"mesh": 0, "name": node_name}
    if translation:
        node["translation"] = list(translation)
    used = sorted({ext for mat in out_mats for ext in mat.get('extensions', {})})
    g = {"asset": {"version": "2.0", "generator": "PteroSim ZLT-NT part cutter"},
         "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
         "meshes": [{"name": node_name, "primitives": out_prims}],
         "accessors": accessors, "bufferViews": views,
         "buffers": [{"byteLength": len(bin_)}], "materials": out_mats}
    for key, val in (("textures", out_tex), ("images", out_img), ("samplers", out_smp), ("extensionsUsed", used)):
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
LIVERY = sys.argv[3] if len(sys.argv) > 3 else None    # a PNG for the envelope, laid out by sheet_uv
# Two PNGs for the upper fin, one per face, laid out by fin_uv: starboard then port.
FIN_SHEETS = (sys.argv[4], sys.argv[5]) if len(sys.argv) > 5 else None
POD = ('Pod', None, None)     # plain white: the pods and their pylons carry no livery
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
    """The pod that swivels, outboard of its pylon.

    On the ship the whole pod turns on the end of its pylon. The pylon runs from the hull at
    x = 7.30 out to x = 8.3; the pod is the bulb beyond it, and only the bulb is cut -- cut
    from x = 7.0 the pylon came with it and swung into the hull.
    """
    def f(p):
        x, y, z = p
        return x * sign > 8.3 and y < 2.0 and -9.3 < z < -7.15
    return f

def aft_nacelle(p):
    """The aft shaft and spinner, which turn with the tail engine.

    Not the cone ahead of them: that is the lateral thruster's housing, offset to port at
    z = 39.0..39.5, and it is fixed -- its own propeller hangs off the hull, so cut with the
    shaft the housing tilted away from its blade.
    """
    x, y, z = p
    return z >= 39.9 and math.hypot(x, y - YAX) < 0.5

PARTS = [
    # name, predicate, hinge point in glTF coordinates
    ("rudder_upper", in_fin(-12, 12), (0.0, YAX + ARM, HINGE_Z)),
    # The lower fins lie 115 degrees off the crown -- measured on the mesh, not the 112 first
    # assumed -- and a hinge 3 degrees out of a fin's plane walks its rudder tip 0.2 m at full travel.
    ("rudder_port", in_fin(-128, -100), (ARM * math.sin(math.radians(-115)), YAX + ARM * math.cos(math.radians(-115)), HINGE_Z)),
    ("rudder_stbd", in_fin(100, 128), (ARM * math.sin(math.radians(115)), YAX + ARM * math.cos(math.radians(115)), HINGE_Z)),
    # Hinged where JSBSim swings the thrust, so the blade the core hangs off this mesh lands on its shaft.
    # Hinged a little aft of the bulb's middle: the nose with the propeller swings up, the
    # tail dips, and neither reaches the pylon.
    ("nacelle_port", side_nacelle(-1), (-8.53, 0.38, -8.45)),
    ("nacelle_stbd", side_nacelle(1), (8.53, 0.38, -8.45)),
    ("nacelle_aft", aft_nacelle, (0.0, YAX, 40.53)),
]

ENVELOPE_MATERIALS = ('Envelope', 'Envelope.002', 'Envelope.003')
Z_BOW, Z_TAIL = -34.02, 41.01     # the hull ends, and the span u is measured over


def sheet_uv(p):
    """Where a point on the hull lands on the sheet: u bow to tail, v round the axis."""
    u = (p[2] - Z_BOW) / (Z_TAIL - Z_BOW)
    return u, (math.degrees(math.atan2(p[0], p[1] - YAX)) + 180.0) / 360.0


def unwrap(src):
    """Wrap the sheet round the hull, splitting the triangles that cross the seam.

    The model arrives with the whole texture square on every single triangle, which is
    no unwrap at all: lettering on it would repeat once per face. Triangles straddling
    the seam -- which runs under the keel, where nobody looks -- get their own copies of
    the vertices a full turn along, so the sheet does not run backwards across them.
    """
    seen, pos, nrm, uv, idx = {}, [], [], [], []
    src_idx = src['idx']
    for k in range(0, len(src_idx), 3):
        tri = (src_idx[k], src_idx[k + 1], src_idx[k + 2])
        vs = [sheet_uv(src['pos'][i])[1] for i in tri]
        straddles = max(vs) - min(vs) > 0.5
        for i, v in zip(tri, vs):
            turn = 1.0 if (straddles and v < 0.5) else 0.0
            key = (i, turn)
            if key not in seen:
                seen[key] = len(pos)
                p = src['pos'][i]
                pos.append(p)
                nrm.append(src['nrm'][i])
                u, vv = sheet_uv(p)
                uv.append((u, vv + turn))
            idx.append(seen[key])
    return dict(src, pos=pos, nrm=nrm, uv=uv, idx=idx)


prims = []
for pr in mesh['primitives']:
    prims.append({
        'pos': read(g, b, pr['attributes']['POSITION']),
        'nrm': read(g, b, pr['attributes']['NORMAL']),
        'uv': read(g, b, pr['attributes']['TEXCOORD_0']),
        'idx': read(g, b, pr['indices']),
        'material': pr['material'],
    })
for i, src in enumerate(prims):
    if g['materials'][src['material']]['name'] in ENVELOPE_MATERIALS:
        prims[i] = unwrap(src)

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

# 'Envelope' is not the envelope: it is the car's shell, x within 1.05 m of the centreline and
# hanging 2.8..5.2 m below the axis. Left off the sheet, it stays white, as the ship's car is.
PAINT = {m: LIVERY for m in ENVELOPE_MATERIALS if m != 'Envelope'} if LIVERY else None

# Only Envelope.002 is cut: the fins and the housings are its own separate sheets, open at
# their roots. The body of revolution underneath is Envelope.003, and a radius test alone
# took its skin out with the rudders -- 22 triangles, and a hole under every one.
CUT_FROM = 'Envelope.002'

taken = {name: [] for name, _, _ in PARTS}
hull = []
for pi, src in enumerate(prims):
    idx = src['idx']
    kept = []
    cuttable = g['materials'][src['material']]['name'] == CUT_FROM
    for k in range(0, len(idx), 3):
        t = (idx[k], idx[k + 1], idx[k + 2])
        where = None
        if cuttable:
            for name, pred, _ in PARTS:
                if all(pred(src['pos'][i]) for i in t):
                    where = name
                    break
        (taken[where] if where else kept).append(t)
    if kept:
        hull.append((pi, kept))

FIN_LE, FIN_TE = 21.0, 32.4   # the upper fin's leading edge and the rudder's trailing edge
CLAMP = 33071                 # glTF CLAMP_TO_EDGE: past the hinge the fin sheet holds its last column, white


def upper_fin(p):
    """The fixed part of the upper fin: the sheet ahead of the rudder hinge."""
    x, y, z = p
    return FIN_LE < z < HINGE_Z and math.hypot(x, y - YAX) > FIN_R and -12 < bearing(x, y) < 12


def fin_uv(prim, shift=(0.0, 0.0, 0.0)):
    """The fin on flat sheets: u along z from the leading-edge station, v down from the tip.

    Rigid, not fitted to the chord: the leading edge and the hinge are both swept, and a sheet
    stretched to the chord at every height sheared every glyph forty degrees. Laid out rigidly
    the lettering has to sit where the chord is at its own height, which livery.py does.

    One sheet per face, so each face is lettered for itself and nothing is mirrored in the
    mapping. Which face a triangle belongs to is decided by where its corners lie on average:
    the ridge vertices along the leading edge, the tip and the trailing edge sit at |x| below
    a micrometre with float-noise signs, and judged one by one they handed the edge triangles
    corners from both faces, which smeared the whole sheet into a strip along every edge. A
    ridge vertex used by both faces is written once per face.
    """
    pos, nrm, tris = prim['pos'], prim['nrm'], prim['tris']
    faces = []
    for side, name, sheet in ((1, 'FinStbd', FIN_SHEETS[0]), (-1, 'FinPort', FIN_SHEETS[1])):
        seen, npos, nnrm, nuv, ntris = {}, [], [], [], []
        for t in tris:
            if (-1 if sum(pos[i][0] for i in t) < 0.0 else 1) != side:
                continue
            nt = []
            for i in t:
                if i not in seen:
                    seen[i] = len(npos)
                    x, y, z = pos[i]
                    npos.append(pos[i])
                    nnrm.append(nrm[i])
                    nuv.append(((z + shift[2] - FIN_LE) / (FIN_TE - FIN_LE),
                                1.0 - (math.hypot(x, y + shift[1] - YAX) - 4.0) / (9.1 - 4.0)))
                nt.append(seen[i])
            ntris.append(tuple(nt))
        if ntris:
            faces.append(dict(prim, pos=npos, nrm=nnrm, uv=nuv, tris=ntris, paint_as=(name, sheet, CLAMP)))
    return faces


def pylon(p):
    """The side pods' pylons, left on the hull when the pods are cut: white, like the pods."""
    x, y, z = p
    return abs(x) > 7.0 and y < 2.0 and -9.6 < z < -6.2


def car(p):
    """The part of the car's shell that Envelope.002 carries: white, not the belly of the sheet."""
    x, y, z = p
    return abs(x) < 1.25 and y < -2.7 and -17.5 < z < -6.0


os.makedirs(OUT, exist_ok=True)
for name, _, hinge in PARTS:
    tris = taken[name]
    src = prims[12]
    parts = [compact(src, tris, hinge)]
    if name == "rudder_upper" and FIN_SHEETS:
        parts = fin_uv(parts[0], hinge)   # the rudder continues the fin's sheets, so the flag can sit on it
    if name.startswith("nacelle"):
        parts[0]['paint_as'] = POD
    size = write_glb(os.path.join(OUT, "zlt_nt_%s.glb" % name), parts, g, b, name, paint=PAINT)
    print("%-14s %5d tris  hinge gltf=(%.2f %.2f %.2f)  ue=(%.2f %.2f %.2f)  %d bytes"
          % (name, len(tris), hinge[0], hinge[1], hinge[2], -hinge[2], hinge[0], hinge[1], size))

body = []
for pi, tris in hull:
    src = prims[pi]
    if FIN_SHEETS and g['materials'][src['material']]['name'] == CUT_FROM:
        fin = {t for t in tris if all(upper_fin(src['pos'][i]) for i in t)}
        plain = {t for t in tris if t not in fin and all(pylon(src['pos'][i]) or car(src['pos'][i]) for i in t)}
        body.append(compact(src, [t for t in tris if t not in fin and t not in plain]))
        body.extend(fin_uv(compact(src, sorted(fin))))
        body.append(dict(compact(src, sorted(plain)), paint_as=POD))
        print("upper fin      %5d tris  on its own sheets;  pylons and car %d tris plain" % (len(fin), len(plain)))
    else:
        body.append(compact(src, tris))
size = write_glb(os.path.join(OUT, "zlt_nt_airframe.glb"), body, g, b, "body", paint=PAINT)
print("hull           %5d tris  %d bytes" % (sum(len(t['tris']) for t in body), size))
