"""Selection geometry in original image coordinates, independent of zoom."""
def contains(points, point):
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(points):
        bx, by = points[(i + 1) % len(points)]
        cross = (x-ax)*(by-ay)-(y-ay)*(bx-ax)
        if abs(cross) < 1e-8 and min(ax,bx)-1e-8 <= x <= max(ax,bx)+1e-8 and min(ay,by)-1e-8 <= y <= max(ay,by)+1e-8:
            return True
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside


def intersects_rect(points, rect):
    x0,y0,x1,y1 = rect
    if any(x0 <= x <= x1 and y0 <= y <= y1 for x,y in points):
        return True
    corners = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    if any(contains(points,p) for p in corners):
        return True
    # Liang-Barsky segment clipping, including touching boundaries.
    for i,(ax,ay) in enumerate(points):
        bx,by = points[(i+1)%len(points)]
        low,high = 0.,1.
        for p,q in zip((ax-bx,bx-ax,ay-by,by-ay),(ax-x0,x1-ax,ay-y0,y1-ay)):
            if abs(p)<1e-12:
                if q<0:
                    break
            elif p<0:
                low=max(low,q/p)
            else:
                high=min(high,q/p)
            if low>high:
                break
        else:
            return True
    return False
