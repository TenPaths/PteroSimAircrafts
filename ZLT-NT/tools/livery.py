"""Paint the envelope: a cylindrical sheet, u along the hull bow to tail, v around it.

v = (bearing + 180) / 360, so the crown of the hull is the middle of the sheet and the
seam falls under the keel, where nothing is drawn and nobody looks.

Drawn from a photograph of D-LZZF: a white envelope, the name in grey on the upper
flank forward of amidships, and one grey stripe low along each flank, a hand's width
amidships, that slides down and broadens towards the ends and wraps the nose in one band. The fin carries the papers: the name, the type
and the registration with the flag.

Each flank shows the sheet turned a different way. From starboard the bow is on the
viewer's right, so u runs right to left: that band is mirrored left-right. From port u
runs left to right but v runs upward -- bearing falls from the crown down the flank --
so that band is flipped top-to-bottom. Capitals flipped top-to-bottom look mirrored,
which is why the port band resisted every left-right mirror it was given. Nothing is
moved along u, which keeps the same word at the same station on either side.

  python tools/livery.py textures/envelope.png textures/fin_stbd.png textures/fin_port.png
"""
import math, sys
from PIL import Image, ImageDraw, ImageFont

W, H = 2048, 1024
WHITE = (250, 250, 248)
GREY = (112, 118, 120)
SILVER = (196, 200, 204)
BOLD = "C:/Windows/Fonts/arialbd.ttf"
PLAIN = "C:/Windows/Fonts/arial.ttf"

PORT, STARBOARD = 0.28, 0.72          # the name: 80 degrees off the crown, above the equator
NAME_AT = 500                         # the name begins a quarter of the way aft, in pixels
Z_BOW, Z_TAIL = -34.02, 41.01


RADIUS = [  # (glTF z, metres): the body of revolution, measured from the source hull
    (-34, 1.01), (-32, 2.83), (-30, 3.76), (-28, 4.69), (-26, 5.39), (-24, 5.93), (-22, 6.37), (-18, 6.64),
    (-14, 6.84), (-10, 6.98), (-6, 7.05), (8, 7.05), (12, 6.91), (16, 6.64), (20, 6.24), (24, 5.80),
    (26, 5.22), (30, 4.60), (32, 4.05), (34, 3.44), (36, 2.65), (38, 1.11), (40, 0.38),
]


