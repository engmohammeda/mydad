#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
محرّك تركيب الصور — haraj-riyadh-2026

الطريقة المعتمدة: يُولَّد المشهد بلا نص، ثم يُرسم النص العربي والعلامة المائية فوقه
بخط Almarai حقيقي، داخل ملف الصورة النهائي. لا طبقات منفصلة.

الاستخدام:
    python3 tools/render.py --list
    python3 tools/render.py --all
    python3 tools/render.py winter-01-majlis cover-haraj
    python3 tools/render.py --sheet            # بناء contact-sheet.png
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tools" / "image-spec.json").read_text(encoding="utf-8"))
META = SPEC["meta"]
IDENTITY = META["identity"]
NUMBER = META["number"]
BADGE = META["badge"]

CHARCOAL = (28, 25, 23)
BRICK = (140, 58, 47)
BRICK_LIGHT = (163, 75, 50)
SAND = (231, 215, 193)
CREAM = (243, 237, 224)
EMBER = (196, 161, 90)
NIGHT = (26, 35, 50)

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


# ------------------------------------------------------------------ أدوات
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(ROOT / META["fonts"][weight]), size)
    return _FONT_CACHE[key]


def _isolated_fallback_map() -> dict[int, int]:
    """خطوط جوجل تحوي الأشكال السياقية (نهائي/أولي/وسطي) لكن قد تخلو من
    الأشكال المنفصلة؛ الحرف الأساسي في الخط يحمل شكله المنفصل، فنستبدل به."""
    try:
        from fontTools.ttLib import TTFont
        path = ROOT / META["fonts"]["bold"]
        cmap = set(TTFont(str(path)).getBestCmap())
    except Exception:
        cmap = set()
    table: dict[int, int] = {}
    letters = {
        0x0621: [0xFE80], 0x0622: [0xFE81, 0xFE82], 0x0623: [0xFE83, 0xFE84],
        0x0624: [0xFE85, 0xFE86], 0x0625: [0xFE87, 0xFE88],
        0x0626: [0xFE89, 0xFE8A, 0xFE8B, 0xFE8C], 0x0627: [0xFE8D, 0xFE8E],
        0x0628: [0xFE8F, 0xFE90, 0xFE91, 0xFE92], 0x0629: [0xFE93, 0xFE94],
        0x062A: [0xFE95, 0xFE96, 0xFE97, 0xFE98], 0x062B: [0xFE99, 0xFE9A, 0xFE9B, 0xFE9C],
        0x062C: [0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0], 0x062D: [0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4],
        0x062E: [0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8], 0x062F: [0xFEA9, 0xFEAA],
        0x0630: [0xFEAB, 0xFEAC], 0x0631: [0xFEAD, 0xFEAE], 0x0632: [0xFEAF, 0xFEB0],
        0x0633: [0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4], 0x0634: [0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8],
        0x0635: [0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC], 0x0636: [0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0],
        0x0637: [0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4], 0x0638: [0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8],
        0x0639: [0xFEC9, 0xFECA, 0xFECB, 0xFECC], 0x063A: [0xFECD, 0xFECE, 0xFECF, 0xFED0],
        0x0641: [0xFED1, 0xFED2, 0xFED3, 0xFED4], 0x0642: [0xFED5, 0xFED6, 0xFED7, 0xFED8],
        0x0643: [0xFED9, 0xFEDA, 0xFEDB, 0xFEDC], 0x0644: [0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0],
        0x0645: [0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4], 0x0646: [0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8],
        0x0647: [0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC], 0x0648: [0xFEED, 0xFEEE],
        0x0649: [0xFEEF, 0xFEF0], 0x064A: [0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4],
    }
    for basic, forms in letters.items():
        for cp in forms:
            if cmap and cp not in cmap:
                table[cp] = basic
            elif not cmap:
                pass
    return table


_FALLBACK = _isolated_fallback_map()


def fit_font(text: str, weight: str, start: int, max_w: int) -> ImageFont.FreeTypeFont:
    """أكبر مقاس لا يتجاوز max_w."""
    size = start
    f = font(weight, size)
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    while size > 20 and text_w(d, ar(text), f) > max_w:
        size -= 4
        f = font(weight, size)
    return f


