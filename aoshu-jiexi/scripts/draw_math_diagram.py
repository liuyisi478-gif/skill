"""Render deterministic math-diagram scenes to PNG plus an SVG source.

python draw_math_diagram.py SCENE.json OUT.png [--font C:/Windows/Fonts/simsun.ttc]
Requires Pillow. Coordinates and labels come from a checked mathematical model;
this renderer does not infer geometry from a scanned picture.
"""
import argparse
import json
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)


def render(scene, output, font_path=None):
    width, height = scene.get('size', [1000, 600])
    if not (100 <= width <= 10000 and 100 <= height <= 10000):
        raise ValueError('Invalid scene dimensions')
    scale = scene.get('scale', 3)
    if not isinstance(scale, (int, float)) or not 1 <= scale <= 6:
        raise ValueError('scale must be between 1 and 6')
    font_path = font_path or scene.get('font')
    if not font_path:
        font_path = next((str(p) for p in [Path('C:/Windows/Fonts/simsun.ttc'),
                          Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
                          if p.is_file()), None)
    if not font_path or not Path(font_path).is_file():
        raise ValueError('Supply an installed CJK-capable font with --font')
    points = scene.get('points', {})

    def point(value):
        p = points[value] if isinstance(value, str) else value
        if len(p) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p):
            raise ValueError('Point must contain two finite coordinates')
        if not (0 <= p[0] <= width and 0 <= p[1] <= height):
            raise ValueError('Point outside scene: ' + str(value))
        return tuple(p)

    for value in points.values():
        point(value)
    # Optional analytic constraints apply to 2D diagrams, not an oblique solid
    # projection. They expose incorrect intersections/parallel lines early.
    for c in scene.get('constraints', []):
        ps = [point(p) for p in c['points']]
        if c['type'] == 'on_segment':
            p, a, b = ps
            cross = (p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0])
            dot = (p[0]-a[0])*(p[0]-b[0])+(p[1]-a[1])*(p[1]-b[1])
            ok = abs(cross) < 1e-6 and dot <= 1e-6
        elif c['type'] in ('parallel', 'perpendicular', 'equal_length'):
            a, b, c1, d = ps
            u, v = (b[0]-a[0], b[1]-a[1]), (d[0]-c1[0], d[1]-c1[1])
            if u == (0, 0) or v == (0, 0):
                raise ValueError('Degenerate constrained segment')
            if c['type'] == 'parallel':
                ok = abs(u[0]*v[1]-u[1]*v[0]) < 1e-6
            elif c['type'] == 'perpendicular':
                ok = abs(u[0]*v[0]+u[1]*v[1]) < 1e-6
            else:
                ok = abs(sum(x*x for x in u)-sum(x*x for x in v)) < 1e-6
        else:
            raise ValueError('Unsupported geometry constraint: ' + c['type'])
        if not ok:
            raise ValueError('Geometry constraint failed: ' + str(c))

    image = Image.new('RGB', (round(width*scale), round(height*scale)), 'white')
    draw = ImageDraw.Draw(image)
    root = ET.Element('{' + SVG + '}svg', {'viewBox': f'0 0 {width} {height}',
                                          'width': str(width), 'height': str(height)})
    ET.SubElement(root, '{' + SVG + '}rect', {'width': '100%', 'height': '100%', 'fill': 'white'})

    def pixels(p):
        return tuple(v*scale for v in p)

    def svg(tag, **attrs):
        return ET.SubElement(root, '{' + SVG + '}' + tag, {k.replace('_', '-'): str(v) for k,v in attrs.items()})

    def line(a, b, color, weight, dash):
        pa, pb = pixels(a), pixels(b)
        distance = math.dist(pa, pb)
        if distance == 0:
            raise ValueError('Zero-length segment')
        if dash:
            if any(not isinstance(v, (int, float)) or v <= 0 for v in dash):
                raise ValueError('Dash lengths must be positive')
            offset, j = 0, 0
            while offset < distance:
                end = min(distance, offset+dash[j % len(dash)]*scale)
                if j % 2 == 0:
                    first = tuple(pa[k]+(pb[k]-pa[k])*offset/distance for k in (0,1))
                    last = tuple(pa[k]+(pb[k]-pa[k])*end/distance for k in (0,1))
                    draw.line([first,last], fill=color, width=max(1,round(weight*scale)))
                offset, j = end, j+1
        else:
            draw.line([pa,pb], fill=color, width=max(1,round(weight*scale)))
        attrs = dict(x1=a[0], y1=a[1], x2=b[0], y2=b[1], stroke=color, stroke_width=weight)
        if dash:
            attrs['stroke_dasharray'] = ','.join(map(str,dash))
        svg('line', **attrs)

    for item in scene.get('items', []):
        kind = item['type']
        color, weight, dash = item.get('color', '#000000'), item.get('width', 2), item.get('dash', [])
        if not isinstance(weight, (int,float)) or not math.isfinite(weight) or weight <= 0:
            raise ValueError('Stroke width must be positive')
        if kind in ('line', 'arrow'):
            a, b = point(item['from']), point(item['to'])
            line(a,b,color,weight,dash)
            if kind == 'arrow':
                dx, dy = a[0]-b[0], a[1]-b[1]
                length = math.hypot(dx,dy)
                ux, uy = dx/length, dy/length
                size = item.get('head_size', 12)
                for sign in (-1,1):
                    end = (b[0]+size*ux+sign*size*.4*uy, b[1]+size*uy-sign*size*.4*ux)
                    line(b,end,color,weight,[])
        elif kind in ('polygon', 'polyline'):
            ps = [point(p) for p in item['points']]
            if len(ps) < (3 if kind == 'polygon' else 2):
                raise ValueError('Too few polygon/polyline points')
            fill = item.get('fill', 'none')
            if kind == 'polygon' and fill != 'none':
                draw.polygon([pixels(p) for p in ps], fill=fill)
                svg('polygon', points=' '.join(f'{p[0]},{p[1]}' for p in ps), fill=fill)
            for a,b in zip(ps, ps[1:] + ([ps[0]] if kind == 'polygon' else [])):
                line(a,b,color,weight,dash)
        elif kind == 'ellipse':
            a,b = point(item['from']), point(item['to'])
            if b[0] <= a[0] or b[1] <= a[1] or dash:
                raise ValueError('Ellipse needs ordered corners; dashed arcs require explicit construction')
            fill = item.get('fill', 'none')
            draw.ellipse([pixels(a),pixels(b)], fill=None if fill == 'none' else fill,
                         outline=color, width=max(1,round(weight*scale)))
            svg('ellipse', cx=(a[0]+b[0])/2, cy=(a[1]+b[1])/2,
                rx=(b[0]-a[0])/2, ry=(b[1]-a[1])/2, fill=fill, stroke=color, stroke_width=weight)
        elif kind == 'label':
            text = item['text']
            if not isinstance(text,str) or not text or re.search(r'[$\\\x00-\x1f]',text):
                raise ValueError('Labels must be plain text; keep editable formulas outside diagrams')
            p = point(item['at'])
            size = item.get('size', 30)
            if not isinstance(size,(int,float)) or size <= 0:
                raise ValueError('Font size must be positive')
            font = ImageFont.truetype(font_path, round(size*scale))
            box = draw.textbbox((0,0),text,font=font)
            tw,th = box[2]-box[0], box[3]-box[1]
            x,y = pixels(p)
            anchor = item.get('anchor','left')
            if anchor not in ('left','center','right'):
                raise ValueError('Invalid text anchor')
            x -= tw/2 if anchor == 'center' else tw if anchor == 'right' else 0
            y -= th/2
            if x < 0 or y < 0 or x+tw > width*scale or y+th > height*scale:
                raise ValueError('Label would be clipped: ' + text)
            draw.text((x-box[0],y-box[1]),text,font=font,fill=color)
            el = svg('text', x=p[0], y=p[1], font_size=size, font_family='SimSun, serif',
                     text_anchor={'left':'start','center':'middle','right':'end'}[anchor],
                     dominant_baseline='central', fill=color)
            el.text = text
        else:
            raise ValueError('Unsupported drawing primitive: ' + kind)
    output = Path(output)
    if output.suffix.lower() != '.png':
        raise ValueError('Output must be PNG; the matching SVG is saved alongside it')
    output.parent.mkdir(parents=True,exist_ok=True)
    image.save(output, dpi=(300,300))
    ET.ElementTree(root).write(output.with_suffix('.svg'), encoding='utf-8', xml_declaration=True)
    return {'pixels':image.size, 'svg':str(output.with_suffix('.svg')),
            'constraints_checked':len(scene.get('constraints',[]))}


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('scene',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--font')
    args=ap.parse_args()
    print(render(json.loads(args.scene.read_text(encoding='utf-8-sig')),args.output,args.font))
