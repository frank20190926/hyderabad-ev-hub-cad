#!/usr/bin/env python3
"""Claude 侧生成器：board1-claude.html / board2-claude.html / index.html
Contest #2799418 — EV Hub & Café Site Layout, Khanapur Hyderabad (800 sq yd, 50'x144', west-facing)

坐标约定（英尺）：x=0 为西侧临街边界，x=144 为东侧；y=0 为北边界，y=50 为南边界；正北朝上。
只写 board1-claude.html / board2-claude.html / index.html，不碰 Codex 的文件。
"""
import html
import json
import math
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "Menlo,'SF Mono',Consolas,monospace"

# ---- palette (light CAD paper, color-coded zones) ----
INK = "#10213f"
PAPER = "#fbf9f2"
C_EV = ("#d5efe4", "#0b6e55")      # EV bays
C_DRV = ("#fde7b4", "#b06a00")     # driveway
C_TR = ("#f8d3d0", "#b3261e")      # transformer
C_CAFE = ("#ffd9b0", "#c2560a")    # café
C_OFF = ("#cfe0fb", "#1f56b0")     # office
C_SWAP = ("#c9eef2", "#0a7d8c")    # swap canopy
C_WC = ("#e3d4f5", "#6a3aa6")      # restroom
C_LAWN = ("#d9efc2", "#4f8a1e")    # lawn
C_HV = "#d6221f"
C_STORM = "#1769d1"
C_SEWER = "#7a4a1d"
C_WATER = "#0a9aa8"
C_SWEPT = "#c2185b"
C_SWEPT2 = "#00897b"


def esc(s):
    return html.escape(str(s), quote=False)


