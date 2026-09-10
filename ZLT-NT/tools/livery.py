"""Paint the envelope: a cylindrical sheet, u along the hull bow to tail, v around it.

v = (bearing + 180) / 360, so the top of the hull is the middle of the sheet and the
seam falls under the keel, where nothing is drawn and nobody looks. The real ship is
white with the type along both flanks and its registration aft; the lettering here is
the type and a registration, not any operator's mark.
"""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 2048, 1024
WHITE = (247, 247, 244)
NAVY = (20, 42, 92)
SILVER = (176, 182, 190)
BOLD = "C:/Windows/Fonts/arialbd.ttf"
PORT, STARBOARD = 0.295, 0.705   # v = (bearing + 180)/360, so +Y -- starboard -- is the far half

img = Image.new("RGB", (W, H), WHITE)
d = ImageDraw.Draw(img)

# A belly a shade darker: the underside of a white hull never reads as the same white.
for y in range(H):
    edge = min(y / H, 1.0 - y / H)
    if edge < 0.18:
        k = (0.18 - edge) / 0.18
        d.line([(0, y), (W, y)], fill=tuple(int(WHITE[i] + (SILVER[i] - WHITE[i]) * k * 0.55) for i in range(3)))

for v in (PORT, STARBOARD):
    d.line([(0, int(v * H) + 150), (W, int(v * H) + 150)], fill=NAVY, width=5)

def ink(layer, xy, parts, mirror, reverse=False):
    """Lay one line down, as one block, at the same station on either flank.

    One block, not one word each: a flank whose bow faces the viewer reads the sheet
    backwards, so the block is flipped and reads right again -- flipping word by word
    left them in the wrong order, NT ahead of ZEPPELIN, and flipping their places as
    well moved the whole line to the other end of the hull.
    """
    w = max(x + ImageFont.truetype(BOLD, size).getbbox(text)[2] for text, size, x, _ in parts)
    h = max(y + size for _, size, _, y in parts) + 40
    tile = Image.new("RGBA", (w + 20, h), (0, 0, 0, 0))
    t = ImageDraw.Draw(tile)
    for text, size, x, y in parts:
        t.text((x, y), text, font=ImageFont.truetype(BOLD, size), fill=NAVY + (255,))
    if mirror:
        tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
    layer.alpha_composite(tile, xy)


def letter(v, mirror, reverse=False):
    """One flank, drawn transparent so only the ink lands on the hull, centred on v."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = int(v * H)
    ink(layer, (500, y - 95), [("ZEPPELIN", 190, 0, 0), ("NT", 86, 990, 80)], mirror, reverse)
    ink(layer, (150, y + 60), [("D-LZNT", 62, 0, 0)], mirror, reverse)   # forward, clear of the fin
    img.paste(layer, (0, 0), layer)


# The starboard flank reads the sheet right to left, so its band is mirrored and the name
# reads true there. The port half of this hull winds its UVs the other way: photographed
# through all four combinations of mirrored band and reversed placement, the letters came
# back mirrored every time while the word order stayed put -- that is the winding, not the
# sheet, and no arrangement of ink fixes it. Giving each half its own half of the sheet
# would, at the cost of a seam along the crown. Left plain until then.
letter(STARBOARD, mirror=True)
letter(PORT, mirror=False)

out = sys.argv[1] if len(sys.argv) > 1 else "envelope.png"
img.save(out)
print("wrote", out, img.size)
