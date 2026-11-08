#!/usr/bin/env python3
"""Parametric contest coordination drawings, not a certified/stamped GFC set.
Run: python3 build_cad_2799418.py [--params custom.json]
Model units: millimetres. Design inputs: feet. SVG/HTML: 1600 x 1200.
Existing dependencies: ezdxf, PyMuPDF, fontTools. No network or installs.
"""
from __future__ import annotations
import argparse, dataclasses, hashlib, html, json, math, os, zipfile
from pathlib import Path
from collections import Counter
import ezdxf
from ezdxf.enums import TextEntityAlignment
import fitz
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.qu2cuPen import Qu2CuPen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'exports'
FT = 304.8
W,H = 1600,1200
INK='#183335'; MUTED='#526765'; PAPER='#f6f4ec'; RULE='#bac5bb'
TEAL='#15796f'; ORANGE='#b8562d'; BLUE='#296da0'; SEWER='#79576f'; GREEN='#63825c'
LAYERS={
 'PLOT_BOUNDARY':(INK,7), 'EV_BAYS':(TEAL,3), 'SWEPT_PATH_ARCS':(ORANGE,30),
 'TSSPDCL_YARD':(ORANGE,30), 'DRIVEWAY_14FT':(TEAL,4), 'REAR_CONTAINERS':(INK,7),
 'PLUMBING_LAYOUT':(BLUE,5), 'HV_CABLE_TRENCH':(ORANGE,1),
 'STORM_DRAINAGE':(TEAL,4), 'DIMENSIONS':(MUTED,8), 'VASTU_GRID':(GREEN,3),
 'TEXT':(INK,7), 'ROAD':(MUTED,8), 'LANDSCAPE':(GREEN,3), 'FURNITURE':(MUTED,8),
 'SEWER_LINE':(SEWER,6), 'WATER_SUPPLY':(BLUE,5), 'EARTHING':(GREEN,3), 'TITLE_BLOCK':(INK,7)}

@dataclasses.dataclass
class Spec:
    depth: float=144
    frontage: float=50
    front_depth: float=90
    driveway: float=14
    road_width: float=100
    bay_count: int=6
    bay_width: float=9
    bay_length: float=18
    bay_start: float=32
    bay_y: float=3
    yard_x: float=2
    yard_y: float=2
    yard_w: float=16
    yard_h: float=14
    cafe_w: float=20
    cafe_h: float=10
    office_w: float=20
    office_h: float=10
    lawn_w: float=28
    lawn_h: float=24
    swap_w: float=10
    swap_h: float=10
    wc_w: float=12
    wc_h: float=10
    turn_outer: float=24
    turn_inner: float=14
    transformer_kva: float=500
    power_factor: float=0.95
    ac_import_limit_kw: float=400
    auxiliary_allowance_kw: float=40
    charger_efficiency: float=0.95
    nominal_charger_kw: float=120
    trench_width_mm: float=600
    trench_depth_mm: float=900
    storm_diameter_mm: float=300
    storm_slope: float=0.005
    sewer_diameter_mm: float=150
    sewer_slope: float=0.01
    water_diameter_mm: float=50
    fee_inr: int=18000
    issue_date: str='2026-11-08'
    @property
    def drive_y(self): return self.frontage-self.driveway
    def footprints(self):
        return {
          'Transformer yard':(self.yard_x,self.yard_y,self.yard_w,self.yard_h),
          'Office':(self.front_depth,0,self.office_w,self.office_h),
          'Cafe':(self.depth-self.cafe_w,0,self.cafe_w,self.cafe_h),
          'Lawn':(self.depth-self.lawn_w,self.drive_y-self.lawn_h,self.lawn_w,self.lawn_h),
          'Swap':(self.depth-self.lawn_w-self.swap_w,self.drive_y-self.swap_h,self.swap_w,self.swap_h),
          'Restrooms':(self.front_depth,self.drive_y-self.wc_h,self.wc_w,self.wc_h)}

# All geometric entities pass through the same scene model for DXF/SVG/PDF.
class Scene:
    def __init__(self): self.items=[]
    def add(self,kind,layer='TEXT',**kw): self.items.append(dict(kind=kind,layer=layer,**kw))
    def line(self,x1,y1,x2,y2,layer='TEXT',**kw): self.add('line',layer,p=[(x1,y1),(x2,y2)],**kw)
    def poly(self,pts,layer='TEXT',close=False,**kw): self.add('poly',layer,p=pts,close=close,**kw)
    def rect(self,x,y,w,h,layer='TEXT',**kw): self.poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],layer,True,**kw)
    def circle(self,x,y,r,layer='TEXT',**kw): self.add('circle',layer,c=(x,y),r=r,**kw)
    def arc(self,x,y,r,a,b,layer='TEXT',**kw): self.add('arc',layer,c=(x,y),r=r,a=a,b=b,**kw)
    def text(self,x,y,t,size=1.2,layer='TEXT',anchor='start',**kw): self.add('text',layer,p=(x,y),text=str(t),size=size,anchor=anchor,**kw)
    def arrow(self,x1,y1,x2,y2,layer='TEXT',head=1,**kw):
        self.line(x1,y1,x2,y2,layer,**kw)
        a=math.atan2(y2-y1,x2-x1)
        self.poly([(x2-head*math.cos(a-.45),y2-head*math.sin(a-.45)),(x2,y2),(x2-head*math.cos(a+.45),y2-head*math.sin(a+.45))],layer,**kw)
    def dim(self,x1,y1,x2,y2,label,vertical=False):
        self.line(x1,y1,x2,y2,'DIMENSIONS',width=.7)
        for x,y in [(x1,y1),(x2,y2)]: self.line(x-.5,y-.5,x+.5,y+.5,'DIMENSIONS',width=.7)
        self.text((x1+x2)/2+(.9 if vertical else 0),(y1+y2)/2+(.5 if not vertical else 0),label,1.35,'DIMENSIONS',anchor='start' if vertical else 'middle')

class Font:
    def __init__(self,path):
        self.font=TTFont(path,fontNumber=0); self.glyphs=self.font.getGlyphSet(); self.cmap=self.font.getBestCmap(); self.upem=self.font['head'].unitsPerEm; self.cache={}
    def resolve(self,c):
        if ord(c) in self.cmap: return self
        fallback=FONTS.get('fallback')
        if fallback and ord(c) in fallback.cmap: return fallback
        raise ValueError(f'Missing font glyph: {c!r}')
    def width(self,t,size):
        return sum(self.resolve(c).font['hmtx'][self.resolve(c).cmap[ord(c)]][0]*size/self.resolve(c).upem for c in t)
    def path(self,c):
        n=self.cmap.get(ord(c),'.notdef')
        if n not in self.cache:
            pen=SVGPathPen(self.glyphs); cubic=Qu2CuPen(pen,max_err=1,all_cubic=True); self.glyphs[n].draw(cubic)
            self.cache[n]=pen.getCommands()
        return self.cache[n], self.font['hmtx'][n][0]