class Plan:
    """英尺 -> 像素 的映射 + 各图层绘制。每个图层是一个 <g data-layer=...>。"""

    def __init__(self, ox, oy, S):
        self.ox, self.oy, self.S = ox, oy, S

    def X(self, ft):
        return self.ox + ft * self.S

    def Y(self, ft):
        return self.oy + ft * self.S

    def L(self, ft):
        return ft * self.S

    # --- primitives (feet in, svg out) ---
    def rect(self, x, y, w, h, fill="none", stroke=INK, sw=1.2, extra=""):
        return (f'<rect x="{self.X(x):.1f}" y="{self.Y(y):.1f}" width="{self.L(w):.1f}" '
                f'height="{self.L(h):.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.2, extra=""):
        return (f'<line x1="{self.X(x1):.1f}" y1="{self.Y(y1):.1f}" x2="{self.X(x2):.1f}" '
                f'y2="{self.Y(y2):.1f}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def poly(self, pts, stroke=INK, sw=1.5, extra=""):
        s = " ".join(f"{self.X(a):.1f},{self.Y(b):.1f}" for a, b in pts)
        return f'<polyline points="{s}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" {extra}/>'

    def circ(self, x, y, r, fill="none", stroke=INK, sw=1.2, extra=""):
        return (f'<circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="{self.L(r):.1f}" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def text(self, x, y, s, size=12, anchor="middle", fill=INK, weight=400, font=SANS, extra=""):
        return (f'<text x="{self.X(x):.1f}" y="{self.Y(y):.1f}" font-family="{font}" font-size="{size}" '
                f'text-anchor="{anchor}" fill="{fill}" font-weight="{weight}" class="h" {extra}>{esc(s)}</text>')

    def lines(self, x, y, arr, size=12, gap=15, anchor="middle", fill=INK, weight=400, font=SANS):
        out = []
        for i, a in enumerate(arr):
            w = weight
            f = fill
            if isinstance(a, tuple):
                a, w, f = (a + (weight, fill))[:3] if len(a) < 3 else a
            out.append(self.text(x, y, a, size, anchor, f, w, font, extra=f'dy="{i*gap}"'))
        return "".join(out)

    def bubble(self, x, y, n, fill="#10213f"):
        return (f'<g><circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="9.5" fill="{fill}"/>'
                f'<text x="{self.X(x):.1f}" y="{self.Y(y)+4:.1f}" font-family="{SANS}" font-size="11" '
                f'text-anchor="middle" fill="#fff" font-weight="700">{n}</text></g>')

    def arc(self, cx, cy, r, a0, a1, stroke, sw=1.6, extra=""):
        """ft 圆心/半径，角度（度，数学方向，y 向上），弧从 a0 到 a1 逆时针。"""
        def pt(a):
            return (self.X(cx + r * math.cos(math.radians(a))), self.Y(cy - r * math.sin(math.radians(a))))
        x0, y0 = pt(a0)
        x1, y1 = pt(a1)
        large = 1 if (a1 - a0) % 360 > 180 else 0
        # 屏幕坐标 y 向下，数学逆时针 = 屏幕 sweep-flag 0
        return (f'<path d="M{x0:.1f},{y0:.1f} A{self.L(r):.1f},{self.L(r):.1f} 0 {large} 0 {x1:.1f},{y1:.1f}" '
                f'fill="none" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    # --- dimension helpers (pixel y / x for the dim line) ---
    def dim_h(self, x1, x2, ypx, label, size=12, color=INK, above=True):
        a, b = self.X(x1), self.X(x2)
        ty = ypx - 5 if above else ypx + 15
        return (f'<g stroke="{color}" stroke-width="1" fill="none">'
                f'<line x1="{a:.1f}" y1="{ypx}" x2="{b:.1f}" y2="{ypx}"/>'
                f'<line x1="{a:.1f}" y1="{ypx-6}" x2="{a:.1f}" y2="{ypx+6}"/>'
                f'<line x1="{b:.1f}" y1="{ypx-6}" x2="{b:.1f}" y2="{ypx+6}"/>'
                f'<line x1="{a-4:.1f}" y1="{ypx+4}" x2="{a+4:.1f}" y2="{ypx-4}" stroke-width="1.8"/>'
                f'<line x1="{b-4:.1f}" y1="{ypx+4}" x2="{b+4:.1f}" y2="{ypx-4}" stroke-width="1.8"/></g>'
                f'<text x="{(a+b)/2:.1f}" y="{ty}" font-family="{MONO}" font-size="{size}" text-anchor="middle" '
                f'fill="{color}" font-weight="600" class="h">{esc(label)}</text>')

    def dim_v(self, y1, y2, xpx, label, size=12, color=INK, tx=-6):
        a, b = self.Y(y1), self.Y(y2)
        cx = xpx + tx
        return (f'<g stroke="{color}" stroke-width="1" fill="none">'
                f'<line x1="{xpx}" y1="{a:.1f}" x2="{xpx}" y2="{b:.1f}"/>'
                f'<line x1="{xpx-6}" y1="{a:.1f}" x2="{xpx+6}" y2="{a:.1f}"/>'
                f'<line x1="{xpx-6}" y1="{b:.1f}" x2="{xpx+6}" y2="{b:.1f}"/>'
                f'<line x1="{xpx-4}" y1="{a+4:.1f}" x2="{xpx+4}" y2="{a-4:.1f}" stroke-width="1.8"/>'
                f'<line x1="{xpx-4}" y1="{b+4:.1f}" x2="{xpx+4}" y2="{b-4:.1f}" stroke-width="1.8"/></g>'
                f'<text transform="translate({cx},{(a+b)/2:.1f}) rotate(-90)" font-family="{MONO}" font-size="{size}" '
                f'text-anchor="middle" fill="{color}" font-weight="600" class="h">{esc(label)}</text>')


BAY_X0, BAY_W, BAY_Y0, BAY_D = 30, 9, 32, 18
BAY_XC = [BAY_X0 + BAY_W * i + BAY_W / 2 for i in range(6)]


def g(layer, body, label=""):
    return f'<g class="layer" data-layer="{layer}" data-label="{esc(label)}">{body}</g>'


# ============================== LAYERS ==============================
def layer_base(p):
    o = []
    # site paper
    o.append(p.rect(0, 0, 144, 50, "#fffef9", INK, 3.4))
    # curb cuts (entry / exit) openings on west boundary
    o.append(p.line(0, 1, 0, 13, "#fffef9", 5))
    o.append(p.line(0, 36, 0, 48, "#fffef9", 5))
    for yy in (1, 13, 36, 48):
        o.append(p.line(-2.2, yy, 0, yy, INK, 2))
    return g("base", "".join(o), "Site boundary")


def layer_driveway(p):
    o = []
    o.append(p.rect(0, 0, 144, 14, C_DRV[0], C_DRV[1], 1.8))
    o.append(p.line(0, 7, 144, 7, C_DRV[1], 1, 'stroke-dasharray="14 6 3 6"'))
    for x in (12, 40, 70, 100, 130):
        o.append(f'<path d="M{p.X(x):.1f},{p.Y(7)-14:.1f} l16,14 l-16,14 l0,-8 l-22,0 l0,-12 l22,0 z" fill="{C_DRV[1]}" opacity=".16"/>')
    o.append(p.text(72, 4.2, "14′-0″ CLEAR SIDE PASSAGE DRIVEWAY — UNBLOCKED, STRAIGHT 144′-0″ FROM WEST ROAD TO REAR ZONE",
                    12, "middle", "#6b3f00", 700))
    o.append(p.text(72, 11.4, "ENTRY LANE → (ONE-WAY IN)  ·  NO PARKING / NO STORAGE  ·  FIRE-TENDER ACCESS", 11.5, "middle", "#6b3f00", 500))
    o.append(p.bubble(2.0, 3.2, 1, C_DRV[1]))
    return g("driveway", "".join(o), "14 ft Driveway")


def layer_evbays(p):
    o = []
    o.append(p.rect(0, 14, 90, 36, "#eef8f3", C_EV[1], 0.8, 'stroke-dasharray="3 4" opacity=".9"'))
    # exit lane
    o.append(p.rect(0, 28, 30, 22, "#e1efe8", "none", 0))
    o.append(p.text(15, 43.2, "EXIT LANE", 12, "middle", C_EV[1], 700))
    o.append(p.text(15, 45.4, "12′ CURB CUT →", 11, "middle", C_EV[1], 500))
    # bays
    for i, xc in enumerate(BAY_XC):
        x0 = BAY_X0 + BAY_W * i
        o.append(p.rect(x0, BAY_Y0, BAY_W, BAY_D, C_EV[0], C_EV[1], 1.6))
        # vehicle envelope
        o.append(p.rect(xc - 3.25, 33.2, 6.5, 13.2, "none", C_EV[1], 0.9, 'rx="9" stroke-dasharray="4 3" opacity=".75"'))
        o.append(p.line(xc - 3, 47.4, xc + 3, 47.4, INK, 2.4))                       # wheel stop
        o.append(p.rect(xc - 1.4, 48.1, 2.8, 1.8, C_EV[1], INK, 0.8))                # charger pedestal
        o.append(p.circ(xc - 0.55, 48.4, 0.25, "#fff", "#fff", 0.5))                 # CCS2 gun
        o.append(p.circ(xc + 0.55, 48.4, 0.25, "#fff", "#fff", 0.5))
        for bx in (xc - 3.3, xc + 3.3):
            o.append(p.circ(bx, 49.2, 0.5, "#ffd400", INK, 1.2))                     # bollard
        o.append(f'<circle cx="{p.X(xc):.1f}" cy="{p.Y(37.6):.1f}" r="12" fill="{C_EV[1]}"/>'
                 f'<text x="{p.X(xc):.1f}" y="{p.Y(37.6)+5:.1f}" font-family="{SANS}" font-size="14" font-weight="800" '
                 f'text-anchor="middle" fill="#fff">{i+1}</text>')
        o.append(p.text(xc, 41.4, "9′×18′", 11.5, "middle", C_EV[1], 700))
        o.append(p.text(xc, 43.0, f"DC-{i+1}", 11, "middle", C_EV[1], 600))
    o.append(p.lines(15, 36.0, [("6 × DC FAST-CHARGING", 800, C_EV[1]), ("BAYS · DUAL-GUN CCS2", 800, C_EV[1]),
                                ("12 safety bollards", 500, C_EV[1])], 11.5, 13))
    o.append(p.text(21, 16.4, "FRONT ZONE 50′×90′ = 500 SQ.YDS", 12, "start", C_EV[1], 700))
    o.append(p.bubble(2.0, 40.0, 2, C_EV[1]))
    return g("evbays", "".join(o), "EV Bays")


def layer_swept(p):
    o = []
    for xc in BAY_XC:
        # R=24' turn-in (solid), tangent vertical at bay mouth
        o.append(p.arc(xc - 24, 32, 24, 0, math.degrees(math.asin(15 / 24)), C_SWEPT, 1.7))
        # R=14' reverse-out (dashed), mirrored toward exit (west)
        o.append(p.arc(xc - 14, 32, 14, 0, 90, C_SWEPT2, 1.5,
                       'stroke-dasharray="5 3"'))
    # arrowheads at bay mouth (turn-in)
    for xc in BAY_XC:
        o.append(f'<path d="M{p.X(xc)-5:.1f},{p.Y(32)-9:.1f} L{p.X(xc):.1f},{p.Y(32)+2:.1f} L{p.X(xc)+5:.1f},{p.Y(32)-9:.1f} z" fill="{C_SWEPT}"/>')
    o.append(p.text(77, 16.4, "R=24′ TURN-IN", 12, "end", C_SWEPT, 800))
    o.append(p.text(89, 16.4, "R=14′ REVERSE", 12, "end", C_SWEPT2, 800))
    return g("swept", "".join(o), "Swept-Path Arcs")


def layer_tssp(p):
    o = []
    o.append(p.rect(0, 14, 16, 14, "url(#hatchRed)", C_TR[1], 2.2))
    o.append(p.rect(0, 14, 16, 14, "none", "#fff", 0.8, 'stroke-dasharray="6 4"'))
    o.append(p.rect(5.2, 21.0, 5.6, 4.4, C_TR[1], INK, 1.2))                    # transformer
    o.append(p.circ(7, 23.2, 0.9, "#fff", "#fff", 1))
    o.append(p.circ(9, 23.2, 0.9, "#fff", "#fff", 1))
    o.append(p.line(4, 28, 12, 28, "#fffef9", 4))                              # gate opening
    o.append(p.arc(4, 28, 8, 0, 90, C_TR[1], 1.2, 'stroke-dasharray="3 3"'))
    o.append(p.lines(8, 17.2, [("TSSPDCL", 800, C_TR[1]), ("TRANSFORMER YARD", 700, C_TR[1]), ("16′×14′ FENCED", 600, C_TR[1])],
                     11.5, 13))
    o.append(p.text(8, 26.7, "GATE 8′ ↓", 11, "middle", C_TR[1], 700))
    o.append(p.rect(17, 20, 2, 2, "#2b2b2b", INK, 1))                           # LT feeder pillar
    o.append(p.bubble(18, 18.2, 3, C_TR[1]))
    return g("tsspdcl", "".join(o), "TSSPDCL Yard")


def layer_rear(p):
    o = []
    o.append(p.rect(90, 14, 54, 36, "#f6f2e8", C_CAFE[1], 0.8, 'stroke-dasharray="3 4"'))
    o.append(p.rect(105, 14, 28, 24, "url(#dotsLawn)", C_LAWN[1], 1.6))
    o.append(p.lines(119, 26.2, [("OUTDOOR LAWN SEATING", 800, C_LAWN[1]), ("28′ × 24′", 700, C_LAWN[1]),
                                 ("café-side · ~16 seats", 500, C_LAWN[1])], 12, 15))
    # café (SE)
    o.append(p.rect(124, 40, 20, 10, C_CAFE[0], C_CAFE[1], 2.2))
    o.append(p.lines(134, 44.0, [("CONTAINER CAFÉ", 800, C_CAFE[1]), ("20′×10′ · SE (AGNI)", 600, C_CAFE[1])], 12, 14))
    # office (SW)
    o.append(p.rect(91, 40, 20, 10, C_OFF[0], C_OFF[1], 2.2))
    o.append(p.lines(101, 44.0, [("CONTAINER OFFICE", 800, C_OFF[1]), ("20′×10′ · SW (NAIRUTYA)", 600, C_OFF[1])], 12, 14))
    # canopy (NE)
    o.append(p.rect(134, 14, 10, 10, C_SWAP[0], C_SWAP[1], 2.2))
    o.append(p.rect(134.6, 14.6, 8.8, 8.8, "none", C_SWAP[1], 0.9, 'stroke-dasharray="4 3"'))
    o.append(p.lines(139, 18.6, [("BATTERY SWAP", 800, C_SWAP[1]), ("CANOPY 10′×10′", 700, C_SWAP[1]), ("NE (ISHANYA)", 600, C_SWAP[1])], 11, 13))
    o.append(p.text(139, 28.6, "SWAP APRON", 11, "middle", C_SWAP[1], 700))
    o.append(p.text(139, 30.3, "(drive access)", 10.5, "middle", C_SWAP[1], 500))
    # restroom block NW (Vayu)
    o.append(p.rect(91, 14, 12, 10, C_WC[0], C_WC[1], 2.2))
    for xx in (95, 99):
        o.append(p.line(xx, 14, xx, 21, C_WC[1], 1.2))
    o.append(p.line(91, 21, 103, 21, C_WC[1], 1.2))
    for xx, s in ((93, "M"), (97, "F"), (101, "A")):
        o.append(p.text(xx, 18.4, s, 14, "middle", C_WC[1], 800))
    o.append(p.text(97, 23.1, "RESTROOM 12′×10′", 10.5, "middle", C_WC[1], 700))
    # septic tank
    o.append(p.rect(91, 32.5, 8, 5, "#eee6dc", C_SEWER, 1.4))
    o.append(p.text(95, 35.6, "SEPTIC TANK", 10.5, "middle", C_SEWER, 700))
    # service yard
    o.append(p.text(117.5, 46.0, "SERVICE / WASTE", 11, "middle", "#6b6b6b", 600))
    o.append(p.text(117.5, 47.6, "YARD", 11, "middle", "#6b6b6b", 600))
    return g("rear", "".join(o), "Rear Containers")


def trench_path(p, pts, w_ft=2.0, extra=""):
    """RCC 600mm (~2ft) 沟：粗虚线中心线 + 外轮廓。"""
    return (p.poly(pts, C_HV, w_ft * p.S * 0.36, f'opacity=".28" {extra}') +
            p.poly(pts, C_HV, 2.2, 'stroke-dasharray="11 4"'))


def layer_hv(p):
    o = []
    # 11kV HT incoming from road pole to transformer
    o.append(p.poly([(-4.5, 21.5), (5.2, 21.5)], C_HV, 3.4))
    o.append(p.text(-0.6, 19.4, "11kV HT", 11, "end", C_HV, 800))
    # LT cable pillar -> trenches
    T1 = [(18, 22), (18, 47), (89, 47), (89, 39)]
    T2 = [(89, 39), (139, 39), (139, 24)]
    T3 = [(89, 47), (89, 19), (91, 19)]
    for t in (T1, T2, T3):
        o.append(trench_path(p, t))
    # spurs to chargers
    for xc in BAY_XC:
        o.append(p.line(xc, 47, xc, 48.4, C_HV, 2))
        o.append(p.circ(xc, 47, 0.38, C_HV, "#fff", 0.8))
    # spurs to office / café
    o.append(p.line(101, 39, 101, 40, C_HV, 2.2))
    o.append(p.line(134, 39, 134, 40, C_HV, 2.2))
    # handholes
    for hx, hy in ((18, 34), (54, 47), (89, 31), (120, 39)):
        o.append(p.rect(hx - 0.9, hy - 0.9, 1.8, 1.8, "#fff", C_HV, 1.6))
    # labels
    o.append(p.lines(55, 20.2, [("TRUNK 1 · 11kV HT → TSSPDCL TRANSFORMER", 800, C_HV), ("→ LT FEEDER PILLAR → 600×900 RCC TRENCH", 800, C_HV),
                                ("→ SPURS TO 6 DC CHARGERS", 800, C_HV)], 11, 13))
    o.append(p.text(119, 36.3, "TRUNK 2 → OFFICE · CAFÉ · SWAP", 10.5, "middle", C_HV, 800))
    o.append(p.bubble(18, 33, 4, C_HV))
    return g("hv", "".join(o), "HV Electrical Trench")


def layer_drain(p):
    o = []
    # 300mm storm drain y=30, fall to west, outfall to road drain
    o.append(p.line(144, 30, 0, 30, C_STORM, 5, 'opacity=".55"'))
    o.append(p.line(144, 30, 0, 30, C_STORM, 1.3))
    for mx in (140, 110, 80, 50, 20):
        o.append(p.circ(mx, 30, 1.1, "#fff", C_STORM, 2))
    o.append(p.text(70, 28.7, "Ø300 STORM DRAIN @1:150 FALL → ROAD DRAIN", 11, "middle", C_STORM, 800))
        # 150mm sewer restroom -> septic
    o.append(p.line(96, 24, 96, 32.5, C_SEWER, 3.4))
    o.append(p.text(98.2, 27.4, "Ø150 SEWER", 10.5, "start", C_SEWER, 800))
    # 50mm water main y=12.8 -> restroom, office, café
    o.append(p.poly([(0, 12.8), (94, 12.8), (94, 14)], C_WATER, 2.4, 'stroke-dasharray="9 3"'))
    o.append(p.poly([(90.6, 12.8), (90.6, 41)], C_WATER, 2.0, 'stroke-dasharray="9 3"'))
    o.append(p.poly([(133.5, 12.8), (133.5, 40)], C_WATER, 2.0, 'stroke-dasharray="9 3"'))
    o.append(p.poly([(94, 12.8), (133.5, 12.8)], C_WATER, 2.4, 'stroke-dasharray="9 3"'))
    o.append(p.text(48, 11.8, "Ø50 WATER MAIN (BOREWELL/ HMWSSB TAP)", 11, "middle", C_WATER, 800))
    return g("drain", "".join(o), "Drainage & Plumbing")


def layer_vastu(p):
    o = []
    for i in (1, 2):
        o.append(p.line(48 * i, 0, 48 * i, 50, "#6a3aa6", 1.0, 'stroke-dasharray="2 5" opacity=".8"'))
    for j in (1, 2):
        yy = 50 / 3 * j
        o.append(p.line(0, yy, 144, yy, "#6a3aa6", 1.0, 'stroke-dasharray="2 5" opacity=".8"'))
    tags = [("NW", 1, 2.2), ("N · KUBERA", 49, 2.2), ("NE", 133, 2.2),
            ("W", 1, 31.4), ("CENTRE · BRAHMASTHAN", 49, 25.6), ("E", 136, 26.4),
            ("SW", 1, 48.8), ("S · YAMA", 49, 33.6), ("SE", 135, 36.6)]
    full = {"NW": "NW · VAYU", "NE": "NE · ISHANYA", "W": "W · VARUNA", "E": "E · INDRA", "SW": "SW · NAIRUTYA", "SE": "SE · AGNI"}
    for lbl, x, y in tags:
        lbl = full.get(lbl, lbl)
        wpx = len(lbl) * 6.6 + 10
        if lbl.startswith("NE"):
            x = 144 - 1 - wpx / p.S
        o.append(f'<rect x="{p.X(x):.1f}" y="{p.Y(y)-11:.1f}" width="{wpx:.1f}" height="15" rx="3" fill="#6a3aa6" opacity=".95"/>')
        o.append(f'<text x="{p.X(x)+5:.1f}" y="{p.Y(y):.1f}" font-family="{SANS}" font-size="10" font-weight="700" fill="#fff">{esc(lbl)}</text>')
    return g("vastu", "".join(o), "Vastu Grid")


DEFS = f'''<defs>
<pattern id="hatchRed" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<rect width="8" height="8" fill="{C_TR[0]}"/><line x1="0" y1="0" x2="0" y2="8" stroke="{C_TR[1]}" stroke-width="1.6" opacity=".55"/></pattern>
<pattern id="dotsLawn" width="9" height="9" patternUnits="userSpaceOnUse"><rect width="9" height="9" fill="{C_LAWN[0]}"/>
<circle cx="2" cy="2" r="1" fill="{C_LAWN[1]}" opacity=".55"/><circle cx="6.5" cy="6" r="1" fill="{C_LAWN[1]}" opacity=".55"/></pattern>
<pattern id="roadHatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(-30)">
<rect width="10" height="10" fill="#e3e5ea"/><line x1="0" y1="0" x2="0" y2="10" stroke="#c8ccd4" stroke-width="1"/></pattern>
</defs>'''

CSS = f'''text.h{{paint-order:stroke;stroke:{PAPER};stroke-width:3px;stroke-linejoin:round}}
.layer.off{{display:none}}'''


def road(p, x0, x1, y0, y1, mid_label=True):
    o = [f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="url(#roadHatch)" stroke="{INK}" stroke-width="1.4"/>']
    cx = (x0 + x1) / 2
    o.append(f'<line x1="{x0+(x1-x0)*0.28:.0f}" y1="{y0}" x2="{x0+(x1-x0)*0.28:.0f}" y2="{y1}" stroke="#fff" stroke-width="2" stroke-dasharray="18 12"/>')
    # sidewalk strip
    o.append(f'<rect x="{x1}" y="{y0}" width="{p.X(0)-x1:.1f}" height="{y1-y0}" fill="#f0ece0" stroke="{INK}" stroke-width="0.8"/>')
    return "".join(o)


def north_arrow(cx, cy, r=26):
    return (f'<g><circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="{INK}" stroke-width="1.6"/>'
            f'<path d="M{cx},{cy-r+3} L{cx+9},{cy+8} L{cx},{cy+3} L{cx-9},{cy+8} z" fill="{INK}"/>'
            f'<text x="{cx}" y="{cy-r-5}" font-family="{SANS}" font-size="13" font-weight="800" text-anchor="middle" fill="{INK}">N</text>'
            f'<text x="{cx-r-8}" y="{cy+4}" font-family="{SANS}" font-size="11" font-weight="700" text-anchor="middle" fill="{C_DRV[1]}">W</text></g>')


def panel(x, y, w, h, title, body="", color=INK):
    return (f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="{INK}" stroke-width="1.2"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="22" fill="{color}"/>'
            f'<text x="{x+8}" y="{y+15}" font-family="{SANS}" font-size="12" font-weight="800" fill="#fff" letter-spacing=".4">{esc(title)}</text>'
            f'{body}</g>')


def tx(x, y, s, size=12, anchor="start", fill=INK, weight=400, font=SANS, extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
            f'font-weight="{weight}" {extra}>{esc(s)}</text>')


def titleblock(x, y, w, h, sheet, name, sub):
    return (f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="{INK}" stroke-width="2.4"/>'
            f'<line x1="{x+760}" y1="{y}" x2="{x+760}" y2="{y+h}" stroke="{INK}" stroke-width="1.2"/>'
            + tx(x + 14, y + 26, "CONTEST #2799418 · EV HUB & CAFÉ SITE LAYOUT · KHANAPUR, HYDERABAD", 13, "start", INK, 800)
            + tx(x + 14, y + 48, name, 17, "start", INK, 800)
            + tx(x + 14, y + 68, sub, 12, "start", "#44506b", 500)
            + tx(x + 14, y + h - 10, "PLOT 800 SQ.YDS (7,200 SQ.FT) · 50′×144′ · WEST-FACING (VASTU) · FACING 100′ MAIN ROAD · ALL DIMENSIONS IN FEET-INCHES",
                 11, "start", "#44506b", 500)
            + tx(x + 780, y + 26, "SHEET", 11, "start", "#44506b", 700)
            + tx(x + 780, y + 62, sheet, 30, "start", INK, 800)
            + tx(x + 960, y + 26, "SCALE", 11, "start", "#44506b", 700)
            + tx(x + 960, y + 52, "1″ = 12′-0″ (SVG)", 13, "start", INK, 700)
            + tx(x + 960, y + 74, "SIZE 1600×1200 px", 11, "start", "#44506b", 500)
            + tx(x + 1130, y + 26, "STATUS", 11, "start", "#44506b", 700)
            + tx(x + 1130, y + 52, "GFC DRAFT", 14, "start", INK, 800)
            + tx(x + 1130, y + 74, "REV 0 · 08-NOV-2026", 11, "start", "#44506b", 500)
            + '</g>')


def swatch_row(x, y, items, gap=0, size=12):
    out = []
    cx = x
    for color, label in items:
        out.append(f'<rect x="{cx}" y="{y-10}" width="14" height="12" fill="{color[0] if isinstance(color, tuple) else color}" '
                   f'stroke="{color[1] if isinstance(color, tuple) else INK}" stroke-width="1.2"/>')
        out.append(tx(cx + 20, y, label, size, "start", INK, 600))
        cx += 20 + len(label) * size * 0.58 + 22
    return "".join(out)


def page(title, body, extra_css=""):
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>html,body{{margin:0;padding:0;background:#fff}}
.board{{width:1600px;height:1200px;overflow:hidden;position:relative;background:{PAPER}}}
svg{{display:block}}{CSS}{extra_css}</style></head>
<body><div class="board">{body}</div></body></html>'''


# ============================== BOARD 1 ==============================
def board1():
    S, OX, OY = 9.7, 125, 330
    p = Plan(OX, OY, S)
    VT, VB = 76, 1040  # plan viewport
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1200" viewBox="0 0 1600 1200">{DEFS}']
    o.append(f'<rect width="1600" height="1200" fill="{PAPER}"/>')
    # header
    o.append(f'<rect x="0" y="0" width="1600" height="64" fill="{INK}"/>')
    o.append(tx(24, 28, "SHEET C-01 — MASTER 2D AUTOCAD CIVIL SITE LAYOUT & SWEPT-PATH PLAN", 22, "start", "#fff", 800))
    o.append(tx(24, 52, "KHANAPUR, HYDERABAD · 800 SQ.YDS · 50′ × 144′ WEST-FACING VASTU SITE · EV FAST-CHARGING HUB + CONTAINER CAFÉ", 13, "start", "#bcd0f5", 500))
    o.append(tx(1576, 28, "₹18,000 INR · UNLIMITED REVISIONS · 48 h FINAL GFC SET", 13, "end", "#ffd37a", 800))
    o.append(tx(1576, 52, "Guaranteed Contest #2799418", 12, "end", "#bcd0f5", 500))
    # viewport frame
    o.append(f'<rect x="20" y="{VT}" width="1560" height="{VB-VT}" fill="#fffefa" stroke="{INK}" stroke-width="2.4"/>')
    o.append(road(p, 28, 112, VT + 2, 862))
    # road labels
    o.append(f'<text transform="translate(52,{OY+240}) rotate(-90)" font-family="{SANS}" font-size="15" font-weight="800" text-anchor="middle" fill="{INK}" class="h">100 FT WIDE MAIN ROAD</text>')
    o.append(f'<text transform="translate(36,{OY+240}) rotate(-90)" font-family="{SANS}" font-size="10.5" text-anchor="middle" fill="#555" class="h">(road width not to scale)</text>')
    o.append(f'<text x="94" y="{p.Y(7)-6:.0f}" font-family="{SANS}" font-size="12" font-weight="800" text-anchor="middle" fill="{C_DRV[1]}" class="h">ENTRY</text>')
    o.append(f'<text x="94" y="{p.Y(7)+10:.0f}" font-family="{SANS}" font-size="11" text-anchor="middle" fill="{C_DRV[1]}" class="h">12′ CUT →</text>')
    o.append(f'<text x="94" y="{p.Y(42)-6:.0f}" font-family="{SANS}" font-size="12" font-weight="800" text-anchor="middle" fill="{C_EV[1]}" class="h">← EXIT</text>')
    o.append(f'<text x="94" y="{p.Y(42)+10:.0f}" font-family="{SANS}" font-size="11" text-anchor="middle" fill="{C_EV[1]}" class="h">12′ CUT</text>')
    # layers
    o.append(layer_base(p))
    o.append(layer_evbays(p))
    o.append(layer_rear(p))
    o.append(layer_driveway(p))
    o.append(layer_tssp(p))
    o.append(layer_swept(p))
    o.append(layer_vastu(p))
    # dimension chains
    o.append(p.dim_h(0, 90, 296, "FRONT ZONE 90′-0″ (500 SQ.YDS)", 12, C_EV[1]))
    o.append(p.dim_h(90, 144, 296, "REAR ZONE 54′-0″ (300 SQ.YDS)", 12, C_CAFE[1]))
    o.append(p.dim_h(0, 144, 318, "OVERALL DEPTH 144′-0″ (EAST–WEST)", 12, INK))
    o.append(p.dim_h(0, 30, 846, "30′-0″ EXIT", 12))
    o.append(p.dim_h(30, 84, 846, "6 BAYS × 9′-0″ = 54′-0″", 12, C_EV[1]))
    o.append(p.dim_h(84, 144, 846, "60′-0″ TO REAR ZONE", 12))
    o.append(p.dim_v(0, 14, 1542, "14′ DRIVEWAY", 11, C_DRV[1], -6))
    o.append(p.dim_v(0, 50, 1566, "FRONTAGE 50′-0″", 12, INK, -6))
    # insets above the plan
    ix, iy, ih = 36, 88, 164
    # A typical bay
    bay = []
    s7 = 6.2
    bx, by = ix + 28, iy + 40
    bay.append(f'<rect x="{bx}" y="{by}" width="{9*s7}" height="{18*s7:.0f}" fill="{C_EV[0]}" stroke="{C_EV[1]}" stroke-width="1.6"/>')
    bay.append(f'<rect x="{bx+9*s7/2-10}" y="{by+18*s7-14}" width="20" height="12" fill="{C_EV[1]}" stroke="{INK}"/>')
    bay.append(f'<circle cx="{bx+9*s7/2-4}" cy="{by+18*s7-8}" r="2.2" fill="#fff"/><circle cx="{bx+9*s7/2+4}" cy="{by+18*s7-8}" r="2.2" fill="#fff"/>')
    for bxx in (bx + 9, bx + 9 * s7 - 9):
        bay.append(f'<circle cx="{bxx}" cy="{by+18*s7-4}" r="4" fill="#ffd400" stroke="{INK}" stroke-width="1.2"/>')
    bay.append(f'<line x1="{bx+12}" y1="{by+18*s7-22}" x2="{bx+9*s7-12}" y2="{by+18*s7-22}" stroke="{INK}" stroke-width="2.6"/>')
    bay.append(tx(bx + 9 * s7 / 2, by + 50, "9′×18′", 13, "middle", C_EV[1], 800))
    bay.append(tx(bx + 9 * s7 + 12, by + 22, "Dual-gun CCS2 DC", 11.5, "start", INK, 700))
    bay.append(tx(bx + 9 * s7 + 12, by + 36, "pedestal 150 kW", 11.5, "start", INK, 600))
    bay.append(tx(bx + 9 * s7 + 12, by + 62, "Bollards Ø6″ ×2", 11.5, "start", INK, 600))
    bay.append(tx(bx + 9 * s7 + 12, by + 76, "Wheel stop 6″", 11.5, "start", INK, 600))
    o.append(panel(ix - 8, iy - 4, 262, ih + 4, "TYPICAL DC BAY DETAIL", "".join(bay), C_EV[1]))
    # B swept legend
    sw = []
    sx, sy = 320, iy + 40
    sw.append(f'<path d="M{sx},{sy+64} A64,64 0 0 0 {sx+64},{sy}" fill="none" stroke="{C_SWEPT}" stroke-width="2.6"/>')
    sw.append(tx(sx + 84, sy + 30, "R = 24′  TURN-IN", 12, "start", C_SWEPT, 800))
    sw.append(tx(sx + 84, sy + 45, "front-in from 18′ aisle", 11, "start", INK, 500))
    sw.append(f'<path d="M{sx},{sy+114} A42,42 0 0 0 {sx+42},{sy+72}" fill="none" stroke="{C_SWEPT2}" stroke-width="2.4" stroke-dasharray="6 4"/>')
    sw.append(tx(sx + 84, sy + 94, "R = 14′  REVERSE-OUT", 12, "start", C_SWEPT2, 800))
    sw.append(tx(sx + 84, sy + 109, "back out toward exit lane", 11, "start", INK, 500))
    o.append(panel(300, iy - 4, 300, ih + 4, "SWEPT-PATH LEGEND", "".join(sw), C_SWEPT))
    # C area schedule
    rows = [("FRONT ZONE", "50′×90′", "4,500 sf", "500 sy"), ("REAR ZONE", "50′×54′", "2,700 sf", "300 sy"),
            ("TOTAL SITE", "50′×144′", "7,200 sf", "800 sy"), ("DRIVEWAY", "14′×144′", "2,016 sf", "224 sy")]
    sc = [tx(618, iy + 38, "ZONE", 11, "start", "#44506b", 800), tx(724, iy + 38, "SIZE", 11, "start", "#44506b", 800),
          tx(812, iy + 38, "AREA", 11, "start", "#44506b", 800), tx(884, iy + 38, "SQ.YD", 11, "start", "#44506b", 800)]
    for i, r in enumerate(rows):
        yy = iy + 62 + i * 24
        sc.append(f'<line x1="610" y1="{yy-16}" x2="942" y2="{yy-16}" stroke="#c9ceda" stroke-width="1"/>')
        for xx, s, wgt in ((618, r[0], 800), (724, r[1], 600), (812, r[2], 600), (884, r[3], 800)):
            sc.append(tx(xx, yy, s, 12, "start", INK, wgt))
    o.append(panel(602, iy - 4, 350, ih + 4, "AREA SCHEDULE", "".join(sc), INK))
    # D keynotes: orientation + vastu
    vn = [tx(978, iy + 42, "VASTU PLACEMENT (WEST-FACING)", 12, "start", C_WC[1], 800),
          tx(978, iy + 62, "NE  Ishanya   — Battery-swap canopy", 11.5, "start", INK, 500),
          tx(978, iy + 78, "NW  Vayu      — Restroom block", 11.5, "start", INK, 500),
          tx(978, iy + 94, "SE  Agni      — Café + lawn seating", 11.5, "start", INK, 500),
          tx(978, iy + 110, "SW  Nairutya  — Office container", 11.5, "start", INK, 500),
          tx(978, iy + 126, "Centre (Brahmasthan) kept open", 11.5, "start", INK, 500)]
    o.append(panel(968, iy - 4, 320, ih + 4, "VASTU / ORIENTATION", "".join(vn), C_WC[1]))
    o.append(north_arrow(1342, iy + 70))
    o.append(tx(1388, iy + 40, "WEST-FACING", 12, "start", INK, 800))
    o.append(tx(1388, iy + 56, "Road on LEFT (west)", 11, "start", "#44506b", 500))
    o.append(tx(1388, iy + 72, "North = TOP of sheet", 11, "start", "#44506b", 500))
    # scale bar
    o.append(f'<g><rect x="1344" y="{iy+124}" width="{10*S:.0f}" height="6" fill="{INK}"/><rect x="{1344+10*S:.0f}" y="{iy+124}" width="{10*S:.0f}" height="6" fill="#fff" stroke="{INK}"/></g>')
    for k, lb in enumerate(("0", "10′", "20′")):
        o.append(tx(1344 + k * 10 * S, iy + 146, lb, 11, "middle", INK, 600, MONO))
    # key table below plan
    ky = 878
    o.append(f'<line x1="40" y1="{ky-14}" x2="1560" y2="{ky-14}" stroke="{INK}" stroke-width="1"/>')
    o.append(tx(40, ky + 4, "KEY NOTES", 13, "start", INK, 800))
    notes = [
        (1, C_DRV[1], "ENTRY curb cut 12′ (north) leads straight into the 14′ side passage along the north boundary."),
        (2, C_EV[1], "EXIT curb cut 12′ at SW; exit lane 30′ wide, clear of bays and separate from entry."),
        (3, C_TR[1], "TSSPDCL yard 16′×14′, fenced, NW of front zone, south of the driveway; 8′ gate; LT pillar beside."),
        ("•", C_EV[1], "6 DC bays 9′×18′ on the south edge (54′ row), 18′ aisle in front, dual-gun CCS2, 2 bollards each."),
        ("•", C_SWEPT, "Turn-in R=24′ (solid) and reverse-out R=14′ (dashed) per bay; arcs stay clear of the 14′ driveway."),
        ("•", C_CAFE[1], "Rear: café 20′×10′ SE + lawn 28′×24′, office 20′×10′ SW, swap canopy 10′×10′ NE, restroom NW."),
        ("•", C_WC[1], "Restroom 12′×10′: Male / Female / Accessible stalls; plumbing and trenching on sheets E-01 / P-01."),
    ]
    col_w = 760
    for i, (n, colr, s) in enumerate(notes):
        cx = 40 + (i // 4) * col_w
        cy = ky + 28 + (i % 4) * 26
        o.append(f'<circle cx="{cx+10}" cy="{cy-4}" r="10" fill="{colr}"/>' + tx(cx + 10, cy, str(n), 11, "middle", "#fff", 800))
        # wrap manually at ~ 84 chars
        w1, w2 = (s, "")
        if len(s) > 120:
            k = s.rfind(" ", 0, 120)
            w1, w2 = s[:k], s[k + 1:]
        o.append(tx(cx + 28, cy, w1, 12, "start", INK, 500))
        if w2:
            o.append(tx(cx + 28, cy + 14, w2, 12, "start", INK, 500))
    # legend row
    o.append(swatch_row(40, 1026, [(C_EV, "EV bays"), (C_DRV, "Driveway"), (C_TR, "Transformer"), (C_CAFE, "Café"),
                                    (C_OFF, "Office"), (C_SWAP, "Swap canopy"), (C_WC, "Restroom"), (C_LAWN, "Lawn")]))
    o.append(titleblock(20, 1048, 1560, 132, "C-01", "MASTER 2D CIVIL SITE LAYOUT & SWEPT-PATH PLAN",
                        "Front zone: 6 DC bays + TSSPDCL yard · 14′ side passage · Rear zone: café, office, swap canopy, restroom · Vastu aligned"))
    o.append("</svg>")
    return page("Sheet C-01 — Master Civil Site Layout (Claude)", "".join(o))


# ============================== BOARD 2 ==============================
def restroom_detail(x, y, w, h):
    """12'x10' 放大平面 (scale 22 px/ft): 1 gridded plumbing layout."""
    s = 28
    ox, oy = x + 80, y + 92
    o = []
    W, H = 12 * s, 10 * s
    o.append(f'<rect x="{ox}" y="{oy}" width="{W}" height="{H}" fill="{C_WC[0]}" stroke="{INK}" stroke-width="3"/>')
    # partitions: male | female | accessible (x: 0-4 male, 4-8 female, 8-12 accessible) ; stall zone y 0-6, wash y 6-10
    for xx in (4, 8):
        o.append(f'<line x1="{ox+xx*s}" y1="{oy}" x2="{ox+xx*s}" y2="{oy+6*s}" stroke="{INK}" stroke-width="2"/>')
    o.append(f'<line x1="{ox}" y1="{oy+6*s}" x2="{ox+W}" y2="{oy+6*s}" stroke="{INK}" stroke-width="2"/>')
    # doors (gaps with swing arcs) on y=6 line
    for xx in (1.2, 5.2, 8.8):
        wd = 2.2 if xx > 8 else 2.0
        o.append(f'<line x1="{ox+xx*s}" y1="{oy+6*s}" x2="{ox+(xx+wd)*s}" y2="{oy+6*s}" stroke="{C_WC[0]}" stroke-width="4"/>')
        o.append(f'<path d="M{ox+xx*s},{oy+6*s} A{wd*s},{wd*s} 0 0 1 {ox+(xx+wd)*s},{oy+(6+0.0)*s+ wd*s*0:.0f}" fill="none" stroke="{C_WC[1]}" stroke-width="1" stroke-dasharray="3 3" opacity="0"/>')
    # main entrance on south wall
    o.append(f'<line x1="{ox+4.5*s}" y1="{oy+H}" x2="{ox+7.5*s}" y2="{oy+H}" stroke="#fff" stroke-width="5"/>')
    o.append(tx(ox + 6 * s, oy + H + 15, "ENTRY 3′ (lawn side)", 11, "middle", INK, 700))
    # fixtures
    def wc(cx, cy):
        return (f'<rect x="{cx-9}" y="{cy-6}" width="18" height="10" fill="#fff" stroke="{INK}" stroke-width="1.4"/>'
                f'<ellipse cx="{cx}" cy="{cy+9}" rx="9" ry="12" fill="#fff" stroke="{INK}" stroke-width="1.4"/>')
    o.append(wc(ox + 2 * s, oy + 1.4 * s))
    o.append(wc(ox + 6 * s, oy + 1.6 * s))
    o.append(wc(ox + 10 * s, oy + 1.6 * s))
    o.append(tx(ox + 2 * s, oy + 4.2 * s, "MALE", 12, "middle", C_WC[1], 800))
    o.append(tx(ox + 2 * s, oy + 4.2 * s + 13, "WC + urinal", 10.5, "middle", INK, 500))
    o.append(tx(ox + 6 * s, oy + 4.2 * s, "FEMALE", 12, "middle", C_WC[1], 800))
    o.append(tx(ox + 6 * s, oy + 4.2 * s + 13, "WC", 10.5, "middle", INK, 500))
    o.append(tx(ox + 10 * s, oy + 4.2 * s, "ACCESSIBLE", 12, "middle", C_WC[1], 800))
    o.append(tx(ox + 10 * s, oy + 4.2 * s + 13, "WC + grab bars", 10.5, "middle", INK, 500))
    # wash basins
    for xx in (2, 5, 8):
        o.append(f'<ellipse cx="{ox+xx*s}" cy="{oy+8.3*s}" rx="14" ry="10" fill="#fff" stroke="{INK}" stroke-width="1.4"/>')
    o.append(tx(ox + 6 * s, oy + 6.9 * s, "WASH BASINS ×3 + FLOOR DRAIN", 10.5, "middle", INK, 600))
    # pipes: Ø150 sewer along north wall outside (y -0.8), Ø50 water along south side
    ys = oy - 16
    o.append(f'<line x1="{ox-14}" y1="{ys}" x2="{ox+W+14}" y2="{ys}" stroke="{C_SEWER}" stroke-width="5"/>')
    for xx in (2, 6, 10):
        o.append(f'<line x1="{ox+xx*s}" y1="{ys}" x2="{ox+xx*s}" y2="{oy+1.6*s}" stroke="{C_SEWER}" stroke-width="2.4"/>')
    o.append(f'<line x1="{ox-14}" y1="{oy+H+34}" x2="{ox+W+14}" y2="{oy+H+34}" stroke="{C_WATER}" stroke-width="3" stroke-dasharray="9 3"/>')
    for xx in (2, 5, 8):
        o.append(f'<line x1="{ox+xx*s}" y1="{oy+H+34}" x2="{ox+xx*s}" y2="{oy+8.3*s+10}" stroke="{C_WATER}" stroke-width="1.6" stroke-dasharray="4 2"/>')
    o.append(tx(ox - 60, ys - 8, "Ø150 SEWER → septic tank (slope 1:60) · Ø100 vent stack", 11, "start", C_SEWER, 800))
    o.append(tx(ox - 60, oy + H + 54, "Ø50 water → Ø20 branches · 1,000 L overhead tank", 11, "start", C_WATER, 800))
    # dims
    o.append(tx(x + w - 12, y + 40, "12′-0″ × 10′-0″", 11, "end", INK, 700, MONO))
    return panel(x, y, w, h, "P-01 · ENLARGED RESTROOM PLUMBING 12′×10′ (NW, VAYU)", "".join(o), C_WC[1])


def trench_section(x, y, w, h):
    o = []
    cx, cy = x + 80, y + 40
    s = 150  # px per m for 0.6 wide => 90
    wpx, hpx = 0.6 * s, 0.9 * s
    gx, gy = cx - 130, cy + 14
    # ground line
    o.append(f'<line x1="{x+10}" y1="{gy}" x2="{x+w-10}" y2="{gy}" stroke="{INK}" stroke-width="2"/>')
    o.append(f'<rect x="{cx-wpx/2}" y="{gy}" width="{wpx}" height="{hpx}" fill="#fbe9e7" stroke="{C_HV}" stroke-width="2.4"/>')
    o.append(f'<rect x="{cx-wpx/2-6}" y="{gy-6}" width="{wpx+12}" height="6" fill="{C_HV}"/>')            # RCC cover
    for i, xx in enumerate((-22, 0, 22)):
        o.append(f'<circle cx="{cx+xx}" cy="{gy+hpx-30}" r="9" fill="#fff" stroke="{INK}" stroke-width="1.6"/><circle cx="{cx+xx}" cy="{gy+hpx-30}" r="4" fill="{C_HV}"/>')
    o.append(f'<rect x="{cx-wpx/2+4}" y="{gy+hpx-12}" width="{wpx-8}" height="8" fill="#d8c8a8" stroke="{INK}" stroke-width="1"/>')
    o.append(f'<line x1="{cx-wpx/2-20}" y1="{gy}" x2="{cx-wpx/2-20}" y2="{gy+hpx}" stroke="{INK}" stroke-width="1"/>')
    o.append(f'<text transform="translate({cx-wpx/2-26},{gy+hpx/2}) rotate(-90)" font-family="{MONO}" font-size="11" text-anchor="middle" font-weight="700" fill="{INK}">900</text>')
    o.append(f'<line x1="{cx-wpx/2}" y1="{gy+hpx+16}" x2="{cx+wpx/2}" y2="{gy+hpx+16}" stroke="{INK}" stroke-width="1"/>')
    o.append(tx(cx, gy + hpx + 32, "600", 11, "middle", INK, 700, MONO))
    lx = x + 150
    for i, s_ in enumerate(["RCC cover slab 75 mm", "3 × 110 mm HDPE duct", "(1 spare)", "Sand bed 100 mm + tape",
                            "M20 RCC walls 100 mm", "Crossings: HDPE sleeve"]):
        o.append(tx(lx, gy + 20 + i * 20, s_, 11, "start", INK, 500))
    return panel(x, y, w, h, "E-01 · TYPICAL 600×900 mm RCC TRENCH", "".join(o), C_HV)


def vastu_matrix(x, y, w, h):
    rows = [("NE", "Ishanya", "Battery swap canopy"), ("NW", "Vayu", "Restroom block"),
            ("SE", "Agni", "Café + lawn"), ("SW", "Nairutya", "Office container"),
            ("Centre", "Brahmasthan", "Open aisle, no structure"), ("W (road)", "Varuna", "Entry + EV bays")]
    o = [f'<rect x="{x}" y="{y+22}" width="{w}" height="22" fill="#efe6fa"/>']
    for i, hdr in enumerate(["ZONE", "DEITY", "PLACED HERE"]):
        o.append(tx(x + [10, 82, 164][i], y + 38, hdr, 11, "start", C_WC[1], 800))
    for i, r in enumerate(rows):
        yy = y + 64 + i * 28
        o.append(f'<line x1="{x}" y1="{yy-18}" x2="{x+w}" y2="{yy-18}" stroke="#d4cde0" stroke-width="1"/>')
        for xx, s, wgt in ((10, r[0], 800), (82, r[1], 500), (164, r[2], 600)):
            o.append(tx(x + xx, yy, s, 12, "start", INK, wgt))
    return panel(x, y, w, h, "VASTU MATRIX (WEST-FACING PLOT)", "".join(o), C_WC[1])


def fee_table(x, y, w, h):
    rows = [("LUMP-SUM FEE", "₹18,000 INR"), ("REVISIONS", "Unlimited"), ("TIMELINE", "48 h — Final GFC set"),
            ("DELIVERABLES", "DXF · PDF · ZIP"), ("SCOPE", "2D only, no 3D / interiors")]
    o = []
    for i, (a, b) in enumerate(rows):
        yy = y + 52 + i * 30
        fill = "#fff8e6" if i < 3 else "#fff"
        o.append(f'<rect x="{x+8}" y="{yy-20}" width="{w-16}" height="28" fill="{fill}" stroke="#e5d9b8" stroke-width="1"/>')
        o.append(tx(x + 16, yy, a, 11.5, "start", "#44506b", 800))
        o.append(tx(x + w - 16, yy, b, 14 if i < 3 else 12, "end", INK, 800))
    return panel(x, y, w, h, "COMMERCIAL PROPOSAL", "".join(o), "#b06a00")


def board2():
    S, OX, OY = 8.6, 125, 150
    p = Plan(OX, OY, S)
    VT, VB = 74, 606
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1200" viewBox="0 0 1600 1200">{DEFS}']
    o.append(f'<rect width="1600" height="1200" fill="{PAPER}"/>')
    o.append(f'<rect x="0" y="0" width="1600" height="64" fill="{INK}"/>')
    o.append(tx(24, 28, "SHEET E-01 & P-01 — UNDERGROUND ELECTRICAL CONDUIT, STORMWATER & PLUMBING BLUEPRINT", 21, "start", "#fff", 800))
    o.append(tx(24, 52, "11kV HT → TSSPDCL TRANSFORMER → LT FEEDER PILLAR → 600×900 mm RCC TRENCH · Ø300 STORM · Ø150 SEWER · Ø50 WATER · VASTU · FEE & TIMELINE", 12.5, "start", "#bcd0f5", 500))
    o.append(tx(1576, 28, "₹18,000 INR · UNLIMITED REV. · 48 h GFC", 13, "end", "#ffd37a", 800))
    o.append(tx(1576, 52, "Contest #2799418", 12, "end", "#bcd0f5", 500))
    o.append(f'<rect x="20" y="{VT}" width="1560" height="{VB-VT}" fill="#fffefa" stroke="{INK}" stroke-width="2.4"/>')
    o.append(road(p, 28, 112, VT + 2, VB - 2))
    o.append(f'<text transform="translate(60,{OY+215}) rotate(-90)" font-family="{SANS}" font-size="14" font-weight="800" text-anchor="middle" fill="{INK}" class="h">100 FT MAIN ROAD</text>')
    # faded base (parking + rear footprints) then utilities
    o.append(layer_base(p))
    # simple faded context
    ctx = []
    ctx.append(p.rect(0, 0, 144, 14, "#fdf1d4", "#e0c88e", 0.8))
    ctx.append(p.text(70, 8.4, "14′ SIDE PASSAGE DRIVEWAY (Ø50 WATER MAIN ALONG SOUTH EDGE)", 11, "middle", "#a8761e", 600))
    for i, xc in enumerate(BAY_XC):
        ctx.append(p.rect(BAY_X0 + 9 * i, 32, 9, 18, "#e1f1ea", "#9ac5b5", 1))
        ctx.append(p.text(xc, 35.3, f"DC-{i+1}", 10.5, "middle", C_EV[1], 700))
    ctx.append(p.text(15, 40, "EXIT", 10.5, "middle", "#6b8c80", 600))
    ctx.append(p.rect(0, 14, 16, 14, "url(#hatchRed)", C_TR[1], 1.8))
    ctx.append(p.rect(5.2, 19.8, 5.6, 4.4, C_TR[1], INK, 1))
    ctx.append(p.lines(8, 17.2, [("TSSPDCL", 800, C_TR[1]), ("TRANSFORMER", 700, C_TR[1])], 10.5, 12))
    ctx.append(p.rect(17, 20, 2, 2, "#2b2b2b", INK, 1))
    ctx.append(p.text(22.6, 20.8, "LT FEEDER PILLAR", 10.5, "start", INK, 800))
    ctx.append(p.rect(91, 14, 12, 10, C_WC[0], C_WC[1], 1.6))
    ctx.append(p.text(97, 19.4, "WC", 11, "middle", C_WC[1], 800))
    ctx.append(p.rect(105, 14, 28, 24, "url(#dotsLawn)", C_LAWN[1], 1))
    ctx.append(p.text(119, 20.8, "LAWN 28′×24′", 10.5, "middle", C_LAWN[1], 700))
    ctx.append(p.rect(124, 40, 20, 10, C_CAFE[0], C_CAFE[1], 1.6))
    ctx.append(p.text(134, 46, "CAFÉ", 11.5, "middle", C_CAFE[1], 800))
    ctx.append(p.rect(91, 40, 20, 10, C_OFF[0], C_OFF[1], 1.6))
    ctx.append(p.text(101, 46, "OFFICE", 11.5, "middle", C_OFF[1], 800))
    ctx.append(p.rect(134, 14, 10, 10, C_SWAP[0], C_SWAP[1], 1.6))
    ctx.append(p.text(139, 19, "SWAP", 10.5, "middle", C_SWAP[1], 800))
    ctx.append(p.text(139, 20.8, "", 10))
    ctx.append(p.rect(91, 32.5, 8, 5, "#eee6dc", C_SEWER, 1.2))
    ctx.append(p.text(95, 35.6, "SEPTIC", 10.5, "middle", C_SEWER, 700))
    o.append(g("context", "".join(ctx), "Context"))
    o.append(layer_drain(p))
    o.append(layer_hv(p))
    # dims
    o.append(p.dim_h(0, 144, 128, "OVERALL 144′-0″ · FALL OF Ø300 STORM DRAIN TOWARD ROAD (WEST)", 12, INK))
    o.append(p.dim_v(0, 50, 1370, "50′-0″", 12, INK, -6))
    # legend (right gutter)
    lx, ly = 1386, 86
    leg = [(C_HV, "11kV HT / LT RCC trench 600×900"), (C_STORM, "Ø300 storm drain + MH"),
           (C_SEWER, "Ø150 sewer → septic"), (C_WATER, "Ø50 water main")]
    o.append(f'<rect x="{lx-8}" y="{ly-6}" width="204" height="{VB-VT-12}" fill="#fff" stroke="{INK}" stroke-width="1.2"/>')
    o.append(tx(lx, ly + 12, "LEGEND — UTILITIES", 12, "start", INK, 800))
    for i, (c, s) in enumerate(leg):
        yy = ly + 44 + i * 50
        dash = ' stroke-dasharray="11 4"' if c in (C_HV, C_WATER) else ""
        o.append(f'<line x1="{lx}" y1="{yy-4}" x2="{lx+34}" y2="{yy-4}" stroke="{c}" stroke-width="4"{dash}/>')
        words = s.split(" ")
        l1 = " ".join(words[: len(words) // 2 + 1])
        l2 = " ".join(words[len(words) // 2 + 1:])
        o.append(tx(lx + 42, yy - 2, l1, 11, "start", INK, 600))
        if l2:
            o.append(tx(lx + 42, yy + 12, l2, 11, "start", INK, 600))
    o.append(f'<rect x="{lx+4}" y="{ly+232}" width="14" height="14" fill="#fff" stroke="{C_HV}" stroke-width="1.8"/>')
    o.append(tx(lx + 42, ly + 243, "Handhole 1.8′ sq", 11, "start", INK, 600))
    o.append(f'<circle cx="{lx+11}" cy="{ly+270}" r="7" fill="#fff" stroke="{C_STORM}" stroke-width="2.2"/>')
    o.append(tx(lx + 42, ly + 274, "Storm manhole", 11, "start", INK, 600))
    o.append(f'<circle cx="{lx+11}" cy="{ly+298}" r="9.5" fill="{C_HV}"/><text x="{lx+11}" y="{ly+302}" font-family="{SANS}" font-size="11" font-weight="800" text-anchor="middle" fill="#fff">4</text>')
    o.append(tx(lx + 42, ly + 302, "LT pillar / hand hole", 11, "start", INK, 600))
    o.append(tx(lx, ly + 346, "TRENCH LOAD", 11, "start", C_HV, 800))
    o.append(tx(lx, ly + 362, "Design: IRC Class AA", 10.5, "start", INK, 500))
    o.append(tx(lx, ly + 376, "wheel load, 600 mm cover", 10.5, "start", INK, 500))
    o.append(tx(lx, ly + 390, "Crossings: HDPE sleeve", 10.5, "start", INK, 500))
    o.append(north_arrow(1480, ly + 450, 20))
    # bottom panels
    by, bh = 622, 452
    o.append(restroom_detail(20, by, 500, bh))
    o.append(trench_section(534, by, 330, 250))
    o.append(panel(534, by + 262, 330, 190, "UTILITY SCHEDULE", "".join([
        tx(544, by + 262 + 44, "LT feed: 4 × 3.5C×240 mm² Al XLPE → pillar", 11, "start", INK, 500),
        tx(544, by + 262 + 62, "Chargers: 6 × 150 kW dual-gun CCS2 (spur 1.5′)", 11, "start", INK, 500),
        tx(544, by + 262 + 80, "Office + café: 1 × 4C×25 mm² each, 63 A MCB", 11, "start", INK, 500),
        tx(544, by + 262 + 98, "Swap canopy: 1 × 4C×95 mm², 100 A MCCB", 11, "start", INK, 500),
        tx(544, by + 262 + 116, "Storm: Ø300 UPVC/RCC, MH every 30′, 1:150 fall", 11, "start", INK, 500),
        tx(544, by + 262 + 134, "Sewer Ø150 to 8′×5′ septic; Ø50 water to WC/café", 11, "start", INK, 500),
        tx(544, by + 262 + 152, "Spare: 2 × 110 mm HDPE duct, pull-pits every 30′", 11, "start", INK, 500),
    ]), INK))
    o.append(vastu_matrix(878, by, 360, 270))
    o.append(fee_table(1252, by, 328, 270))
    # note panel
    nl = ["Transformer (16′×14′) sits NW, south of the 14′ driveway, so the passage stays unblocked end to end.",
          "Trenches run along the aisle and rear edges; every crossing of the Ø300 storm drain is sleeved.",
          "Routing is conceptual working-drawing level for ground civil execution; cable sizing by the licensed electrical contractor.",
          "Out of scope: 3D renders, interior design, structural container engineering (per brief)."]
    nbody = "".join(tx(890, by + 282 + 48 + i * 28, t, 12, "start", INK, 500) for i, t in enumerate(nl))
    o.append(panel(878, by + 282, 702, 170, "DESIGN NOTES", nbody, INK))
    o.append(titleblock(20, 1084, 1560, 110, "E-01 / P-01", "UNDERGROUND ELECTRICAL, STORMWATER & PLUMBING BLUEPRINT",
                        "Trench routing to 6 DC chargers, battery swap, rear containers · restroom plumbing · Vastu matrix · fee & timeline"))
    o.append("</svg>")
    return page("Sheet E-01 / P-01 — Utility Blueprint (Claude)", "".join(o))


# ============================== INDEX ==============================
def index_html():
    S, OX, OY = 11.2, 90, 40
    p = Plan(OX, OY, S)
    W, H = int(OX + 144 * S + 70), int(OY + 50 * S + 60)
    svg = [f'<svg id="plan" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{DEFS}']
    svg.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
    svg.append(f'<rect x="0" y="{OY-10}" width="{OX-6}" height="{50*S+20:.0f}" fill="url(#roadHatch)" stroke="{INK}"/>')
    svg.append(layer_base(p))
    svg.append(layer_driveway(p))
    svg.append(layer_evbays(p))
    svg.append(layer_tssp(p))
    svg.append(layer_rear(p))
    svg.append(layer_swept(p))
    svg.append(layer_drain(p))
    svg.append(layer_hv(p))
    svg.append(layer_vastu(p))
    svg.append(p.dim_h(0, 144, int(OY - 18), "144′-0″", 12))
    svg.append(p.dim_v(0, 50, int(OX + 144 * S + 28), "50′-0″", 12, INK, -6))
    svg.append("</svg>")
    layers = [("evbays", "EV Bays"), ("swept", "Swept-Path Arcs"), ("tsspdcl", "TSSPDCL Yard"), ("driveway", "14ft Driveway"),
              ("rear", "Rear Containers"), ("hv", "HV Electrical Trench"), ("drain", "Drainage & Plumbing"), ("vastu", "Vastu Grid")]
    presets = {
        "C-01": ["evbays", "swept", "tsspdcl", "driveway", "rear", "vastu"],
        "E-01": ["tsspdcl", "evbays", "rear", "hv"],
        "P-01": ["rear", "drain", "driveway"],
    }
    info = {
        "C-01": "Master civil site layout: 6 DC bays (9′×18′), swept-path R=24′/R=14′, TSSPDCL yard 16′×14′, 14′ side passage, rear containers.",
        "E-01": "Electrical: 11kV HT → TSSPDCL transformer → LT feeder pillar → 600×900 RCC trench to 6 chargers, swap canopy, office and café.",
        "P-01": "Plumbing & drainage: Ø300 storm drain falling west, Ø150 sewer from restroom to septic, Ø50 water main; see enlarged restroom on board 2.",
    }
    tmpl = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Khanapur EV Hub — CAD Layer & Trenching Inspector</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:{SANS};background:#eef0f5;color:{INK}}}
header{{background:{INK};color:#fff;padding:14px 22px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
header h1{{font-size:18px;margin:0}}header p{{margin:2px 0 0;font-size:12px;color:#bcd0f5}}
.fee{{font-size:13px;color:#ffd37a;font-weight:700}}
main{{display:grid;grid-template-columns:260px 1fr;gap:16px;padding:16px;max-width:1700px;margin:auto}}
aside{{background:#fff;border:1px solid #cfd5e3;border-radius:6px;padding:14px;align-self:start}}
aside h2{{font-size:12px;letter-spacing:.6px;text-transform:uppercase;margin:0 0 8px;color:#44506b}}
.sheets{{display:flex;gap:6px;margin-bottom:14px}}
.sheets button{{flex:1;padding:8px 0;border:1.5px solid {INK};background:#fff;font-weight:800;cursor:pointer;border-radius:4px}}
.sheets button.on{{background:{INK};color:#fff}}
label.ly{{display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid #eceff5;font-size:13px;cursor:pointer}}
label.ly input{{width:16px;height:16px}}
.dl a{{display:block;margin:6px 0;padding:9px 10px;background:#b06a00;color:#fff;border-radius:4px;text-decoration:none;font-size:13px;font-weight:700}}
.dl a.alt{{background:{INK}}}
#sheetinfo{{font-size:12.5px;line-height:1.45;color:#2d3a55;background:#f4f6fb;padding:10px;border-radius:4px;margin-bottom:14px}}
#hover{{font-size:12px;margin-top:12px;min-height:34px;color:#44506b}}
.stage{{background:#fff;border:1px solid #cfd5e3;border-radius:6px;overflow:auto;padding:8px}}
.stage svg{{max-width:100%;height:auto}}
.tbl{{margin-top:14px;font-size:12.5px;border-collapse:collapse;width:100%}}
.tbl td{{border-bottom:1px solid #eceff5;padding:5px 2px}}.tbl td:last-child{{text-align:right;font-weight:800}}
{CSS}
.layer{{cursor:pointer}}
</style></head><body>
<header><div><h1>Khanapur EV Hub &amp; Café — 2D AutoCAD Layer &amp; Trenching Inspector</h1>
<p>800 Sq. Yds · 50′ × 144′ west-facing Vastu site · Contest #2799418</p></div>
<div class="fee">₹18,000 INR · Unlimited revisions · 48 h final GFC set</div></header>
<main><aside>
<h2>Sheet</h2><div class="sheets"><button data-s="C-01" class="on">C-01</button><button data-s="E-01">E-01</button><button data-s="P-01">P-01</button></div>
<div id="sheetinfo"></div>
<h2>CAD layers</h2>
{"".join(f'<label class="ly"><input type="checkbox" data-l="{k}" checked> {v}</label>' for k, v in layers)}
<div id="hover">Hover a layer in the drawing to identify it.</div>
<h2 style="margin-top:16px">Download</h2>
<div class="dl"><a href="exports/Khanapur_EV_Hub_CAD_Package.zip" download>⬇ CAD package (.zip)</a>
<a class="alt" href="exports/Khanapur_EV_Hub_800sqyd_Master.dxf" download>⬇ Master AutoCAD (.dxf)</a>
<a class="alt" href="exports/Khanapur_EV_Hub_Civil_and_Trenching_Set.pdf" download>⬇ Civil &amp; trenching set (.pdf)</a></div>
<table class="tbl"><tr><td>Lump-sum fee</td><td>₹18,000 INR</td></tr><tr><td>Revisions</td><td>Unlimited</td></tr><tr><td>Timeline</td><td>48 h final GFC</td></tr></table>
</aside>
<section class="stage">{"".join(svg)}</section></main>
<script>
const PRESETS={json.dumps(presets)},INFO={json.dumps(info)};
const boxes=[...document.querySelectorAll('input[data-l]')];
function apply(){{boxes.forEach(b=>document.querySelectorAll('[data-layer="'+b.dataset.l+'"]').forEach(g=>g.classList.toggle('off',!b.checked)));}}
function sheet(s){{document.querySelectorAll('.sheets button').forEach(b=>b.classList.toggle('on',b.dataset.s===s));
boxes.forEach(b=>b.checked=PRESETS[s].includes(b.dataset.l));document.getElementById('sheetinfo').textContent=INFO[s];apply();}}
boxes.forEach(b=>b.addEventListener('change',apply));
document.querySelectorAll('.sheets button').forEach(b=>b.addEventListener('click',()=>sheet(b.dataset.s)));
document.querySelectorAll('.layer').forEach(g=>{{g.addEventListener('mouseenter',()=>{{document.getElementById('hover').textContent='Layer: '+(g.dataset.label||g.dataset.layer);}});}});
sheet('C-01');
</script></body></html>'''
    return tmpl


def main():
    (OUT / "board1-claude.html").write_text(board1(), encoding="utf-8")
    (OUT / "board2-claude.html").write_text(board2(), encoding="utf-8")
    (OUT / "index.html").write_text(index_html(), encoding="utf-8")
    print("wrote board1-claude.html board2-claude.html index.html")


if __name__ == "__main__":
    main()