def ar(text: str) -> str:
    """يشكّل النص العربي ويضبط اتجاهه. الأرقام اللاتينية تبقى كما هي.
    أي شكل عرضي غير موجود في الخط يُستبدل بحرفه الأساسي (شكله المنفصل)."""
    if re.fullmatch(r"[\d\s+\-–—.,:/•]+", text or ""):
        return text
    shaped = arabic_reshaper.reshape(text)
    if _FALLBACK:
        shaped = "".join(chr(_FALLBACK[ord(c)]) if ord(c) in _FALLBACK else c for c in shaped)
    return get_display(shaped)


def fit_cover(im: Image.Image, w: int, h: int) -> Image.Image:
    """قص مركزي إلى النسبة ثم تحجيم LANCZOS — بلا تمدد."""
    im = im.convert("RGB")
    sw, sh = im.size
    target = w / h
    src = sw / sh
    if src > target:                       # المصدر أعرض → نقص من الجانبين
        nw = int(sh * target)
        left = (sw - nw) // 2
        im = im.crop((left, 0, left + nw, sh))
    elif src < target:                     # المصدر أطول → نقص من الأعلى والأسفل
        nh = int(sw / target)
        top = (sh - nh) // 2
        im = im.crop((0, top, sw, top + nh))
    return im.resize((w, h), Image.LANCZOS)


def load_scene(rel: str, w: int, h: int) -> Image.Image:
    p = ROOT / rel
    if not p.exists():                      # جرّب امتدادات أخرى للمشهد
        for ext in (".png", ".jpg", ".jpeg"):
            alt = p.with_suffix(ext)
            if alt.exists():
                p = alt
                break
    if not p.exists():
        raise FileNotFoundError(f"المشهد غير موجود: {rel}")
    return fit_cover(Image.open(p), w, h)


def v_gradient(w: int, h: int, top: int, bottom: int) -> Image.Image:
    """طبقة تدرّج رأسي: شفافة أعلى → (bottom) أسفل."""
    g = Image.new("L", (1, h), 0)
    px = g.load()
    for y in range(h):
        t = max(0.0, min(1.0, (y - top) / max(1, (h - top))))
        t = t ** 1.35
        px[0, y] = int(top_a(bottom, t))
    return g.resize((w, h))


def top_a(bottom: int, t: float) -> float:
    return bottom * t


def darken_bottom(im: Image.Image, strength: int = 205, start: float = 0.42) -> Image.Image:
    w, h = im.size
    mask = v_gradient(w, h, int(h * start), strength)
    layer = Image.new("RGB", (w, h), CHARCOAL)
    return Image.composite(layer, im, mask)


def darken_top(im: Image.Image, strength: int = 130, end: float = 0.3) -> Image.Image:
    w, h = im.size
    g = Image.new("L", (1, h), 0)
    px = g.load()
    for y in range(h):
        t = 1.0 - max(0.0, min(1.0, y / max(1, h * end)))
        px[0, y] = int(strength * (t ** 1.2))
    mask = g.resize((w, h))
    layer = Image.new("RGB", (w, h), CHARCOAL)
    return Image.composite(layer, im, mask)


def h_gradient_right(w: int, h: int, strength: int, frac: float) -> Image.Image:
    """تدرّج أفقي: داكن عند الحافة اليمنى → شفاف عند frac من الاتساع."""
    g = Image.new("L", (w, 1), 0)
    px = g.load()
    edge = int(w * (1 - frac))
    for x in range(w):
        if x <= edge:
            px[x, 0] = 0
        else:
            t = (x - edge) / max(1, (w - edge))
            px[x, 0] = int(strength * (t ** 1.15))
    return g.resize((w, h))


def text_w(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=f))


def put_text(im: Image.Image, xy, text: str, f: ImageFont.FreeTypeFont,
             fill=CREAM, anchor="rm", shadow: int = 0, shadow_alpha: int = 165,
             tracking: int = 0):
    """يرسم نصاً مع ظل ناعم اختيارياً. xy = (x, y)."""
    shaped = ar(text)
    if tracking:
        shaped = (" " * tracking).join(list(shaped)) if False else shaped
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shadow:
        sx, sy = xy[0] + shadow, xy[1] + shadow
        d.text((sx, sy), shaped, font=f, fill=(0, 0, 0, shadow_alpha), anchor=anchor)
        layer = layer.filter(ImageFilter.GaussianBlur(shadow * 0.9))
        d = ImageDraw.Draw(layer)
    d.text(xy, shaped, font=f, fill=fill + (255,) if len(fill) == 3 else fill, anchor=anchor)
    im.alpha_composite(layer)
    return im