def font_path(bold=False):
    env=os.getenv('CAD_FONT_BOLD' if bold else 'CAD_FONT_REGULAR')
    candidates=[env] if env else []
    candidates += ['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    return next((p for p in candidates if p and Path(p).exists()),None)
FONTS={}

def svg_text(x,y,t,size,color=INK,bold=False,anchor='start'):
    f=FONTS[bool(bold)]; width=f.width(t,size); x-=width/2 if anchor=='middle' else width if anchor=='end' else 0
    chunks=[f'<g aria-label="{html.escape(t,quote=True)}" fill="{color}" stroke="none">']
    for c in t:
        glyphfont=f.resolve(c); d,advance=glyphfont.path(c)
        if d: chunks.append(f'<path d="{d}" transform="translate({x:.4f},{y:.4f}) scale({size/glyphfont.upem:.7f},{-size/glyphfont.upem:.7f})"/>')
        x+=advance*size/glyphfont.upem
    chunks.append('</g>'); return ''.join(chunks)

class Sheet:
    def __init__(self,title,code,subtitle):
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1200" viewBox="0 0 1600 1200" role="img" aria-labelledby="title desc"><title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(subtitle)}</desc>']
        self.text_log=[]; self.scene=Scene()
        self.box(0,0,W,H,PAPER)
        self.line(48,48,1552,48,INK,2)
        self.text(48,81,'KHANAPUR  /  HYDERABAD',17,TEAL,True)
        self.text(48,137,title,44,INK,True)
        self.text(48,173,subtitle,18,MUTED)
        self.text(1552,120,code,55,INK,True,'end')
        self.line(48,198,1552,198,INK,1)
        self.code=code
    def line(self,x1,y1,x2,y2,color=RULE,width=1,dash=None):
        dashattr=f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="{color}" stroke-width="{width}" fill="none"{dashattr}/>')
        self.scene.line(x1,H-y1,x2,H-y2,'TITLE_BLOCK',color=color,width=width)
    def box(self,x,y,w,h,fill='none',stroke=None,width=1):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')
        if stroke: self.scene.rect(x,H-y-h,w,h,'TITLE_BLOCK',color=stroke)
    def text(self,x,y,t,size=16,color=INK,bold=False,anchor='start'):
        width=FONTS[bool(bold)].width(t,size)
        left=x-width/2 if anchor=='middle' else x-width if anchor=='end' else x
        if left<0 or left+width>W+.1 or y>H or y-size<0:
            raise ValueError(f'Text outside sheet: {t}, {left}, {y}, {width}')
        self.parts.append(svg_text(x,y,t,size,color,bold,anchor)); self.text_log.append((left,y-size,width,size,t))
        self.scene.text(x,H-y,t,size,'TITLE_BLOCK',anchor,color=color)
    def lines(self,x,y,lines,size=16,leading=24,color=MUTED):
        for i,t in enumerate(lines): self.text(x,y+i*leading,t,size,color)
    def section(self,x,y,title,width):
        self.line(x,y,x+width,y,INK,1.2); self.text(x,y+27,title,18,INK,True)
    def draw(self,scene,ox,oy,scale,muted=False):
        # world coordinates y-up, sheet coordinates y-down
        tr=lambda p:(ox+p[0]*scale,oy-p[1]*scale)
        for e in scene.items:
            layer=e['layer']; color=e.get('color',LAYERS[layer][0]); color=MUTED if muted else color
            stroke=e.get('width',1.05); dash=' stroke-dasharray="5 4"' if e.get('dash') else ''
            fill=e.get('fill','none')
            kind=e['kind']
            if kind in ('line','poly'):
                pts=[tr(p) for p in e['p']]; d='M'+' L'.join(f'{x:.4f},{y:.4f}' for x,y in pts)+(' Z' if e.get('close') else '')
                if e.get('dash'):
                    segments=[]
                    for a,b in zip(pts,pts[1:]+([pts[0]] if e.get('close') else [])):
                        length=math.dist(a,b)
                        for start in range(0,math.ceil(length),9):
                            end=min(start+5,length)
                            if start>=length: continue
                            u=start/length; v=end/length
                            segments.append(f'M{a[0]+(b[0]-a[0])*u},{a[1]+(b[1]-a[1])*u} L{a[0]+(b[0]-a[0])*v},{a[1]+(b[1]-a[1])*v}')
                    d=' '.join(segments); dash=''
                self.parts.append(f'<path d="{d}" stroke="{color}" stroke-width="{stroke}" fill="{fill}"{dash}/>')
            elif kind=='circle':
                x,y=tr(e['c'])
                if e.get('dash'):
                    r=e['r']*scale
                    for start in range(0,math.ceil(2*math.pi*r),9):
                        a=start/r; b=min(start+5,2*math.pi*r)/r
                        self.parts.append(f'<path d="M{x+r*math.cos(a)},{y+r*math.sin(a)} A{r},{r} 0 0 1 {x+r*math.cos(b)},{y+r*math.sin(b)}" stroke="{color}" stroke-width="{stroke}" fill="none"/>')
                else: self.parts.append(f'<circle cx="{x}" cy="{y}" r="{e["r"]*scale}" stroke="{color}" stroke-width="{stroke}" fill="{fill}"/>')
            elif kind=='arc':
                cx,cy=e['c']; r=e['r']; a,b=map(math.radians,(e['a'],e['b']))
                x1,y1=tr((cx+r*math.cos(a),cy+r*math.sin(a))); x2,y2=tr((cx+r*math.cos(b),cy+r*math.sin(b)))
                if e.get('dash'):
                    total=(b-a)*r*scale
                    for start in range(0,math.ceil(total),9):
                        aa=a+start/(r*scale); bb=a+min(start+5,total)/(r*scale)
                        x1,y1=tr((cx+r*math.cos(aa),cy+r*math.sin(aa))); x2,y2=tr((cx+r*math.cos(bb),cy+r*math.sin(bb)))
                        self.parts.append(f'<path d="M{x1},{y1} A{r*scale},{r*scale} 0 0 0 {x2},{y2}" stroke="{color}" stroke-width="{stroke}" fill="none"/>')
                else: self.parts.append(f'<path d="M{x1},{y1} A{r*scale},{r*scale} 0 {int((e["b"]-e["a"])%360>180)} 0 {x2},{y2}" stroke="{color}" stroke-width="{stroke}" fill="none"/>')
            elif kind=='text':
                x,y=tr(e['p']); self.text(x,y,e['text'],e['size']*scale,color,e.get('bold',False),e.get('anchor','start'))
        # copy all world elements into sheet-space model for CAD paperspace
        for e in scene.items:
            q=dict(e)
            if e['kind'] in ('line','poly'): q['p']=[(ox+x*scale,H-oy+y*scale) for x,y in e['p']]
            elif e['kind'] in ('circle','arc'): q['c']=(ox+e['c'][0]*scale,H-oy+e['c'][1]*scale); q['r']=e['r']*scale
            elif e['kind']=='text': continue # text already copied by self.text
            self.scene.items.append(q)
    def footer(self,spec,scale_note):
        self.line(48,1110,1552,1110,INK,1.2)
        self.text(48,1140,'CONTEST 2799418  /  COORDINATION ISSUE 01',14,INK,True)
        self.text(48,1167,'NOT FOR CONSTRUCTION  ·  Unstamped; survey, utility and licensed-design checks outstanding.',14,MUTED)
        self.text(1552,1140,scale_note,14,INK,False,'end')
        self.text(1552,1167,f'{spec.issue_date}  /  {self.code}  /  24 × 18 in at 100% print',14,MUTED,False,'end')
    def svg(self): return ''.join(self.parts)+'</svg>'


def base_scene(p,utility=False):
    s=Scene(); d=p.footprints(); dy=p.drive_y
    # Road is shown broken in presentation; modelspace contains full 100 ft extent.
    s.rect(-22,0,22,p.frontage,'ROAD',fill='#e7e9e2',width=.7)
    for y in range(0,int(p.frontage)+1,5): s.line(-19,y,-17,y+1.3,'ROAD',width=.7)
    s.line(-9,2,-9,p.frontage-2,'ROAD',dash=True)
    s.text(-11,12,f'{p.road_width:g} ft',1.7,'ROAD',anchor='middle',bold=True)
    s.text(-11,9,'MAIN ROAD',1.35,'ROAD',anchor='middle')
    s.text(-11,6,'WEST / BROKEN',.95,'ROAD',anchor='middle')
    s.rect(0,0,p.depth,p.frontage,'PLOT_BOUNDARY',fill='#fcfbf6',width=2.3)
    s.rect(0,dy,p.depth,p.driveway,'DRIVEWAY_14FT',fill='#e1eee6',width=1.1)
    s.line(p.front_depth,0,p.front_depth,p.frontage,'DIMENSIONS',dash=True)
    s.text(p.front_depth/2,p.frontage+7.8,f'FRONT EV ZONE  /  {p.front_depth*p.frontage/9:,.0f} sq yds',1.7,bold=True,anchor='middle')
    s.text((p.front_depth+p.depth)/2,p.frontage+7.8,f'REAR LIFESTYLE ZONE  /  {(p.depth-p.front_depth)*p.frontage/9:,.0f} sq yds',1.7,bold=True,anchor='middle')
    s.dim(0,p.frontage+4,p.front_depth,p.frontage+4,f'{p.front_depth:g}\' / {p.front_depth*FT/1000:.3f} m')
    s.dim(p.front_depth,p.frontage+4,p.depth,p.frontage+4,f'{p.depth-p.front_depth:g}\' / {(p.depth-p.front_depth)*FT/1000:.3f} m')
    for x in (0,p.front_depth,p.depth): s.line(x,p.frontage,x,p.frontage+5,'DIMENSIONS',width=.6)
    s.dim(p.depth+3,0,p.depth+3,p.frontage,f'{p.frontage:g}\'',True)
    s.text(p.depth+4,22,f'{p.frontage*FT/1000:.3f} m',1,'DIMENSIONS')
    s.dim(0,-6,p.depth,-6,f'{p.depth:g}\' OVERALL / {p.depth*FT/1000:.4f} m')
    for x in (0,p.depth): s.line(x,0,x,-7,'DIMENSIONS',width=.6)
    s.text(47,dy+8.2,f'{p.driveway:g} ft CLEAR / {p.driveway*FT/1000:.4f} m',1.65,'DRIVEWAY_14FT',anchor='middle',bold=True)
    s.text(47,dy+5.6,'CONTINUOUS SERVICE + CUSTOMER CORRIDOR',1.08,'DRIVEWAY_14FT',anchor='middle')
    for x in (4,75,119): s.arrow(x,dy+10.8,x+10,dy+10.8,'DRIVEWAY_14FT',head=.8)
    s.text(137,dy+3,'DEAD END',.95,'DRIVEWAY_14FT',anchor='middle')
    # Transformer yard and equipment.
    x,y,w,h=d['Transformer yard']; s.rect(x,y,w,h,'TSSPDCL_YARD',fill='#f3e6d8',width=1.8)
    for xx in range(int(x),int(x+w)+1,2): s.line(xx,y,xx,y-.3,'TSSPDCL_YARD',width=.6)
    s.rect(x+4,y+3,7,6,'TSSPDCL_YARD',width=1.1)
    s.rect(x+1,y+h-3,4,2,'TSSPDCL_YARD'); s.text(x+3,y+h-2.5,'VCB',.9,anchor='middle')
    s.rect(x+10,y+h-3,5,2,'TSSPDCL_YARD'); s.text(x+12.5,y+h-2.5,'METER',.8,anchor='middle')
    s.text(x+7.5,y+6.8,f'{p.transformer_kva:g}',1.55,'TSSPDCL_YARD',anchor='middle',bold=True)
    s.text(x+7.5,y+4.8,'kVA TX',1,'TSSPDCL_YARD',anchor='middle')
    for xx,yy in [(x+1,y+1),(x+w-1,y+1),(x+1,y+9),(x+w-1,y+9)]:
        s.circle(xx,yy,.4,'EARTHING'); s.line(xx-.7,yy,xx+.7,yy,'EARTHING')
    s.text(x+w/2,y-1.7,f'TSSPDCL YARD  {w:g} × {h:g} ft',1.12,'TSSPDCL_YARD',anchor='middle')
    # Six physically dimensioned bays, individual islands, dual gun heads and bollards.
    for i in range(p.bay_count):
        bx=p.bay_start+i*p.bay_width; by=p.bay_y
        s.rect(bx,by,p.bay_width,p.bay_length,'EV_BAYS',fill='#e9f0e7',width=1.35)
        s.rect(bx+2,.25,5,2.5,'EV_BAYS',fill='#d0d9ca')
        s.rect(bx+3.5,.7,2,1.5,'EV_BAYS',fill=TEAL)
        for xx in (bx+2.5,bx+6.5): s.circle(xx,2,.22,'EV_BAYS',fill=ORANGE)
        for dx in (-.45,.45): s.line(bx+4.5+dx,1.4,bx+4.5+dx,3.2,'EV_BAYS')
        if not utility:
            s.rect(bx+1.5,by+3,6,12.8,'FURNITURE',width=.65)
            s.rect(bx+1.9,by+5,5.2,2.3,'FURNITURE',width=.65)
            s.rect(bx+1.9,by+12.3,5.2,1.6,'FURNITURE',width=.65)
        s.text(bx+p.bay_width/2,by+8,f'EV {i+1:02}',1.35,'EV_BAYS',anchor='middle',bold=True)
        s.text(bx+p.bay_width/2,by+5.8,f'{p.bay_width:g} × {p.bay_length:g} ft',1.08,'EV_BAYS',anchor='middle')
        s.text(bx+p.bay_width/2,by-1.7,f'DC-{i+1:02}',.9,'EV_BAYS',anchor='middle')
    s.text(62,31,f'EV MANEUVER AISLE  /  {p.drive_y-p.bay_y-p.bay_length:g} ft',1.45,'EV_BAYS',anchor='middle',bold=True)
    s.text(62,28.5,'REVERSE-IN / FORWARD-OUT',1.05,'EV_BAYS',anchor='middle')
    s.arrow(81,25,45,25,'EV_BAYS',head=1)
    # Module footprints and layout details.
    for key in ('Office','Cafe','Swap','Restrooms','Lawn'):
        x,y,w,h=d[key]; lay='LANDSCAPE' if key=='Lawn' else 'REAR_CONTAINERS'
        s.rect(x,y,w,h,lay,fill='#e3ead7' if key=='Lawn' else '#efece1',width=1.7)
        if key=='Lawn':
            for tx in (x+5,x+14,x+23):
                for ty in (y+6,y+16):
                    s.circle(tx,ty,1.5,'FURNITURE');
                    for dx,ddy in [(0,2.2),(0,-2.2),(2.2,0),(-2.2,0)]: s.circle(tx+dx,ty+ddy,.45,'FURNITURE')
            for tx in (x+1,x+w-1):
                for ty in (y+1,y+h-1): s.rect(tx-.3,ty-.3,.6,.6,'LANDSCAPE',fill=GREEN)
            s.text(x+w/2,y+h/2+1,'PERGOLA / LAWN',1.5,'LANDSCAPE',anchor='middle',bold=True)
            s.text(x+w/2,y+h/2-1.3,f'{w:g} × {h:g} ft  /  {w*h:g} sq ft',1.18,'LANDSCAPE',anchor='middle')
        elif key=='Cafe':
            s.rect(x+1,y+1,w-2,2,'REAR_CONTAINERS'); s.rect(x+w-4,y+1,3,5,'REAR_CONTAINERS')
            s.text(x+w/2,y+6.5,'CAFÉ / SE',1.55,anchor='middle',bold=True)
            s.text(x+w/2,y+4.2,f'{w:g} × {h:g} ft',1.25,anchor='middle')
            s.text(x+w/2,y+1.5,'ESPRESSO + KITCHEN COUNTER',.79,anchor='middle')
            s.line(x+6,y+h,x+10,y+h,'REAR_CONTAINERS',color=PAPER,width=3)
        elif key=='Office':
            s.rect(x+1,y+1,7,2,'FURNITURE'); s.rect(x+14,y+1,5,2,'FURNITURE')
            s.text(x+w/2,y+6.5,'OFFICE / SW*',1.5,anchor='middle',bold=True)
            s.text(x+w/2,y+4.1,f'{w:g} × {h:g} ft',1.25,anchor='middle')
            s.text(x+w/2,y+1.5,'ADMIN / CCTV / DRIVER LOUNGE',.76,anchor='middle')
            s.line(x+8,y+h,x+12,y+h,'REAR_CONTAINERS',color=PAPER,width=3)
        elif key=='Swap':
            s.rect(x+1,y+1,w-2,2,'REAR_CONTAINERS')
            s.text(x+w/2,y+6.1,'SWAP',1.4,anchor='middle',bold=True)
            s.text(x+w/2,y+4.1,f'{w:g} × {h:g} ft',1.05,anchor='middle')
            s.text(x+w/2,y+1.5,'2W / 3W / 4W*',.74,anchor='middle')
            s.arrow(x+w/2,y+h+2,x+w/2,y+h-1,'DRIVEWAY_14FT',head=.6)
        elif key=='Restrooms':
            s.line(x+6,y,x+6,y+h,'REAR_CONTAINERS',width=.7)
            s.line(x+9,y,x+9,y+6,'REAR_CONTAINERS',width=.7)
            s.line(x+6,y+6,x+w,y+6,'REAR_CONTAINERS',width=.7)
            s.text(x+3,y+5.4,'ACC.',1.1,anchor='middle'); s.text(x+7.5,y+3,'M',1.1,anchor='middle'); s.text(x+10.5,y+3,'F',1.1,anchor='middle')
            s.text(x+9,y+8,'STAFF',.88,anchor='middle'); s.text(x+w/2,y-2,f'WC {w:g} × {h:g} ft / NW*',1.02,anchor='middle')
    s.text(106,17,'PEDESTRIAN COURT',1.05,anchor='middle')
    s.text(115,-2.4,'* SW / NW refer to rear-block zoning',1.05,'DIMENSIONS',anchor='middle')
    s.text(0,-2,'O (0,0)',1.05,'DIMENSIONS')
    return s


def civil_scene(p):
    s=base_scene(p)
    # Exact radius CAD arcs, not a claim of vehicle-specific AutoTURN validation.
    cx=p.turn_inner; cy=p.drive_y-p.turn_inner
    for r in (p.turn_outer,p.turn_inner): s.arc(cx,cy,r,90,180,'SWEPT_PATH_ARCS',width=1.8)
    s.text(11,29,'R24 / R14',1.25,'SWEPT_PATH_ARCS',anchor='middle',bold=True)
    s.text(11,26.8,'TURN-IN',1,'SWEPT_PATH_ARCS',anchor='middle')
    s.arrow(-16,23,-16,34,'DRIVEWAY_14FT'); s.arrow(-4,34,4,41,'DRIVEWAY_14FT')
    s.arrow(20,23,-4,23,'EV_BAYS'); s.arrow(-4,23,-4,17,'EV_BAYS')
    for r in (p.turn_outer,p.turn_inner): s.arc(p.bay_start,p.bay_y+p.bay_length,r,90,180,'SWEPT_PATH_ARCS',dash=True,width=1)
    s.text(24,49,'REVERSE ENVELOPE',.95,'SWEPT_PATH_ARCS',anchor='middle')
    s.text(24,46.8,'R24 / R14 · TEMPLATE',.95,'SWEPT_PATH_ARCS',anchor='middle')
    return s


def utility_scene(p):
    s=base_scene(p,True); d=p.footprints()
    # LV power and HT cable routes share a dedicated electrical strip, not wet services.
    ex=p.yard_x+p.yard_w+3
    s.poly([(-22,7),(p.yard_x+2,7),(p.yard_x+2,13),(p.yard_x+7,13),(p.yard_x+7,8)],'HV_CABLE_TRENCH',width=2.6)
    s.poly([(p.yard_x+9,8),(ex,8),(ex,1),(p.front_depth-2,1)],'HV_CABLE_TRENCH',width=2.2)
    s.rect(ex-1.5,6,3,4,'HV_CABLE_TRENCH',fill='#f0d5bf'); s.text(ex,11,'LT / EMS',1,'HV_CABLE_TRENCH',anchor='middle')
    for i in range(p.bay_count):
        x=p.bay_start+i*p.bay_width+p.bay_width/2
        s.line(x,1,x,2,'HV_CABLE_TRENCH',width=2.3)
    s.poly([(ex,8),(ex,18),(28,18),(28,23),(p.front_depth+14,23),(p.front_depth+14,35)],'HV_CABLE_TRENCH',width=2)
    sx,sy,sw,sh=d['Swap']; s.line(p.front_depth+14,sy+3,sx+2,sy+3,'HV_CABLE_TRENCH',width=2)
    for key in ('Office','Cafe'):
        x,y,w,h=d[key]; s.poly([(p.front_depth+14,23),(p.front_depth+14,12),(x+2,12),(x+2,h-1)],'HV_CABLE_TRENCH',width=2); s.rect(x+1,h-2,2,1,'HV_CABLE_TRENCH')
    s.text(63,-3,f'{p.trench_width_mm:g} × {p.trench_depth_mm:g} mm RCC CABLE TRENCH / TYP.',1.05,'HV_CABLE_TRENCH',anchor='middle')
    s.text(-11,16,'11 kV IN',1.15,'HV_CABLE_TRENCH',anchor='middle')
    # Separate north-side wet-service lines. Covers are flush and traffic rated.
    storm_y=p.frontage-1.4; sewer_y=p.frontage-4; water_y=p.frontage-7
    s.line(0,storm_y,p.depth-1,storm_y,'STORM_DRAINAGE',width=2.2)
    for x in (3,45,88,p.depth-2):
        s.rect(x-.55,storm_y-.55,1.1,1.1,'STORM_DRAINAGE',fill=PAPER)
    s.arrow(112,storm_y,100,storm_y,'STORM_DRAINAGE',head=.7)
    s.poly([(0,storm_y),(-12,storm_y)],'STORM_DRAINAGE',width=2.2)
    rx,ry,rw,rh=d['Restrooms']
    s.poly([(rx+rw-1,ry+rh-1),(rx+rw-1,sewer_y),(-12,sewer_y)],'SEWER_LINE',width=1.7,dash=True)
    for x in (8,50,rx+rw-1): s.circle(x,sewer_y,.5,'SEWER_LINE')
    s.text(62,storm_y+1.3,f'{p.storm_diameter_mm:g} mm STORM → WEST CULVERT',.96,'STORM_DRAINAGE',anchor='middle')
    s.text(71,sewer_y-1.4,f'{p.sewer_diameter_mm:g} mm SEWER / IC AT BENDS',.93,'SEWER_LINE',anchor='middle')
    # Supply ring wraps occupied rear block; never shares a wastewater trench.
    s.poly([(1,water_y),(p.depth-2,water_y),(p.depth-2,11),(rx-2,11),(rx-2,water_y)],'WATER_SUPPLY',width=1.5)
    s.line(rx+2,water_y,rx+2,ry+rh-1,'WATER_SUPPLY',width=1.5)
    s.circle(rx+3,ry+rh-2,1.1,'WATER_SUPPLY'); s.text(rx+3,ry+rh-2.4,'T',.85,'WATER_SUPPLY',anchor='middle')
    s.line(d['Cafe'][0]+3,11,d['Cafe'][0]+3,3,'WATER_SUPPLY',width=1.5)
    s.text(121,water_y-1.7,f'{p.water_diameter_mm:g} mm CPVC WATER LOOP',.96,'WATER_SUPPLY',anchor='middle')
    s.rect(rx+rw+1,ry-5,3,2,'PLUMBING_LAYOUT',fill='#dce8e8')
    s.poly([(rx+rw,ry+2),(rx+rw+2.5,ry+2),(rx+rw+2.5,ry-3)],'PLUMBING_LAYOUT',dash=True,width=1.2)
    s.text(rx+rw+3,ry-6.7,'BIO-FILTER',.9,'PLUMBING_LAYOUT',anchor='middle')
    return s


def plumbing_scene(p):
    s=Scene(); w,h=12,10; wall=.25
    s.rect(0,0,w,h,'PLUMBING_LAYOUT',fill='#fcfbf6',width=3)
    s.rect(wall,wall,w-2*wall,h-2*wall,'PLUMBING_LAYOUT',width=.6)
    s.line(6,0,6,10,'PLUMBING_LAYOUT',width=2); s.line(9,0,9,6,'PLUMBING_LAYOUT',width=2); s.line(6,6,12,6,'PLUMBING_LAYOUT',width=2)
    # Three public entrances to south, private staff entry on east; sliding accessible door.
    for x,door in [(1.2,3.3),(6.25,2.5),(9.25,2.5)]:
        s.line(x,0,x+door,0,'PLUMBING_LAYOUT',color=PAPER,width=5)
        if x<2:
            s.line(x,-.3,x+door,-.3,'PLUMBING_LAYOUT'); s.arrow(x+door,-.3,x,-.3,'PLUMBING_LAYOUT',head=.2)
        else:
            s.line(x,0,x,-door,'PLUMBING_LAYOUT',width=.7); s.arc(x,0,door,270,360,'PLUMBING_LAYOUT',width=.6)
    s.line(12,6.6,12,9.1,'PLUMBING_LAYOUT',color=PAPER,width=5)
    s.line(12,6.6,14.5,6.6,'PLUMBING_LAYOUT',width=.7); s.arc(12,6.6,2.5,0,90,'PLUMBING_LAYOUT',width=.6)
    s.circle(3,4.2,2.46,'PLUMBING_LAYOUT',dash=True,width=.7)
    s.text(3,4.15,'Ø1500 CLEAR',.36,'PLUMBING_LAYOUT',anchor='middle',bold=True)
    s.text(3,2.7,'ACCESSIBLE / PUBLIC',.36,anchor='middle',bold=True)
    s.text(7.5,2.7,'MALE',.38,anchor='middle',bold=True); s.text(10.5,2.7,'FEMALE',.34,anchor='middle',bold=True)
    s.text(9,7,'PRIVATE / STAFF',.33,anchor='middle',bold=True)
    for x,y in [(1.2,8.2),(7.5,4.9),(10.5,4.9),(7.4,8.6)]:
        s.rect(x-.55,y+.2,1.1,.7,'PLUMBING_LAYOUT'); s.circle(x,y-.35,.5,'PLUMBING_LAYOUT')
        s.line(x,y+.9,x,10.6,'SEWER_LINE',width=1.3)
    # Wall-mounted grab bars and low wash basin.
    s.poly([(.5,9.4),(.5,7.1),(1.4,7.1)],'PLUMBING_LAYOUT',width=1.5)
    for x,y in [(4.8,8.8),(6.75,1.4),(9.75,1.4),(10.5,8.8)]:
        s.rect(x-.5,y-.3,1,.65,'PLUMBING_LAYOUT'); s.circle(x,y,.16,'PLUMBING_LAYOUT')
        s.poly([(x,y),(x,11.3)],'WATER_SUPPLY',width=1.1)
        s.poly([(x+.2,y),(x+.2,10.1)],'PLUMBING_LAYOUT',dash=True,width=.7)
    s.line(.4,11.3,11.6,11.3,'WATER_SUPPLY',width=1.5)
    s.line(.4,10.6,11.6,10.6,'SEWER_LINE',width=1.8)
    s.line(.4,10.1,11.6,10.1,'PLUMBING_LAYOUT',width=.9,dash=True)
    s.text(6,12.25,f'{p.water_diameter_mm:g} CPVC FROM OHT / ISOLATING VALVES',.34,'WATER_SUPPLY',anchor='middle')
    s.text(6,11.65,f'{p.sewer_diameter_mm:g} uPVC SOIL → IC / ROAD SEWER',.33,'SEWER_LINE',anchor='middle')
    s.text(6,-3.2,'SOUTH: LEVEL PEDESTRIAN COURT / NO STEP',.32,'PLUMBING_LAYOUT',anchor='middle')
    s.text(14.1,10.6,'100 VENT',.3,'SEWER_LINE',anchor='middle')
    s.line(11.6,10.6,13.1,10.6,'SEWER_LINE'); s.circle(13.1,10.6,.2,'SEWER_LINE')
    for x,y in [(4.8,1.2),(8.3,1.2),(11.3,1.2),(11.3,7.3)]:
        s.rect(x-.14,y-.14,.28,.28,'PLUMBING_LAYOUT'); s.text(x,y-.6,'FT',.23,'PLUMBING_LAYOUT',anchor='middle')
        s.poly([(x,y),(x,10.1)],'PLUMBING_LAYOUT',width=.6,dash=True)
    s.dim(0,-4.2,12,-4.2,f'{p.wc_w:g} ft / {p.wc_w*FT:.1f} mm')
    # Override dimension label size to match enlarged detail, without hardcoding pixel geometry.
    s.items[-1]['size']=.38
    sx,sy=p.wc_w/12,p.wc_h/10
    for e in s.items:
        if e['kind'] in ('line','poly'): e['p']=[(x*sx,y*sy) for x,y in e['p']]
        elif e['kind'] in ('circle','arc'): e['c']=(e['c'][0]*sx,e['c'][1]*sy)
        elif e['kind']=='text': e['p']=(e['p'][0]*sx,e['p'][1]*sy)
    return s


def north_and_scale(sh,x,y,scale=8):
    sh.text(x,y-34,'N',18,INK,True,'middle'); sh.line(x,y-25,x,y+13,INK,1.7)
    sh.line(x,y-25,x-6,y-13,INK,1.7); sh.line(x,y-25,x+6,y-13,INK,1.7)
    sh.text(x+22,y+8,'E →',13,MUTED)
    bx=x-40; by=y+45
    for i in range(4): sh.box(bx+i*2.5*scale,by,2.5*scale,5,INK if i%2==0 else PAPER,INK,.5)
    sh.text(bx,by+24,'0',12,MUTED); sh.text(bx+5*scale,by+24,'5',12,MUTED,anchor='middle'); sh.text(bx+10*scale,by+24,'10 ft',12,MUTED,anchor='end')


def make_c01(p):
    sh=Sheet('EV hub & café destination','C-01','MASTER SITE PLAN  /  800 sq yds  /  West-facing  /  2D civil coordination')
    sh.text(48,231,'01  /  SITE SET-OUT',16,INK,True)
    sh.text(1552,231,'ORIGIN: SOUTHWEST CORNER  ·  X EAST / Y NORTH',14,MUTED,anchor='end')
    sh.draw(civil_scene(p),240,790,8)
    north_and_scale(sh,1494,358,8)
    sh.text(48,856,'Road shown with width break. Plot and all scheduled footprints are drawn to scale.',14,MUTED)
    sh.text(48,882,'Solid arcs: turn-in. Dashed arcs: reverse template. R24 / R14 = 7.3152 / 4.2672 m; vehicle simulation pending.',14,ORANGE)
    cols=[48,562,1076]; cw=476
    for x,t in zip(cols,['02  /  CHARGING & ACCESS','03  /  SET-OUT SCHEDULE','04  /  DESIGN BASIS']): sh.section(x,914,t,cw)
    sh.lines(cols[0],966,[f'{p.bay_count} bays · {p.bay_width:g} × {p.bay_length:g} ft each · {p.bay_count*p.bay_width*p.bay_length:g} sq ft total',
       'Dual-gun CCS2 · 120 kW / 240 kW option', 'Concrete islands + protective bollards',
       f'North corridor: {p.driveway:g} ft clear, full {p.depth:g} ft length', 'Rear vehicle access is a dead end; no fire tender turn.'],15,25)
    sh.lines(cols[1],966,['Café  124–144 / 0–10 ft     Office  90–110 / 0–10 ft',
       'Lawn  116–144 / 12–36 ft   Swap  106–116 / 26–36 ft',
       'WC  90–102 / 26–36 ft     Yard  2–18 / 2–16 ft',
       'Coordinates shown as X range / Y range.', 'No fixed footprint intersects the north corridor.'],15,25)
    sh.lines(cols[2],966,['Rear-block Vastu zoning; see P-01 matrix.',
       f'{p.drive_y-p.bay_y-p.bay_length:g} ft bay aisle: verify chosen design vehicle.',
       'TSSPDCL yard clearance and setbacks unapproved.',
       '4W swapping compatibility is vendor-dependent.',
       'No structural container engineering in this scope.'],15,25)
    sh.footer(p,'SITE 1:100  /  DIMENSIONS GOVERN')
    return sh


def make_e01(p):
    sh=Sheet('Power, water & groundworks','E-01','UTILITY ROUTING  /  Dedicated electrical trench  /  Separate wet-service corridors')
    sh.text(48,231,'01  /  UNDERGROUND COORDINATION PLAN',16,INK,True)
    sh.text(1552,231,'SIZES FROM DESIGN BRIEF · FINAL SIZING SUBJECT TO CALCULATIONS',13,MUTED,anchor='end')
    sh.draw(utility_scene(p),240,790,8)
    north_and_scale(sh,1494,358,8)
    legend=[(48,ORANGE,'HT / LV POWER'),(345,TEAL,'300 mm STORM'),(630,SEWER,'150 mm SEWER'),(930,BLUE,'50 mm CPVC'),(1227,GREEN,'EARTH / LANDSCAPE')]
    for x,c,t in legend: sh.line(x,855,x+30,855,c,3); sh.text(x+40,860,t,14,c,True)
    for x,t in zip([48,562,1076],['02  /  RCC TRENCH SECTION','03  /  LOAD & CABLE SCHEDULE','04  /  DRAINAGE DESIGN BASIS']): sh.section(x,891,t,476)
    # trench cross section, dimensions in mm
    sh.line(64,953,298,953,INK,1.4); sh.box(85,953,174,112,'none',INK,2)
    sh.box(85,953,174,10,'#d5d8cd',INK,1); sh.line(101,1047,243,1047,ORANGE,1)
    for xx in (126,171,216):
        sh.parts.append(f'<circle cx="{xx}" cy="1030" r="9" fill="none" stroke="{ORANGE}" stroke-width="2"/>')
    sh.text(172,1085,f'{p.trench_width_mm:g} mm CLEAR',12,INK,False,'middle')
    sh.text(276,1006,f'{p.trench_depth_mm:g} mm',12,INK); sh.text(276,1027,'deep',12,MUTED)
    sh.lines(324,958,['RCC cover', 'Traffic-rated', 'Cable supports', 'Sand bedding', 'HT/LV divider', 'Section NTS'],13,24)
    sh.lines(562,946,['500 kVA · 11/0.433 kV TX → VCB / meter → LT',
        '3×300 sq.mm Al XLPE: brief basis; cores / runs TBD.',
        '600×900 mm trench → DC-01…06 + rear DBs.',
        'EMS cap: 400 kW AC; auxiliary allowance 40 kW.',
        'At 95% efficiency: 342 kW aggregate DC budget.',
        'Six 120 kW units need 720 kW DC if uncapped.'],14.5,26)
    sh.lines(1076,946,['300 NP2 storm: assumed 0.5% fall east → west.',
        '43.891 m run gives 219 mm fall (verify outfall).',
        '150 uPVC foul: nominal 1% gradient to road IC.',
        '50 CPVC ring + OHT feed + isolated branches.',
        'Keep wet services separate; sleeve crossings.',
        'No road sewer confirmed; septic option unlocated.'],14.5,26)
    sh.footer(p,'SITE 1:100  /  TRENCH SECTION NTS')
    return sh


def make_p01(p,board=False):
    sh=Sheet('Plumbing & Vastu coordination','P-01','RESTROOM DETAIL  /  Fixture routing  /  Zoning matrix  /  Commercial proposal')
    sh.section(48,228,'01  /  RESTROOM PLUMBING PLAN',660)
    sh.draw(plumbing_scene(p),106,764,32)
    sh.text(48,950,f'{p.wc_w:g} × {p.wc_h:g} ft gross block. 75 mm indicative partitions.',14,MUTED)
    sh.lines(48,979,['Public male + female + accessible WC; separate private staff WC.',
       'FT = trapped floor drain. Dashed blue = greywater to bio-filter.',
       '150 mm soil collector → inspection chamber → confirmed sewer.',
       'Dimensions and accessibility clearances require local approval.'],14,25)
    sh.section(764,228,'02  /  VASTU ZONING MATRIX',788)
    # rear block grid, cardinal directions explicit
    gx,gy,cell=780,300,94
    labels=[['NW / WC','N / SWAP','NE / OPEN'],['W / COURT','CENTRE','E / LAWN'],['SW / ADMIN','S / COURT','SE / CAFÉ']]
    for row in range(3):
        for col in range(3):
            sh.box(gx+col*cell,gy+row*cell,cell,cell,'#e5ebdc' if row==2 or row==0 else 'none',RULE)
            sh.text(gx+col*cell+cell/2,gy+row*cell+53,labels[row][col],11.5,INK,True,'middle')
    sh.lines(1100,318,['NORTH ↑  /  WEST ← ROAD',
       f'Rear block: X{p.front_depth:g}–{p.depth:g} / Y0–{p.frontage:g} ft.', 'SE café / kitchen: Agni intent.',
       'SW admin: rear-block Nairutya.', 'NW WC: rear-block Vayu.',
       'North-centre swap faces driveway.', 'Site SW: transformer utility yard.',
       'No universal Vastu certification', 'claimed for this coordination set.'],14,30)
    sh.text(780,612,'Rear-block zoning is distinct from whole-site Vastu quadrants.',14,ORANGE)
    sh.section(764,646,'03  /  FEE, REVISIONS & DELIVERY',788)
    sh.text(780,702,f'₹{p.fee_inr:,} INR',36,INK,True)
    sh.text(780,734,'Estimated lump-sum civil / MEP drawing fee; included in contest.',16,MUTED)
    sh.text(780,782,'Unlimited revisions until ground execution sign-off',18,INK,True)
    sh.text(780,827,'Initial draft delivered Today',18,INK,True)
    sh.text(780,859,'Final stamped GFC working set within 48 hours',18,INK,True)
    sh.lines(780,891,['Requested service target; conditional on licensed engineer engagement,',
       'survey / utility inputs and approvals. This issue is not stamped GFC.'],14,23,ORANGE)
    sh.section(764,960,'04  /  RELEASE CHECKS',788)
    sh.lines(780,1003,['Survey & levels · vehicle-specific swept paths · fire access strategy',
       'TSSPDCL yard approval · cable ampacity / fault duty · earthing design',
       'Sewer / culvert invert confirmation · accessible WC & Vastu review'],14,27)
    sh.footer(p,'PLUMBING 1:25  /  VASTU DIAGRAM NTS')
    return sh


def make_board2(p):
    # Board 2 combines the utility routing with the enlarged restroom and schedules.
    sh=Sheet('The infrastructure behind the destination','E-01 + P-01','ELECTRICAL + PLUMBING  /  Coordinated site services, rear amenities and delivery schedule')
    sh.text(48,229,'01  /  HEAVY-LOAD UTILITIES & DRAINAGE',16,INK,True)
    sh.draw(utility_scene(p),244,722,7.6)
    north_and_scale(sh,1490,336,5)
    sh.text(48,795,'POWER  11 kV → 500 kVA → LT / EMS → 6 DC chargers + swap + café / office DBs',16,ORANGE,True)
    sh.text(48,822,'600×900 mm RCC trench · 3×300 sq.mm Al XLPE*  |  300 NP2 storm · 150 uPVC sewer · 50 CPVC water',15,MUTED)
    sh.section(48,846,'02  /  RESTROOM PLUMBING',490)
    sh.draw(plumbing_scene(p),90,1052,12)
    sh.lines(310,899,['12 × 10 ft gross', 'Male / female / accessible', 'Private staff WC', 'OHT → CPVC → fixtures', 'Soil → IC → road sewer', 'Greywater → bio-filter'],13,29)
    sh.section(570,846,'03  /  VASTU + DESIGN BASIS',464)
    sh.lines(570,897,['SE café / kitchen · SW admin*', 'NW WC* · north-central swapping',
       '* SW / NW refer to the rear block.', '500 kVA uses a 400 kW AC import cap.',
       '342 kW DC budget after auxiliary load.', '* Cable design and fire access pending.'],14,29)
    sh.section(1066,846,'04  /  COMMERCIAL SCHEDULE',486)
    sh.text(1066,910,'₹18,000 INR',29,INK,True)
    sh.lines(1066,939,['Included in contest · civil / MEP drawing fee',
       'Unlimited revisions until ground execution sign-off',
       'Initial draft delivered Today',
       'Final stamped GFC working set within 48 hours'],13.5,28)
    sh.lines(1066,1050,['Requested target; licensed sign-off and inputs required.',
       'Current issue: coordination drawings, unstamped.'],12,22,ORANGE)
    sh.footer(p,'SCALED PLANS / FULL DETAIL ON P-01')
    return sh


def write_dxf(p,scenes,sheets,path):
    doc=ezdxf.new('R2010'); doc.units=4
    doc.header['$INSUNITS']=4; doc.header['$MEASUREMENT']=1
    doc.header['$LUNITS']=2; doc.header['$LUPREC']=1
    if 'DASHED' not in doc.linetypes: doc.linetypes.new('DASHED',dxfattribs={'pattern':[150,100,-50]})
    for name,(color,aci) in LAYERS.items():
        doc.layers.new(name,dxfattribs={'color':aci,'lineweight':25,'true_color':int(color[1:],16)})
    def emit(space,scene,scale,offset=(0,0),paper=False):
        def pos(pt): return (pt[0]*scale+offset[0],pt[1]*scale+offset[1])
        for e in scene.items:
            at={'layer':e['layer']}; k=e['kind']
            if e.get('dash'): at['linetype']='DASHED'
            if k=='line': space.add_line(pos(e['p'][0]),pos(e['p'][1]),dxfattribs=at)
            elif k=='poly': space.add_lwpolyline([pos(pt) for pt in e['p']],close=e.get('close',False),dxfattribs=at)
            elif k=='circle': space.add_circle(pos(e['c']),e['r']*scale,dxfattribs=at)
            elif k=='arc': space.add_arc(pos(e['c']),e['r']*scale,e['a'],e['b'],dxfattribs=at)
            elif k=='text':
                t=space.add_text(e['text'],dxfattribs={**at,'height':e['size']*scale*.73})
                align={'start':TextEntityAlignment.LEFT,'middle':TextEntityAlignment.CENTER,'end':TextEntityAlignment.RIGHT}[e.get('anchor','start')]
                t.set_placement(pos(e['p']),align=align)
    msp=doc.modelspace()
    for i,(name,sc) in enumerate(scenes):
        dy=-i*110*FT; emit(msp,sc,FT,(0,dy))
        msp.add_text(name,dxfattribs={'height':600,'layer':'TEXT'}).set_placement((0,dy+65*FT))
    # Full surveyed-road allocation is explicit in native CAD, without screen clipping.
    msp.add_lwpolyline([(-p.road_width*FT,0),(0,0),(0,p.frontage*FT),(-p.road_width*FT,p.frontage*FT)],close=True,dxfattribs={'layer':'ROAD'})
    msp.add_text('100 FT MAIN ROAD - WIDTH TO BE VERIFIED BY SURVEY',dxfattribs={'height':400,'layer':'TEXT'}).set_placement((-90*FT,26*FT))
    for x in (p.depth/3,2*p.depth/3): msp.add_line((x*FT,0),(x*FT,p.frontage*FT),dxfattribs={'layer':'VASTU_GRID','linetype':'DASHED'})
    for y in (p.frontage/3,2*p.frontage/3): msp.add_line((0,y*FT),(p.depth*FT,y*FT),dxfattribs={'layer':'VASTU_GRID','linetype':'DASHED'})
    doc.layers.get('VASTU_GRID').off()
    # Native associative-style DIMENSION entities in millimetres, with explicit foot labels.
    for a,b,base,text in [((0,0),(p.depth,0),(0,-12),f'{p.depth:g} ft / {p.depth*FT:.1f} mm'),((0,0),(0,p.frontage),(-28,0),f'{p.frontage:g} ft / {p.frontage*FT:.1f} mm'),((p.depth,p.drive_y),(p.depth,p.frontage),(p.depth+9,0),f'{p.driveway:g} ft CLEAR')]:
        dim=msp.add_linear_dim(base=tuple(v*FT for v in base),p1=tuple(v*FT for v in a),p2=tuple(v*FT for v in b),angle=90 if a[0]==b[0] else 0,text=text,dimstyle='EZDXF',override={'dimtxt':350,'dimasz':180,'dimexo':100,'dimexe':200},dxfattribs={'layer':'DIMENSIONS'}); dim.render()
    for i in range(p.bay_count):
        x=p.bay_start+i*p.bay_width
        dim=msp.add_linear_dim(base=(x*FT,-4*FT),p1=(x*FT,p.bay_y*FT),p2=((x+p.bay_width)*FT,p.bay_y*FT),text=f'{p.bay_width:g} ft',override={'dimtxt':220,'dimasz':100},dxfattribs={'layer':'DIMENSIONS'}); dim.render()
    # Print-ready paper spaces mirror all three vector sheets, in true paper mm.
    for sh in sheets:
        layout=doc.layouts.new(sh.code)
        layout.page_setup(size=(609.6,457.2),margins=(0,0,0,0),units='mm')
        emit(layout,sh.scene,609.6/W)
    doc.set_modelspace_vport(130*FT,center=(p.depth*FT/2,10*FT))
    doc.saveas(path)
    reloaded=ezdxf.readfile(path); audit=reloaded.audit()
    if audit.errors: raise RuntimeError(f'DXF audit errors: {audit.errors}')
    return {'version':reloaded.dxfversion,'units':'millimetres','audit_errors':len(audit.errors),'audit_fixes':len(audit.fixes),'model_entities':len(reloaded.modelspace()),'entity_types':dict(Counter(e.dxftype() for e in reloaded.modelspace())),'layers':list(LAYERS),'paperspaces':[s.code for s in sheets]}


def validate_geometry(p):
    f=p.footprints(); errors=[]
    assert p.depth>p.front_depth>0 and p.frontage>p.driveway>0
    assert p.turn_outer>p.turn_inner>0
    allboxes={**f,**{f'EV {i+1}':(p.bay_start+i*p.bay_width,p.bay_y,p.bay_width,p.bay_length) for i in range(p.bay_count)}}
    def overlap(a,b): return min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])>1e-7 and min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1])>1e-7
    for key,(x,y,w,h) in allboxes.items():
        if not(0<=x<x+w<=p.depth and 0<=y<y+h<=p.drive_y): errors.append(f'{key}: outside plot or obstructs drive')
        if key in ('Office','Cafe','Lawn','Swap','Restrooms') and x<p.front_depth: errors.append(f'{key}: outside rear zone')
    for i,(ka,a) in enumerate(allboxes.items()):
        for kb,b in list(allboxes.items())[i+1:]:
            if overlap(a,b): errors.append(f'Footprints overlap: {ka} / {kb}')
    for i in range(p.bay_count):
        if p.bay_start+(i+1)*p.bay_width>p.front_depth: errors.append('EV bay outside front zone')
    if errors: raise ValueError('; '.join(errors))
    return {'plot_sqft':p.depth*p.frontage,'plot_sqyd':p.depth*p.frontage/9,'front_sqyd':p.front_depth*p.frontage/9,'rear_sqyd':(p.depth-p.front_depth)*p.frontage/9,'clear_drive_ft':p.driveway,'bay_count':p.bay_count,'footprints':allboxes,'footprint_overlap_count':0,'fixed_obstructions_in_drive':0,'turn_radii_ft':[p.turn_outer,p.turn_inner], 'full_vehicle_swept_path_validated':False,'gfc_stamped':False}


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--params',type=Path); args=ap.parse_args()
    p=Spec(**(json.loads(args.params.read_text()) if args.params else {}))
    meta=json.loads((ROOT/'brief_assets/contest_meta.json').read_text()); assert meta['id']==2799418 and meta['type']=='guaranteed'
    for bold in (False,True):
        fp=font_path(bold)
        if not fp: raise RuntimeError('Provide CAD_FONT_REGULAR / CAD_FONT_BOLD TTF font paths')
        FONTS[bold]=Font(fp)
    fallback=Path('/System/Library/Fonts/Supplemental/NotoSansNagMundari-Regular.ttf')
    if fallback.exists(): FONTS['fallback']=Font(fallback)
    OUT.mkdir(exist_ok=True); qa=ROOT/'.build'; qa.mkdir(exist_ok=True)
    report={'geometry':validate_geometry(p),'design_status':'COORDINATION / NOT FOR CONSTRUCTION','unresolved':['Licensed stamping and local approvals unavailable','15 ft maneuver aisle: vehicle-specific swept-path simulation required','14 ft dead-end service corridor is not a certified fire-appliance route','SW office / NW restroom are rear-block, not whole-plot, Vastu positions','500 kVA requires load management; cable ampacity / voltage drop / fault duty not calculated','Road sewer, culvert invert, storm capacity and septic feasibility unverified','Accessible WC and swapping vendor clearance checks required']}
    sheets=[make_c01(p),make_e01(p),make_p01(p)]
    svg_names=['sheet_c01_site_layout.svg','sheet_e01_utility_trenching.svg','sheet_p01_plumbing_vastu.svg']
    doc=fitz.open()
    for sh,name in zip(sheets,svg_names):
        data=sh.svg(); (OUT/name).write_text(data)
        source=fitz.open(stream=data.encode(),filetype='svg'); pdf=fitz.open('pdf',source.convert_to_pdf())
        page=doc.new_page(width=1728,height=1296); page.show_pdf_page(page.rect,pdf,0)
        page.get_pixmap(matrix=fitz.Matrix(1600/1728,1600/1728),alpha=False).save(qa/(name.replace('.svg','.png')))
    pdfpath=OUT/'Khanapur_EV_Hub_Civil_and_Trenching_Set.pdf'; doc.set_metadata({'title':'Khanapur EV Hub | Civil, Electrical & Plumbing Coordination','subject':'Contest 2799418 / Unstamped / Not for construction','author':'Design team'}); doc.save(pdfpath,garbage=4,deflate=True)
    dxfpath=OUT/'Khanapur_EV_Hub_800sqyd_Master.dxf'
    report['dxf']=write_dxf(p,[('C-01 MASTER SITE',civil_scene(p)),('E-01 UTILITIES',utility_scene(p)),('P-01 RESTROOM (NATIVE 1:1)',plumbing_scene(p))],sheets,dxfpath)
    for n,sh in [(1,sheets[0]),(2,make_board2(p))]:
        title='Master site layout' if n==1 else 'Utilities, plumbing and schedules'
        markup=f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=1600,initial-scale=1"><title>Khanapur EV Hub — {title}</title><style>*{{box-sizing:border-box}}html,body{{margin:0;width:1600px;height:1200px;background:{PAPER}}}main,svg{{display:block;width:1600px;height:1200px}}@page{{size:1600px 1200px;margin:0}}</style></head><body><main aria-label="{title}">{sh.svg()}</main></body></html>'
        (ROOT/f'board{n}-codex.html').write_text(markup)
        (qa/f'board{n}.svg').write_text(sh.svg())
        (qa/f'board{n}-text-bounds.json').write_text(json.dumps(sh.text_log,ensure_ascii=False,indent=2))
    with fitz.open(pdfpath) as verify:
        report['pdf']={'pages':len(verify),'page_size_pt':list(verify[0].rect),'raster_images_per_page':[len(pg.get_images()) for pg in verify],'vector_paths_per_page':[len(pg.get_drawings()) for pg in verify]}
        assert len(verify)==3 and all(not pg.get_images() for pg in verify)
    files=[dxfpath,pdfpath]+[OUT/n for n in svg_names]
    zpath=OUT/'Khanapur_EV_Hub_CAD_Package.zip'
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files: z.write(f,f.name)
    with zipfile.ZipFile(zpath) as z: assert z.testzip() is None
    report['archive_members']=[f.name for f in files]
    report['sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (qa/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (OUT/'design_parameters.json').write_text(json.dumps(dataclasses.asdict(p),indent=2))
    print(json.dumps({'status':'generated','files':[str(f.relative_to(ROOT)) for f in files]+[str(zpath.relative_to(ROOT)),'board1-codex.html','board2-codex.html'],'geometry':report['geometry'],'dxf':report['dxf'],'pdf':report['pdf']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
