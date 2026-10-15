"""WGS84 input; local equirectangular area is preliminary, not cadastral measurement."""
import math
from html import escape

EPS = 1e-10

def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

def on_segment(p, a, b):
    return abs(cross(a,b,p)) < EPS and min(a[0],b[0])-EPS <= p[0] <= max(a[0],b[0])+EPS and min(a[1],b[1])-EPS <= p[1] <= max(a[1],b[1])+EPS

def intersects(a,b,c,d):
    return (cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0) or any((on_segment(c,a,b), on_segment(d,a,b), on_segment(a,c,d), on_segment(b,c,d)))

def polygon(value):
    if not isinstance(value, list) or not 3 <= len(value) <= 1000:
        raise ValueError('Контур: от 3 до 1000 пар [долгота, широта] в WGS84.')
    points = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in pair):
            raise ValueError('Координаты должны быть конечными числами [долгота, широта].')
        x,y = pair
        if not -180 <= x <= 180 or not -85 <= y <= 85:
            raise ValueError('Координаты вне диапазона WGS84.')
        points.append((float(x),float(y)))
    if points[0] == points[-1]:
        points.pop()
    if len(set(points)) != len(points) or len(points) < 3:
        raise ValueError('Повторяющиеся вершины контура.')
    for i in range(len(points)):
        for j in range(i+1,len(points)):
            if j == i+1 or (i == 0 and j == len(points)-1):
                continue
            if intersects(points[i],points[(i+1)%len(points)],points[j],points[(j+1)%len(points)]):
                raise ValueError('Контур имеет самопересечение.')
    if area(points) < 1:
        raise ValueError('Площадь контура меньше 1 м².')
    return points

def area(points):
    lat = math.radians(sum(p[1] for p in points)/len(points))
    origin = points[0]
    xy = [((x-origin[0])*111195.08*math.cos(lat),(y-origin[1])*111195.08) for x,y in points]
    return abs(sum(xy[i][0]*xy[(i+1)%len(xy)][1]-xy[(i+1)%len(xy)][0]*xy[i][1] for i in range(len(xy)))/2)

def contains(p, ring):
    inside = False
    for i, a in enumerate(ring):
        b = ring[(i+1)%len(ring)]
        if on_segment(p,a,b):
            return True
        if (a[1]>p[1]) != (b[1]>p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside

def covers(ring, parcel):
    if not all(contains(p,ring) for p in parcel):
        return False
    # Split every parcel edge at boundary intersections, then test each subsegment.
    for i,a in enumerate(parcel):
        b = parcel[(i+1)%len(parcel)]
        cuts = [0.,1.]
        dx,dy = b[0]-a[0],b[1]-a[1]
        for j,c in enumerate(ring):
            d = ring[(j+1)%len(ring)]
            ex,ey = d[0]-c[0],d[1]-c[1]
            den = dx*ey-dy*ex
            if abs(den)>1e-18:
                t = ((c[0]-a[0])*ey-(c[1]-a[1])*ex)/den
                u = ((c[0]-a[0])*dy-(c[1]-a[1])*dx)/den
                if 0 <= t <= 1 and 0 <= u <= 1:
                    cuts.append(t)
        cuts.sort()
        for lo,hi in zip(cuts,cuts[1:]):
            t = (lo+hi)/2
            if not contains((a[0]+t*dx,a[1]+t*dy),ring):
                return False
    return True

def svg(points, title):
    lat = math.radians(sum(p[1] for p in points)/len(points))
    xy = [(x*math.cos(lat),-y) for x,y in points]
    minx,miny = min(p[0] for p in xy),min(p[1] for p in xy)
    scale = 580/max(max(p[0] for p in xy)-minx,max(p[1] for p in xy)-miny)
    coords = [(60+(x-minx)*scale,100+(y-miny)*scale) for x,y in xy]
    labels = ''.join(f'<text x="{x+8:.2f}" y="{y-8:.2f}" font-size="15">{i+1}</text>' for i,(x,y) in enumerate(coords))
    pts = ' '.join(f'{x:.2f},{y:.2f}' for x,y in coords)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="800" viewBox="0 0 760 800"><rect width="760" height="800" fill="#f5f8f6"/><text x="30" y="35" font-size="20">{escape(title[:65])}</text><text x="30" y="65" font-size="14">Предварительная схема • WGS84 • север ↑</text><polygon points="{pts}" fill="#c8e8d5" stroke="#18694a" stroke-width="3"/>{labels}<text x="30" y="745" font-size="14">Площадь ≈ {area(points):.1f} м². Не является утверждённой СРЗУ.</text><text x="30" y="775" font-size="13">Для официальной СРЗУ нужны местная СК и кадастровый инженер.</text></svg>'