def rule(im: Image.Image, x_right: int, y: int, width: int, color=EMBER, thickness: int = 6):
    d = ImageDraw.Draw(im)
    d.rectangle([x_right - width, y, x_right, y + thickness], fill=color + (255,))
    return im


# ------------------------------------------------------------ العلامة المائية
def watermark_strip(im: Image.Image, ratio: float = 0.115, min_h: int = 84,
                    stacked: bool | None = None) -> Image.Image:
    """شريط سفلي مقروء: الهوية + الرقم، بتباين عالٍ، داخل هامش 4%."""
    w, h = im.size
    bar_h = max(min_h, int(h * ratio))
    inset = max(40, int(w * 0.04))                      # هامش أمان 4% على الأقل

    strip = Image.new("RGBA", (w, bar_h), CHARCOAL + (238,))
    im.alpha_composite(strip, (0, h - bar_h))

    d = ImageDraw.Draw(im)
    d.rectangle([0, h - bar_h, w, h - bar_h + 4], fill=EMBER + (255,))   # خط جمر

    d0 = ImageDraw.Draw(im)
    if stacked is None:
        stacked = bar_h >= 118
    s_id = 0.30 if stacked else 0.40
    s_num = 0.38 if stacked else 0.46
    f_id = font("bold", int(bar_h * s_id))
    f_num = font("extrabold", int(bar_h * s_num))

    # حماية من التراكب في السطر الواحد: إن لم يتّسع، صغّر الخطوط
    if not stacked:
        need = (text_w(d0, ar(IDENTITY), f_id) + text_w(d0, ar(NUMBER), f_num)
                + 2 * inset + int(w * 0.05))
        if need > w:
            k = (w - 2 * inset - int(w * 0.05)) / max(1, need - 2 * inset - int(w * 0.05))
            f_id = font("bold", max(18, int(bar_h * s_id * k)))
            f_num = font("extrabold", max(20, int(bar_h * s_num * k)))

    y0 = h - bar_h
    if stacked:
        put_text(im, (w - inset, y0 + bar_h * 0.33), IDENTITY, f_id, fill=SAND, anchor="rm")
        put_text(im, (w - inset, y0 + bar_h * 0.74), NUMBER, f_num, fill=CREAM, anchor="rm")
    else:
        cy = y0 + bar_h * 0.52
        put_text(im, (w - inset, cy), IDENTITY, f_id, fill=SAND, anchor="rm")
        put_text(im, (inset, cy), NUMBER, f_num, fill=CREAM, anchor="lm")
    return im


def diagonal_repeat(im: Image.Image, opacity: float = 0.16, angle: float = -28) -> Image.Image:
    """تكرار قطري خفيف في الوسط حتى لا تُسرق الصورة بقص الزاوية."""
    w, h = im.size
    size = int(math.hypot(w, h))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font("bold", max(20, int(w * 0.026)))
    line = f"{IDENTITY}      {NUMBER}"
    step_y = int(f.size * 4.2)
    step_x = text_w(d, ar(line), f) + int(f.size * 3.0)
    y = 0
    row = 0
    while y < size:
        x = -step_x if row % 2 else 0
        while x < size:
            d.text((x, y), ar(line), font=f, fill=CREAM + (255,))
            x += step_x
        y += step_y
        row += 1
    a = layer.getchannel("A").point(lambda p: int(p * opacity))
    layer.putalpha(a)
    layer = layer.rotate(angle, resample=Image.BICUBIC, expand=False)
    left = (size - w) // 2
    top = (size - h) // 2
    layer = layer.crop((left, top, left + w, top + h))
    im.alpha_composite(layer)
    return im


def chip(im: Image.Image, text: str, x_right: int, y: int, size: int | None = None) -> Image.Image:
    w, _ = im.size
    size = size or max(24, int(w * 0.026))
    f = font("bold", size)
    pad_x, pad_y = int(size * 0.9), int(size * 0.55)
    tw = text_w(ImageDraw.Draw(im), ar(text), f)
    box = [x_right - tw - pad_x * 2, y, x_right, y + size + pad_y * 2]
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, radius=int(size * 0.55), fill=CHARCOAL + (215,))
    d.rounded_rectangle(box, radius=int(size * 0.55), outline=EMBER + (255,), width=2)
    put_text(im, (x_right - pad_x, box[1] + (box[3] - box[1]) / 2), text, f, fill=CREAM, anchor="rm")
    return im


