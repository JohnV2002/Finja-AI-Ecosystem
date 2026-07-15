"""
======================================================================
         Finja Omni Test – OCR Reader
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / ocr
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Reusable OCR reader (latin5fast) — the heart of Layer 1.
  Encapsulates RapidOCR PP-OCRv5 latin + reading order sorting + junk 
  filtering, so that benchmark AND live pipeline (verarbeite.py) use 
  the same logic.
======================================================================
"""

import os

CPU_THREADS = 2
os.environ["OMP_NUM_THREADS"]      = str(CPU_THREADS)
os.environ["OPENBLAS_NUM_THREADS"] = str(CPU_THREADS)

import re

_HAS_LETTER = re.compile(r"[a-zA-ZäöüßÄÖÜàâçéèêëîïôûùüÿñ]")

# CPU throttling via process affinity
try:
    import psutil
    _p = psutil.Process()
    _p.cpu_affinity(list(range(min(CPU_THREADS, psutil.cpu_count()))))
    if os.name == "nt":
        _p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

from rapidocr import RapidOCR
from rapidocr.utils.typings import OCRVersion, LangDet, LangRec, ModelType

MIN_CONF = 0.8
LINE_TOL = 20   # px tolerance "same line"

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = RapidOCR(params={
            "Det.ocr_version": OCRVersion.PPOCRV5, "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec.LATIN,
            "Rec.model_type": ModelType.MOBILE,
            "EngineConfig.onnxruntime.intra_op_num_threads": CPU_THREADS,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
    return _engine


def _is_junk(token):
    t = token.strip()
    if not t or not _HAS_LETTER.search(t):
        return True
    if len(t) == 1 and t in "OoO© ":
        return True
    return False


def _box_top_left(box):
    try:
        return min(p[1] for p in box), min(p[0] for p in box)
    except Exception:
        return 0, 0


def read_text(image, band=None):
    """OCR -> clean text in reading order.

    image: File path OR PIL Image (the latter for the live loop).
    band: None = whole image. 0.4 = only bottom 40% (subtitle zone).
    Returns "" if nothing useful is found.
    """
    import numpy as np
    from PIL import Image as _Image

    img = image if isinstance(image, _Image.Image) else _Image.open(image)
    img = img.convert("RGB")
    if band:
        w, h = img.size
        img = img.crop((0, int(h * (1 - band)), w, h))
    arr = np.array(img)

    res = _get_engine()(arr)
    txts   = getattr(res, "txts", None)
    scores = getattr(res, "scores", None)
    boxes  = getattr(res, "boxes", None)
    if not txts:
        return ""

    items = []
    for i, t in enumerate(txts):
        c = float(scores[i]) if scores is not None else 1.0
        if c < MIN_CONF or _is_junk(str(t)):
            continue
        y, x = _box_top_left(boxes[i]) if boxes is not None and i < len(boxes) else (i, 0)
        items.append((y, x, str(t).strip()))

    if not items:
        return ""

    # Reading order: group lines by y, then within by x
    items.sort(key=lambda it: it[0])
    out, line, cur_y = [], [], None
    for y, x, t in items:
        if cur_y is None or abs(y - cur_y) <= LINE_TOL:
            line.append((x, t)); cur_y = y if cur_y is None else cur_y
        else:
            line.sort(); out += [t for _, t in line]
            line = [(x, t)]; cur_y = y
    if line:
        line.sort(); out += [t for _, t in line]
    return " ".join(out)
