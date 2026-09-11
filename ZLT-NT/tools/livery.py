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

  python tools/livery.py textures/envelope.png textures/fin.png
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


def ink(layer, xy, parts, flip=Image.FLIP_LEFT_RIGHT):
    """Lay one line down as a single block, turned the way its flank turns the sheet."""
    w = max(x + ImageFont.truetype(font, size).getbbox(text)[2] for text, font, size, x, _ in parts)
    h = max(y + size for _, _, size, _, y in parts) + 30
    tile = Image.new("RGBA", (w + 20, h), (0, 0, 0, 0))
    t = ImageDraw.Draw(tile)
    for text, font, size, x, y in parts:
        t.text((x, y), text, font=ImageFont.truetype(font, size), fill=GREY + (255,))
    tile = tile.transpose(flip)
    layer.alpha_composite(tile, xy)
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
    ink(layer, (NAME_AT, int(v * H) - 72), [("ZEPPELIN", BOLD, 132, 0, 0)], flip)
    img.paste(layer, (0, 0), layer)

out = sys.argv[1] if len(sys.argv) > 1 else "envelope.png"
img.save(out)
print("wrote", out, img.size)

# The upper fin carries the papers, as the real one does. Its sheet is the fixed fin's own
# chord: u from the leading edge to the hinge at every height, v down from the tip. The chord
# at the lettering is 3.9 m across 1024 px and the span 5.1 m across 512, so a tile drawn
# square is stretched 2.65 times along u before it goes on, or the letters come out narrow.
if len(sys.argv) > 2:
    FW, FH = 1024, 512
    STRETCH = 2.65

    def ink_fin(layer, xy, parts):
        w = max(x + ImageFont.truetype(font, size).getbbox(text)[2] for text, font, size, x, _ in parts)
        h = max(y + size for _, _, size, _, y in parts) + 20
        tile = Image.new("RGBA", (w + 10, h), (0, 0, 0, 0))
        t = ImageDraw.Draw(tile)
        for text, font, size, x, y in parts:
            t.text((x, y), text, font=ImageFont.truetype(font, size), fill=GREY + (255,))
        tile = tile.resize((int(tile.width * STRETCH), tile.height), Image.LANCZOS)
        tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
        layer.alpha_composite(tile, xy)
        return tile.width

    fin = Image.new("RGB", (FW, FH), WHITE)
    layer = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    ink_fin(layer, (115, 175), [("ZEPPELIN", BOLD, 52, 0, 0), ("Neue Technologie", PLAIN, 22, 2, 58)])
    w = ink_fin(layer, (640, 118), [("D-LZNT", BOLD, 26, 0, 0)])
    # The flag sits to the right of the registration in view, so left of it on the mirrored sheet.
    tile = Image.new("RGBA", (int(54 * STRETCH), 30), (0, 0, 0, 0))
    t = ImageDraw.Draw(tile)
    for i, band in enumerate(((0, 0, 0), (221, 0, 0), (255, 206, 0))):
        t.rectangle([0, i * 10, tile.width, i * 10 + 10], fill=band + (255,))
    layer.alpha_composite(tile, (640 - tile.width - 16, 124))
    fin.paste(layer, (0, 0), layer)
    fin.save(sys.argv[2])
    print("wrote", sys.argv[2], fin.size)