# ---------------------------------------------------------------- التخطيطات
def base_canvas(name: str, spec: dict) -> Image.Image:
    w, h = spec["size"]
    return load_scene(spec["scene"], w, h).convert("RGBA")


def layout_post(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = base_canvas(None, spec)
    im = darken_bottom(im, 220, 0.34)
    im = darken_top(im, 120, 0.22)
    inset = max(48, int(w * 0.045))
    chip(im, BADGE, w - inset, int(h * 0.05))

    bar_h = max(84, int(h * 0.115))
    hero = spec["lines"][0]
    sub = spec["lines"][1] if len(spec["lines"]) > 1 else None
    f_hero = font("extrabold", int(w * 0.072))
    f_sub = font("bold", int(w * 0.043))

    y_sub = h - bar_h - int(h * 0.055)
    y_hero = y_sub - int(h * 0.075) if sub else y_sub
    rule(im, w - inset, int(y_hero - h * 0.035), int(w * 0.16), EMBER, int(w * 0.008))
    put_text(im, (w - inset, y_hero), hero, f_hero, fill=CREAM, anchor="rm", shadow=6)
    if sub:
        put_text(im, (w - inset, y_sub), sub, f_sub, fill=SAND, anchor="rm", shadow=4)

    diagonal_repeat(im, 0.15)
    watermark_strip(im)
    return im


def layout_story(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = base_canvas(None, spec)
    if spec.get("blur"):
        im = im.filter(ImageFilter.GaussianBlur(spec["blur"]))
    im = darken_top(im, 190, 0.30)
    im = darken_bottom(im, 230, 0.55)
    inset = max(56, int(w * 0.06))

    hero = spec["lines"][0]
    ident = spec["lines"][1] if len(spec["lines"]) > 1 else IDENTITY
    f_hero = fit_font(hero, "extrabold", int(w * 0.085), w - 2 * inset)
    f_id = font("bold", int(w * 0.038))
    f_num = font("extrabold", int(w * 0.155))

    put_text(im, (w - inset, h * 0.13), hero, f_hero, fill=CREAM, anchor="rm", shadow=8)
    rule(im, w - inset, int(h * 0.175), int(w * 0.22), EMBER, int(w * 0.009))

    put_text(im, (w / 2, h * 0.735), ident, f_id, fill=SAND, anchor="mm", shadow=4)
    put_text(im, (w / 2, h * 0.80), NUMBER, f_num, fill=CREAM, anchor="mm", shadow=8)

    diagonal_repeat(im, 0.15)
    watermark_strip(im, ratio=0.075, min_h=110)
    return im


def layout_profile(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = base_canvas(None, spec)
    im = darken_bottom(im, 210, 0.30)
    im = darken_top(im, 120, 0.28)

    # لوحة نصية وسطى
    panel_h, panel_w = int(h * 0.30), int(w * 0.86)
    px0, py0 = (w - panel_w) // 2, int(h * 0.34)
    panel = Image.new("RGBA", (panel_w, panel_h), CHARCOAL + (150,))
    im.alpha_composite(panel, (px0, py0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([px0, py0, px0 + panel_w, py0 + panel_h], radius=24,
                        outline=EMBER + (220,), width=3)

    f1 = font("extrabold", int(w * 0.095))
    f2 = font("bold", int(w * 0.048))
    put_text(im, (w / 2, py0 + panel_h * 0.38), spec["lines"][0], f1, fill=CREAM, anchor="mm")
    put_text(im, (w / 2, py0 + panel_h * 0.72), spec["lines"][1], f2, fill=EMBER, anchor="mm")

    diagonal_repeat(im, 0.15)
    watermark_strip(im, ratio=0.13, min_h=110)
    return im


def layout_cover(spec: dict) -> Image.Image:
    w, h = spec["size"]                      # 1500×500 بالضبط
    half = w // 2
    left = load_scene(spec["scenes"][0], half, h)
    right = load_scene(spec["scenes"][1], w - half, h)
    im = Image.new("RGBA", (w, h))
    im.paste(left, (0, 0))
    im.paste(right, (half, 0))

    # لحمة بين المشهدين
    seam = Image.new("RGBA", (160, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seam)
    for x in range(160):
        a = int(120 * (1 - abs(x - 80) / 80))
        sd.line([(x, 0), (x, h)], fill=CHARCOAL + (a,))
    im.alpha_composite(seam, (half - 80, 0))

    # تهدئة الثلث الأيمن ليُقرأ النص
    im.alpha_composite(Image.new("RGBA", (w, h), (0, 0, 0, 0)))
    mask = h_gradient_right(w, h, 215, 0.46)
    dark = Image.new("RGBA", (w, h), CHARCOAL + (255,))
    dark.putalpha(mask)
    im.alpha_composite(dark)
    im = darken_bottom(im, 150, 0.55)

    margin = 60                              # ≥ 48 بكسل من الحافة
    f1 = font("bold", 30)
    f2 = font("extrabold", 56)
    f3 = font("extrabold", 46)
    bar_h = max(84, int(h * 0.17))

    y3 = h - bar_h - 34
    put_text(im, (w - margin, y3 - 132), spec["lines"][0], f1, fill=SAND, anchor="rm", shadow=3)
    put_text(im, (w - margin, y3 - 72), spec["lines"][1], f2, fill=CREAM, anchor="rm", shadow=5)
    put_text(im, (w - margin, y3 - 6), spec["lines"][2], f3, fill=EMBER, anchor="rm", shadow=4)
    rule(im, w - margin, int(y3 - 168), 190, EMBER, 5)

    diagonal_repeat(im, 0.14)
    watermark_strip(im, ratio=bar_h / h, min_h=bar_h, stacked=False)
    return im


def layout_card(spec: dict) -> Image.Image:
    w, h = spec["size"]                      # 1050×650
    im = Image.new("RGBA", (w, h), CREAM + (255,))

    # شريط طوب على الحافة اليمنى
    tex = load_scene(spec["scene"], 300, h)
    tex = Image.eval(tex.convert("RGB"), lambda p: int(p * 0.92)).convert("RGBA")
    im.alpha_composite(tex, (w - 300, 0))
    fade = Image.new("L", (300, h), 0)
    fd = ImageDraw.Draw(fade)
    for x in range(300):
        fd.line([(x, 0), (x, h)], fill=int(255 * (x / 300) ** 0.7))
    tex.putalpha(fade)
    im.alpha_composite(tex, (w - 300, 0))

    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=BRICK + (255,), width=6)

    inset = 64
    f_id = font("extrabold", 54)
    f_city = font("bold", 32)
    put_text(im, (w - 300 - inset, h * 0.30), spec["lines"][0], f_id, fill=CHARCOAL, anchor="rm")
    put_text(im, (w - 300 - inset, h * 0.42), spec["lines"][1], f_city, fill=BRICK, anchor="rm")
    rule(im, w - 300 - inset, int(h * 0.48), 220, EMBER, 6)

    diagonal_repeat(im, 0.14)
    watermark_strip(im, ratio=0.20, min_h=118)
    return im


def layout_sign(spec: dict) -> Image.Image:
    w, h = spec["size"]                      # 1500×1000
    tex = load_scene(spec["scene"], w, h)
    im = tex.convert("RGBA")
    dark = Image.new("RGBA", (w, h), CHARCOAL + (255,))
    mask = Image.new("L", (w, h), 205)
    dark.putalpha(mask)
    im.alpha_composite(dark)

    d = ImageDraw.Draw(im)
    d.rectangle([26, 26, w - 27, h - 27], outline=EMBER + (255,), width=6)
    d.rectangle([46, 46, w - 47, h - 47], outline=BRICK_LIGHT + (255,), width=3)

    f_id = font("extrabold", 74)
    f_city = font("bold", 46)
    f_num = font("extrabold", 168)
    put_text(im, (w / 2, h * 0.24), spec["lines"][0], f_id, fill=CREAM, anchor="mm", shadow=5)
    put_text(im, (w / 2, h * 0.34), spec["lines"][1], f_city, fill=EMBER, anchor="mm", shadow=3)
    rule(im, int(w * 0.66), int(h * 0.42), int(w * 0.32), SAND, 6)
    put_text(im, (w / 2, h * 0.60), NUMBER, f_num, fill=CREAM, anchor="mm", shadow=8)

    diagonal_repeat(im, 0.14)
    watermark_strip(im, ratio=0.115, min_h=110, stacked=False)
    return im


def layout_prices(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = Image.new("RGBA", (w, h), CHARCOAL + (255,))
    tex = load_scene(spec["scene"], w, h)
    tex = tex.convert("RGBA")
    tex.putalpha(Image.new("L", (w, h), 42))
    im.alpha_composite(tex)

    inset = max(56, int(w * 0.055))
    f_title = font("extrabold", int(w * 0.052))
    f_lab = font("bold", int(w * 0.036))
    f_val = font("extrabold", int(w * 0.038))
    d = ImageDraw.Draw(im)

    y = int(h * 0.10)
    put_text(im, (w - inset, y), spec["title"], f_title, fill=CREAM, anchor="rm")
    rule(im, w - inset, y + int(w * 0.035), int(w * 0.30), EMBER, 6)

    y = int(h * 0.24)
    row_h = int(h * 0.088)
    for lab, val in spec["rows"]:
        put_text(im, (w - inset, y + row_h * 0.45), lab, f_lab, fill=SAND, anchor="rm")
        put_text(im, (inset, y + row_h * 0.45), val, f_val, fill=EMBER, anchor="lm")
        d.line([(inset, y + row_h), (w - inset, y + row_h)], fill=SAND + (70,), width=2)
        y += row_h

    f_foot = font("bold", int(w * 0.034))
    put_text(im, (w - inset, h * 0.80), spec["foot"][0], f_foot, fill=SAND, anchor="rm")

    diagonal_repeat(im, 0.15)
    watermark_strip(im, ratio=0.13, min_h=110)
    return im


def layout_focus(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = base_canvas(None, spec)
    im = darken_bottom(im, 232, 0.30)
    im = darken_top(im, 150, 0.26)
    inset = max(56, int(w * 0.055))

    f_kick = font("bold", int(w * 0.036))
    f_hero = font("extrabold", int(w * 0.105))
    f_line = font("bold", int(w * 0.040))

    bar_h = max(84, int(h * 0.115))
    y = h - bar_h - int(h * 0.07)
    put_text(im, (w - inset, y - int(h * 0.16)), spec["kicker"], f_kick, fill=SAND, anchor="rm", shadow=4)
    put_text(im, (w - inset, y - int(h * 0.085)), spec["hero"], f_hero, fill=CREAM, anchor="rm", shadow=8)
    rule(im, w - inset, int(y - h * 0.035), int(w * 0.22), EMBER, int(w * 0.008))
    put_text(im, (w - inset, y), spec["lines"][0], f_line, fill=EMBER, anchor="rm", shadow=4)

    diagonal_repeat(im, 0.15)
    watermark_strip(im)
    return im


def layout_grid4(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = Image.new("RGBA", (w, h), CHARCOAL + (255,))
    gut = int(w * 0.035)
    bar_h = max(84, int(h * 0.115))
    grid_h = int(h * 0.66)
    cw = (w - gut * 3) // 2
    ch = (grid_h - gut * 3) // 2
    for i, sc in enumerate(spec["scenes"]):
        cell = load_scene(sc, cw, ch)
        x = gut + (i % 2) * (cw + gut)
        y = gut + (i // 2) * (ch + gut)
        im.alpha_composite(cell.convert("RGBA"), (x, y))
        d = ImageDraw.Draw(im)
        d.rectangle([x, y, x + cw, y + ch], outline=SAND + (120,), width=3)

    f1 = font("extrabold", int(w * 0.058))
    f2 = font("bold", int(w * 0.040))
    y_txt = gut * 2 + grid_h + int(h * 0.045)
    put_text(im, (w - gut, y_txt), spec["lines"][0], f1, fill=CREAM, anchor="rm")
    put_text(im, (w - gut, y_txt + int(h * 0.055)), spec["lines"][1], f2, fill=EMBER, anchor="rm")

    diagonal_repeat(im, 0.15)
    watermark_strip(im)
    return im


def layout_frame(spec: dict) -> Image.Image:
    w, h = spec["size"]
    im = Image.new("RGBA", (w, h), SAND + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=BRICK + (255,), width=8)

    bar_h = max(84, int(h * 0.115))
    box = int(w * 0.40)
    gap = int(w * 0.05)
    y0 = int(h * 0.14)
    for i, lab in enumerate(spec["labels"]):
        x = w - gap - box - i * (box + gap)          # «قبل» يميناً ثم «بعد»
        d.rectangle([x, y0, x + box, y0 + box], fill=CREAM + (255,), outline=BRICK_LIGHT + (255,), width=5)
        # حدود متقطعة داخلية
        for k in range(0, box, 26):
            d.line([(x + k, y0 + box - 12), (x + min(k + 14, box), y0 + box - 12)], fill=BRICK + (120,), width=3)
            d.line([(x + k, y0 + 12), (x + min(k + 14, box), y0 + 12)], fill=BRICK + (120,), width=3)
        f_lab = font("bold", int(w * 0.042))
        put_text(im, (x + box / 2, y0 + box + int(w * 0.035)), lab, f_lab, fill=CHARCOAL, anchor="mm")

    f_cap = font("extrabold", int(w * 0.048))
    put_text(im, (w / 2, h - bar_h - int(h * 0.055)), spec["caption"], f_cap, fill=CHARCOAL, anchor="mm")

    diagonal_repeat(im, 0.14)
    watermark_strip(im)
    return im


LAYOUTS = {
    "post": layout_post,
    "story": layout_story,
    "profile": layout_profile,
    "cover": layout_cover,
    "card": layout_card,
    "sign": layout_sign,
    "prices": layout_prices,
    "focus": layout_focus,
    "grid4": layout_grid4,
    "frame": layout_frame,
}


# -------------------------------------------------------------------- البناء
def build(name: str, verbose: bool = True) -> Path | None:
    spec = SPEC["images"][name]
    out = ROOT / spec["file"]
    try:
        im = LAYOUTS[spec["layout"]](spec)
    except FileNotFoundError as e:
        if verbose:
            print(f"  — {name}: تخطّي ({e})")
        return None
    assert im.size == tuple(spec["size"]), f"{name}: المقاس {im.size} ≠ المطلوب {tuple(spec['size'])}"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, "PNG", optimize=True)
    if verbose:
        print(f"  ✔ {name:<22} {im.size[0]}×{im.size[1]}  →  {spec['file']}")
    return out


def contact_sheet() -> Path:
    names = [n for n in SPEC["images"] if (ROOT / SPEC["images"][n]["file"]).exists()]
    if not names:
        raise SystemExit("لا توجد صور نهائية بعد — شغّل --all أولاً")
    cols = 4
    thumb_w = 380
    pad, label_h = 14, 40
    rows = math.ceil(len(names) / cols)
    cells = []
    for n in names:
        im = Image.open(ROOT / SPEC["images"][n]["file"]).convert("RGB")
        th = int(im.height * thumb_w / im.width)
        cells.append((n, im.resize((thumb_w, th), Image.LANCZOS)))
    max_h = max(c[1].height for c in cells)
    sheet_w = cols * (thumb_w + pad) + pad
    sheet_h = rows * (max_h + label_h + pad) + pad + 70
    sheet = Image.new("RGB", (sheet_w, sheet_h), CHARCOAL)
    d = ImageDraw.Draw(sheet)
    f_title = font("extrabold", 34)
    f_lab = font("bold", 20)
    d.text((sheet_w / 2, 44), ar("حزمة مشبات وأفران — الرياض  •  0531060401"), font=f_title,
           fill=CREAM, anchor="mm")
    for i, (n, th) in enumerate(cells):
        r, c = divmod(i, cols)
        x = pad + c * (thumb_w + pad)
        y = 70 + pad + r * (max_h + label_h + pad)
        sheet.paste(th, (x, y))
        d.rectangle([x, y, x + thumb_w, y + th.height], outline=BRICK_LIGHT, width=2)
        d.text((x + thumb_w / 2, y + th.height + 22), ar(n), font=f_lab, fill=SAND, anchor="mm")
    out = ROOT / "contact-sheet.png"
    sheet.save(out, "PNG", optimize=True)
    print(f"  ✔ contact-sheet.png  {sheet.size[0]}×{sheet.size[1]}  ({len(names)} صورة)")
    return out


def main() -> int:
    args = sys.argv[1:]
    if not args or "--list" in args:
        for n, s in SPEC["images"].items():
            exists = "✔" if (ROOT / s["file"]).exists() else "·"
            print(f" {exists} {n:<22} {s['size'][0]}×{s['size'][1]:<5} {s['file']}")
        return 0
    if "--sheet" in args:
        contact_sheet()
        return 0
    targets = SPEC["images"].keys() if "--all" in args else args
    missing_scenes = 0
    for n in targets:
        if n not in SPEC["images"]:
            print(f"  ! اسم غير معروف: {n}")
            continue
        if build(n) is None:
            missing_scenes += 1
    if missing_scenes:
        print(f"\n{missing_scenes} عنصر بانتظار مشاهده.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
