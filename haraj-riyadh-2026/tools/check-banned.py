#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فاحص الكلمات الممنوعة — haraj-riyadh-2026

يفحص:
  1) الملفات العامة (ما يصل للعميل: هوية، منشورات، رسائل قروبات، روابط، نصوص الصور)
  2) الملفات الداخلية (خطط ومتابعة) — تُطبع مطابقاتها للعلم، ولا تُفشل الفحص

الاستخدام:
    python3 tools/check-banned.py            # فحص كامل
    python3 tools/check-banned.py --json     # مخرجات JSON
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- القائمة
BANNED = [
    # ترميم
    "ترميم", "ترميمات", "نرمم", "ترميمه",
    # تصغير الحرفة
    "صغير", "صغيرة", "معلم صغير",
    # وعود مدة التنفيذ
    "أسبوع", "اسبوع", "يومين", "خلال أيام", "خلال ايام", "بسرعة",
    "اليوم نخلّص", "اليوم نخلص", "شغل سريع",
    # شعارات الدفع
    "دفعة أولى", "دفعة اولى", "الباقي بالتسليم", "قبل البدء", "بدون مفاجآت", "بدون مفاجئات",
    # كلمات البيع الرخيص
    "عرض", "عروض", "خصم", "خصومات", "معاينة", "مجاني", "مجاناً", "مجانا", "مجانية",
    # الاستجداء
    "محتاج شغل", "الله يكتب الرزق", "ادعموني",
    # خطأ إملائي قديم في الرقم/التطبيق
    "وأتساب", "واتس اب", "واتسآب", "وأتس اب",
]

# الاسم الشخصي ممنوع — نفحصه بنمط، لا بقائمة كلمات.
# أي سطر فيه لقب عائلي معروف بجانب صيغة تعريف يُرصد يدوياً في المراجعة البصرية.
NAME_PATTERNS = [
    r"أبو\s+[عبداللهمحمدسعدفهدخالد]",
    r"\b(بن|آل)\s+[عبداللهمحمدسعدفهدخالدناصر]",
]

# ------------------------------------------------------- تصنيف الملفات
PUBLIC_FILES = [
    "01-الهوية.md",
    "02-المنشورات.md",
    "قوالب/رسائل-القروبات.md",
    "روابط.md",
    "tools/image-spec.json",   # نصوص الصور — مادة عامة مطبوعة على البكسلات
]

INTERNAL_FILES = [
    "00-اليوم-الأول.md",
    "03-خطة-الأسبوع-والانتشار.md",
    "04-واتساب-والمتابعة.md",
    "05-الأسعار.md",
    "06-دليل-الصور.md",
    "README.md",
    "تقرير-الفحص.md",
    "قوالب/سجل-العملاء.csv",
]

# مواضع يُسمح فيها استثناءً بذكر كلمة ممنوعة داخل ملف عام، بشرط أن تكون
# في سياق «ممنوع» صريح (توثيق القاعدة، لا استخدام لها).
ALLOWED_CONTEXTS = {
    # لا شيء حالياً — الملفات العامة لا تذكر الممنوعات حتى في سياق النفي.
}


def scan_text(text: str, label: str):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line
        for word in BANNED:
            if word in low:
                hits.append({"file": label, "line": i, "word": word, "text": line.strip()})
        for pat in NAME_PATTERNS:
            if re.search(pat, low):
                hits.append({"file": label, "line": i, "word": f"[نمط اسم شخصي: {pat}]",
                             "text": line.strip()})
    return hits


def main() -> int:
    as_json = "--json" in sys.argv
    public_hits, internal_hits, missing = [], [], []

    for rel in PUBLIC_FILES:
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        public_hits += scan_text(p.read_text(encoding="utf-8"), rel)

    for rel in INTERNAL_FILES:
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        internal_hits += scan_text(p.read_text(encoding="utf-8"), rel)

    # -------------------------------------------------- تقرير
    if as_json:
        print(json.dumps({
            "public_matches": len(public_hits),
            "internal_matches": len(internal_hits),
            "missing_files": missing,
            "public": public_hits,
            "internal": internal_hits,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 68)
        print("فحص الكلمات الممنوعة — haraj-riyadh-2026")
        print("=" * 68)
        print(f"الملفات العامة المفحوصة : {len(PUBLIC_FILES) - len([m for m in missing if m in PUBLIC_FILES])}")
        print(f"الملفات الداخلية        : {len(INTERNAL_FILES) - len([m for m in missing if m in INTERNAL_FILES])}")
        print("-" * 68)
        print(f"مطابقات في الملفات العامة : {len(public_hits)}")
        for h in public_hits:
            print(f"  ✗ {h['file']}:{h['line']} — «{h['word']}» → {h['text'][:70]}")
        print("-" * 68)
        print(f"مطابقات في الملفات الداخلية (مسموحة، للعلم) : {len(internal_hits)}")
        for h in internal_hits[:40]:
            print(f"  · {h['file']}:{h['line']} — «{h['word']}»")
        if len(internal_hits) > 40:
            print(f"  ... و{len(internal_hits) - 40} مطابقة أخرى داخلية")
        if missing:
            print("-" * 68)
            print("ملفات مفقودة:")
            for m in missing:
                print(f"  ! {m}")
        print("=" * 68)
        if not public_hits:
            print("النتيجة: صفر مطابقات في الملفات العامة ✔")
        else:
            print("النتيجة: توجد مطابقات في ملفات عامة ✗ — صحّحها قبل النشر")

    return 1 if (public_hits or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