def hull_radius(u):
    """The hull's radius at a station, metres, interpolated along the measured profile."""
    z = Z_BOW + u * (Z_TAIL - Z_BOW)
    for (z0, r0), (z1, r1) in zip(RADIUS, RADIUS[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return RADIUS[0][1] if z < RADIUS[0][0] else RADIUS[-1][1]


def stripe_band(z):
    """The stripe's centre height below the axis and its thickness, metres, at a station.

    Amidships and aft it is a hand's width at one height, which is why it runs out at the tail
    cone where the hull draws in above it. Forward of the full section it rises towards the axis
    and thickens, so that on the nose it becomes the broad cap that wraps the bow below the
    mooring cone -- the photographs show its upper edge climbing to the tip, not dipping under
    the chin, which is what a band at one height would do.
    """
    if z >= -16.0:
        return -2.98, 0.42
    t = min(1.0, (-16.0 - z) / 18.0)
    return -2.98 + 2.38 * t ** 1.2, 0.42 + 1.2 * t ** 1.5


def stripe_mask():
    """Where the stripe lands on the sheet: the skin within the band's height range, per station."""
    import numpy as np
    u = (np.arange(W) + 0.5) / W
    z = Z_BOW + u * (Z_TAIL - Z_BOW)
    r = np.array([hull_radius(x) for x in u])
    centre = np.array([stripe_band(x)[0] for x in z])
    width = np.array([stripe_band(x)[1] for x in z])
    bearing = np.radians((np.arange(H) + 0.5) / H * 360.0 - 180.0)
    height = r[None, :] * np.cos(bearing)[:, None]
    # The stripe ends before the tail propeller: past that the band is not painted.
    return (np.abs(height - centre[None, :]) < width[None, :] / 2.0) & (u[None, :] < 0.955)


import numpy as np
sheet = np.full((H, W, 3), WHITE, dtype=np.uint8)
# A belly a shade darker: the underside of a white hull never reads as the same white.
edge = np.minimum(np.arange(H) / H, 1.0 - np.arange(H) / H)
k = np.clip((0.12 - edge) / 0.12, 0.0, 1.0) * 0.6
sheet[:] = (np.array(WHITE)[None, None, :] + (np.array(SILVER) - np.array(WHITE))[None, None, :] * k[:, None, None]).astype(np.uint8)
sheet[stripe_mask()] = GREY
img = Image.fromarray(sheet)


# The envelope sheet is not square on the hull: 2048 px span 75.0 m along it and 1024 px span
# the 44.3 m girth, so a tile drawn square must be widened by this before it goes on, or the
# name comes out eighteen percent too tall.
ASPECT = (W / 75.03) / (H / 44.3)


def ink(layer, xy, parts, flip=Image.FLIP_LEFT_RIGHT, stretch=ASPECT):
    """Lay one line down as a single block, turned the way its flank turns the sheet.

    xy is the block's left edge and the line its ink is centred on, so a band flipped
    top-to-bottom sits at the same height as one flipped left-to-right: placed by the tile's
    corner instead, the port name came out 0.74 m nearer the crown than the starboard one.
    """
    w = max(x + ImageFont.truetype(font, size).getbbox(text)[2] for text, font, size, x, _ in parts)
    h = max(y + size for _, _, size, _, y in parts) + 30
    tile = Image.new("RGBA", (w + 20, h), (0, 0, 0, 0))
    t = ImageDraw.Draw(tile)
    for text, font, size, x, y in parts:
        t.text((x, y), text, font=ImageFont.truetype(font, size), fill=GREY + (255,))
    tile = tile.resize((max(1, int(tile.width * stretch)), tile.height), Image.LANCZOS)
    tile = tile.transpose(flip)
    box = tile.getbbox()
    x, y = xy
    layer.alpha_composite(tile, (x, y - (box[1] + box[3]) // 2))
    return tile.width


def flag(layer, xy):
    """The national flag beside the registration; mirrored like the lettering."""
    tile = Image.new("RGBA", (54, 33), (0, 0, 0, 0))
    t = ImageDraw.Draw(tile)
    for i, band in enumerate(((0, 0, 0), (221, 0, 0), (255, 206, 0))):
        t.rectangle([0, i * 11, 54, i * 11 + 11], fill=band + (255,))
    layer.alpha_composite(tile.transpose(Image.FLIP_LEFT_RIGHT), xy)


for v, flip in ((STARBOARD, Image.FLIP_LEFT_RIGHT), (PORT, Image.FLIP_TOP_BOTTOM)):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ink(layer, (NAME_AT, int(v * H)), [("ZEPPELIN", BOLD, 132, 0, 0)], flip)
    img.paste(layer, (0, 0), layer)

out = sys.argv[1] if len(sys.argv) > 1 else "envelope.png"
img.save(out)
print("wrote", out, img.size)

# The upper fin carries the papers, laid out from the photograph: the name large and high on
# the fin, ending just ahead of the hinge; the type beneath it, ending under the name's end;
# the registration in light type above the name; the flag beside it, across the hinge on the
# rudder. Each face gets a sheet of its own -- the same layout, glyphs mirrored for starboard,
# plain for port -- so nothing has to fit a chord and its mirror at once. The sheet is rigid:
# u along the hull from the leading-edge station, 11.4 m across 1024 px, v down the 5.1 m of
# span across 512, and a tile drawn square is narrowed to that aspect before it goes on.
if len(sys.argv) > 3:
    FW, FH = 1024, 512
    FIN_ASPECT = (FW / 11.4) / (FH / 5.1)
    NARROW_BOLD = "C:/Windows/Fonts/ARIALNB.TTF"
    NARROW = "C:/Windows/Fonts/ARIALN.TTF"

    def fin_x(u):
        return int(u * FW)

    def fin_y(r):
        return int((9.1 - r) / 5.1 * FH)

    def stamp(layer, right_u, r, text, font, cap_m, mirror):
        """One word, its right edge at right_u and its capitals centred on radius r."""
        size = int(round(cap_m * (FH / 5.1) / 0.716))
        f = ImageFont.truetype(font, size)
        box = f.getbbox(text)
        tile = Image.new("RGBA", (box[2] + 8, box[3] + 8), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((0, 0), text, font=f, fill=GREY + (255,))
        tile = tile.resize((max(1, int(tile.width * FIN_ASPECT)), tile.height), Image.LANCZOS)
        if mirror:
            tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
        b = tile.getbbox()
        layer.alpha_composite(tile, (fin_x(right_u) - b[2], fin_y(r) - (b[1] + b[3]) // 2))

    for path, mirror in ((sys.argv[2], True), (sys.argv[3], False)):
        fin = Image.new("RGB", (FW, FH), WHITE)
        layer = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
        # High on the fin, as on the ship, every row ending at the seam a viewer sees: the aft
        # row of the hinge fairing, z = 30.36 at every height, u = 0.82 -- so the rows end in
        # one straight line, as they do on the ship.
        stamp(layer, 0.810, 7.85, "ZEPPELIN", NARROW_BOLD, 0.48, mirror)
        stamp(layer, 0.810, 7.30, "Neue Technologie", NARROW, 0.17, mirror)
        stamp(layer, 0.810, 8.35, "D-LZNT", NARROW, 0.26, mirror)
        # The flag, on the rudder. Not right behind the hinge: at this height the fixed fin's
        # trailing edge is swept forward of the rudder's cut, and a flag at u = 0.73 fell into
        # that gap and showed as a black sliver. A flag reads the same either way round.
        tile = Image.new("RGBA", (int(0.5 * FW / 11.4), int(0.3 * FH / 5.1)), (0, 0, 0, 0))
        t = ImageDraw.Draw(tile)
        third = tile.height / 3.0
        for i, band in enumerate(((0, 0, 0), (221, 0, 0), (255, 206, 0))):
            t.rectangle([0, int(i * third), tile.width, int((i + 1) * third)], fill=band + (255,))
        layer.alpha_composite(tile, (fin_x(0.845), fin_y(8.35) - tile.height // 2))   # clear of the fairing lip
        fin.paste(layer, (0, 0), layer)
        fin.save(path)
        print("wrote", path, fin.size)
