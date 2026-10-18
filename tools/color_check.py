"""Check the KemoMichi palette for contrast and colour-vision differences.

For every pair listed in PAIRS it prints:
- the WCAG 2 contrast ratio,
- the CIEDE2000 colour difference for typical vision and for simulated
  protanopia, deuteranopia and tritanopia (Machado, Oliveira & Fernandes 2009,
  severity 1.0, applied in linear RGB).

Rough reading: contrast 4.5 for text (3.0 for large text, lines and icons);
ΔE under 10 is hard to tell apart, 20 or more is easy.

Usage:
    python tools/color_check.py
Edit PALETTE and PAIRS in docs/design-system.md and here together.
"""

from __future__ import annotations

import math

# Values from the Digital Agency design tokens (@digital-go-jp/design-tokens
# 2.0.1, MIT) except the accent, which is KemoMichi's own.
PALETTE = {
    "primary": "#0066BE",         # light-blue-800 (plan A)
    "primary_strong": "#00428C",  # light-blue-1000
    "primary_b": "#0031D8",       # blue-800 (plan B)
    "surface": "#E8F1FE",         # blue-50
    "accent": "#F08A00",
    "text": "#1A1A1A",            # solid-gray-900
    "text_sub": "#4D4D4D",        # solid-gray-700
    "border": "#767676",          # solid-gray-536
    "divider": "#CCCCCC",         # solid-gray-200
    "white": "#FFFFFF",
    "focus": "#FFD43D",           # yellow-300
    "error": "#CE0000",           # error-2
    "warning": "#927200",         # warning-yellow-2
    "success": "#197A4B",         # success-2
    "viewer": "#333333",          # solid-gray-800
}

PAIRS = [
    ("white", "primary"), ("primary", "surface"), ("primary_strong", "white"),
    ("text", "white"), ("text", "surface"), ("text_sub", "white"), ("text_sub", "surface"),
    ("border", "white"), ("text", "accent"), ("accent", "primary"), ("accent", "white"),
    ("surface", "white"), ("accent", "focus"), ("accent", "error"), ("accent", "warning"),
    ("error", "white"), ("warning", "white"), ("warning", "surface"), ("success", "white"),
    ("accent", "viewer"), ("white", "viewer"), ("white", "primary_b"), ("accent", "primary_b"),
    ("primary_b", "surface"),
]

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}


def to_linear(hex_color: str) -> tuple[float, float, float]:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)


def luminance(lin: tuple[float, float, float]) -> float:
    r, g, b = lin
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(to_linear(a)), luminance(to_linear(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def simulate(lin, matrix):
    return tuple(min(1.0, max(0.0, sum(m * c for m, c in zip(row, lin)))) for row in matrix)


def to_lab(lin):
    r, g, b = lin
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(lab1, lab2) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dlp, dcp = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dhp_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    lp_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    else:
        hp_bar = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hp_bar - 30)) + 0.24 * math.cos(math.radians(2 * hp_bar))
         + 0.32 * math.cos(math.radians(3 * hp_bar + 6)) - 0.20 * math.cos(math.radians(4 * hp_bar - 63)))
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cp_bar ** 7 / (cp_bar ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lp_bar - 50) ** 2 / math.sqrt(20 + (lp_bar - 50) ** 2)
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhp_big / sh) ** 2
                     + rt * (dcp / sc) * (dhp_big / sh))


def delta_e(a: str, b: str, kind: str | None) -> float:
    la, lb = to_linear(a), to_linear(b)
    if kind:
        la, lb = simulate(la, MACHADO[kind]), simulate(lb, MACHADO[kind])
    return ciede2000(to_lab(la), to_lab(lb))


def main() -> None:
    print(f"{'foreground':>15} / {'background':<15} contrast  ΔE:normal protan deutan tritan")
    for fg, bg in PAIRS:
        a, b = PALETTE[fg], PALETTE[bg]
        diffs = [delta_e(a, b, k) for k in (None, "protan", "deutan", "tritan")]
        print(f"{fg:>15} / {bg:<15} {contrast(a, b):7.2f}   "
              + "  ".join(f"{d:6.1f}" for d in diffs))


if __name__ == "__main__":
    main()
