"""Original dashboard monogram as a dependency-free PNG/Windows icon."""
import math
import struct
import zlib


def icon_png(size=64):
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    def distance(x,y,a,b):
        dx=b[0]-a[0];dy=b[1]-a[1]
        u=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(x-a[0]-u*dx,y-a[1]-u*dy)
    lines=[((11,35),(24,12),(126,186,210)),((24,12),(37,35),(246,164,83)),((16,27),(32,27),(155,139,193))]
    rows=[]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            px=(x+.5)*48/size;py=(y+.5)*48/size
            edge=math.hypot(max(14-px,0,px-34),max(14-py,0,py-34))
            alpha=max(0.,min(1.,(13-edge)*size/48))
            color=[36,36,36]
            for a,b,stroke in lines:
                coverage=max(0.,min(1.,(2.75-distance(px,py,a,b))*size/48))
                color=[round(v*(1-coverage)+stroke[n]*coverage) for n,v in enumerate(color)]
            row.extend(color+[round(alpha*255)])
        rows.append(bytes(row))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows),9))+chunk(b'IEND',b'')


def icon_ico():
    images=[(size,icon_png(size)) for size in (16,32,48,64,256)]
    offset=6+16*len(images);directory=[]
    for size,payload in images:
        directory.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(payload),offset));offset+=len(payload)
    return struct.pack('<HHH',0,1,len(images))+b''.join(directory)+b''.join(payload for _,payload in images)
