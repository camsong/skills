# -*- coding: utf-8 -*-
"""Pull slide screenshots out of a talk video. Needs ffmpeg and Pillow.

  python3 slides.py sheet <video> <out.png> <m:ss> [<m:ss> ...]
      Contact sheet of frames at those times, 3 per row, each labelled with its time.
      Look at it to decide which frames show a slide worth keeping.

  python3 slides.py grid <video> <time> <out.png>
      One full-size frame with a 50 px / 100 px coordinate grid. Read crop boxes off it.

  python3 slides.py crop <video> <time> <x0,y0,x1,y1> <out.png> [--mask cx,cy,r] [--bg x,y]
      Crop the slide. --mask paints a circle (the presenter's camera bubble) plus the
      area below-right of it with the colour sampled at --bg, so a slide that runs
      under the bubble can still be cropped whole.

  python3 slides.py check <out.png> crop1.png crop2.png ...
      Sheet of finished crops on a grey background. Verify every edge is complete
      (titles, boxes, footnotes) and no camera or caption bar remains.
"""
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw


def frame(video, t):
    fd, path = tempfile.mkstemp(suffix='.png'); os.close(fd)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', t, '-i', video, '-frames:v', '1', path], check=True)
    im = Image.open(path).convert('RGB'); os.remove(path)
    return im


def sheet(images, labels, out, cols=3, cell=(640, 400), pad=8, bg=(128, 128, 128)):
    rows = (len(images) + cols - 1) // cols
    W, H = cols * (cell[0] + pad) + pad, rows * (cell[1] + pad + 22) + pad
    canvas = Image.new('RGB', (W, H), bg); d = ImageDraw.Draw(canvas)
    for k, (im, lab) in enumerate(zip(images, labels)):
        im = im.copy(); im.thumbnail(cell)
        x = pad + (k % cols) * (cell[0] + pad); y = pad + (k // cols) * (cell[1] + pad + 22)
        canvas.paste(im, (x, y + 22)); d.text((x + 4, y + 4), lab, fill=(255, 255, 255))
    canvas.save(out); print(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == 'sheet':
        video, out, times = a[0], a[1], a[2:]
        sheet([frame(video, t) for t in times], times, out)
    elif cmd == 'grid':
        im = frame(a[0], a[1]); d = ImageDraw.Draw(im)
        for x in range(0, im.width, 50):
            d.line([(x, 0), (x, im.height)], fill=(255, 0, 0) if x % 100 == 0 else (255, 170, 170), width=1)
        for y in range(0, im.height, 50):
            d.line([(0, y), (im.width, y)], fill=(255, 0, 0) if y % 100 == 0 else (255, 170, 170), width=1)
        im.save(a[2]); print(a[2], im.size)
    elif cmd == 'crop':
        video, t, box, out = a[0], a[1], tuple(int(v) for v in a[2].split(',')), a[3]
        im = frame(video, t)
        if '--mask' in a:
            cx, cy, r = (int(v) for v in a[a.index('--mask') + 1].split(','))
            bx, by = (int(v) for v in a[a.index('--bg') + 1].split(','))
            color = im.getpixel((bx, by)); d = ImageDraw.Draw(im)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
            d.rectangle((cx - r + 10, cy, im.width, im.height), fill=color)
        im.crop(box).save(out); print(out, box)
    elif cmd == 'check':
        paths = a[1:]
        sheet([Image.open(p).convert('RGB') for p in paths], [os.path.basename(p) for p in paths], a[0], cols=2,
              cell=(900, 560))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
