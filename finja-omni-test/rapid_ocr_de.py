"""
======================================================================
         Finja Omni Test – RapidOCR Benchmark
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / rapid_ocr_de
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
  CPU-OCR Benchmark with RapidOCR + LATIN/Multilang model.
  Latin model = German + English + all Latin languages in ONE model,
  incl. umlauts (ä ö ü) and ß. Runs as ONNX -> Python 3.14 compatible
  (no paddlepaddle needed). Writes summary.json for vergleich.py.

  Installation (new, unified package):
      pip install rapidocr onnxruntime psutil
  (downloads the Latin model automatically on first run)
======================================================================
"""

import os

# Throttle CPU (before heavy imports)
CPU_THREADS = 2
os.environ["OMP_NUM_THREADS"]      = str(CPU_THREADS)
os.environ["OPENBLAS_NUM_THREADS"] = str(CPU_THREADS)

import sys
import glob
import json
import time
import re
import statistics

# Tokens without letters (pure digits/symbols like "000", "0", "□", "∞00")
# are OCR junk from logos/effects -> filter out. Real words stay.
_HAS_LETTER = re.compile(r"[a-zA-ZäöüßÄÖÜàâçéèêëîïôûùüÿñ]")

def is_junk(token):
    t = token.strip()
    if not t:
        return True
    if not _HAS_LETTER.search(t):      # not a single letter -> junk
        return True
    if len(t) == 1 and t in "OoO© ":   # isolated single characters
        return True
    return False

# Pin process to a few cores
try:
    import psutil
    _p = psutil.Process()
    _p.cpu_affinity(list(range(min(CPU_THREADS, psutil.cpu_count()))))
    if os.name == "nt":
        _p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    print(f"[i] CPU throttled to {CPU_THREADS} cores")
except Exception as e:
    print(f"[i] CPU throttle not possible ({e})")

# New 'rapidocr' package (>=2.0) can switch the recognition language.
try:
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import OCRVersion, LangDet, LangRec, ModelType
    NEW_API = True
except ImportError:
    try:
        from rapidocr_onnxruntime import RapidOCR
        NEW_API = False
    except ImportError:
        raise SystemExit("Please install:  pip install rapidocr onnxruntime")

# Input folder via argument: python rapid_ocr_de.py captures/editor
# Without argument -> default test_frames (Anime benchmark).
INPUT_DIR   = sys.argv[1] if len(sys.argv) > 1 else "test_frames"
RESULTS_DIR = "benchmark_results"
# Derive result label from folder name (e.g. "editor", "youtube")
INPUT_TAG   = os.path.basename(os.path.normpath(INPUT_DIR))
MIN_CONF    = 0.8   # >=0.8: filters false alarms on empty frames (Empty% ~94%)

# --- Select PROFILE: which Det/Rec model combo to test? ---
# Just change PROFILE and run the script again. Each profile gets its own
# folder -> all end up side-by-side in vergleich.py.
# IMPORTANT: rapidocr requires REAL Enum objects (no strings)!
if NEW_API:
    PROFILES = {
        # Latin specialist (PP-OCRv5) – best bet for German.
        # Det is language independent (ch), Rec uses the latin model.
        "latin5": {
            "Det.ocr_version": OCRVersion.PPOCRV5, "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.SERVER,
            "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec.LATIN,
            "Rec.model_type": ModelType.MOBILE,
        },
        # Like latin5, but fast det_mobile instead of det_server (~5x faster).
        # Same latin recognition -> umlauts stay, just det is lighter.
        "latin5fast": {
            "Det.ocr_version": OCRVersion.PPOCRV5, "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec.LATIN,
            "Rec.model_type": ModelType.MOBILE,
        },
        # PP-OCRv6 medium (larger multi-allrounder than the small)
        "v6medium": {
            "Det.ocr_version": OCRVersion.PPOCRV6, "Det.lang_type": LangDet.MULTI,
            "Det.model_type": ModelType.MEDIUM,
            "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.lang_type": LangRec.CH,
            "Rec.model_type": ModelType.MEDIUM,
        },
        # Reference: the small V6 (what we already had)
        "v6small": {
            "Det.ocr_version": OCRVersion.PPOCRV6, "Det.lang_type": LangDet.MULTI,
            "Det.model_type": ModelType.SMALL,
            "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.lang_type": LangRec.CH,
            "Rec.model_type": ModelType.SMALL,
        },
    }
else:
    PROFILES = {"latin5": {}}
PROFILE     = "latin5fast"       # <- latin5fast / latin5 / v6medium / v6small
# Result folder contains content + profile, e.g. "RapidOCR-latin5fast-editor"
_tag_suffix = "" if INPUT_TAG in ("test_frames", "") else f"-{INPUT_TAG}"
MODEL_NAME  = f"RapidOCR-{PROFILE}{_tag_suffix}"

out_dir   = os.path.join(RESULTS_DIR, MODEL_NAME)
os.makedirs(out_dir, exist_ok=True)
log_file  = os.path.join(out_dir, "ocr_log.txt")
json_file = os.path.join(out_dir, "summary.json")

image_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.png")))
if not image_files:
    raise SystemExit(f"No images in '{INPUT_DIR}'!")
total_images = len(image_files)

print("=" * 60)
print(f"  CPU BENCHMARK: {MODEL_NAME}   (API: {'new' if NEW_API else 'old'})")
print(f"  Images: {total_images}")
print("=" * 60)

# Engine with chosen profile + thread throttle via config
params = dict(PROFILES[PROFILE])
params["EngineConfig.onnxruntime.intra_op_num_threads"] = CPU_THREADS
params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
if NEW_API:
    try:
        engine = RapidOCR(params=params)
        print(f"[i] Profile '{PROFILE}' active: {PROFILES[PROFILE]}")
    except Exception as e:
        print(f"[!] Profile rejected ({e}) -> standard model")
        engine = RapidOCR()
else:
    print("[!] Old rapidocr_onnxruntime – please 'pip install -U rapidocr'.")
    engine = RapidOCR()


def _box_top_left(box):
    """Returns (y, x) of the top-left corner of a box [[x,y],...]."""
    try:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        return min(ys), min(xs)
    except Exception:
        return 0, 0


def run_ocr(path):
    """Sort OCR + boxes in READING ORDER (top->bottom, left->right).

    This way 'The trailer is from the movie, right?' comes out clean instead
    of chopped up. Returns (text, conf) list in reading order.
    """
    res = engine(path)
    items = []   # (y, x, text, conf)
    if NEW_API:
        txts   = getattr(res, "txts", None)
        scores = getattr(res, "scores", None)
        boxes  = getattr(res, "boxes", None)
        if txts:
            for i, t in enumerate(txts):
                c = float(scores[i]) if scores is not None else 1.0
                if boxes is not None and i < len(boxes):
                    y, x = _box_top_left(boxes[i])
                else:
                    y, x = i, 0   # Fallback: original order
                items.append((y, x, t, c))
    else:
        result = res[0] if isinstance(res, tuple) else res
        for item in (result or []):
            try:
                y, x = _box_top_left(item[0])
                c = float(item[2])
            except (IndexError, TypeError, ValueError):
                y, x, c = 0, 0, 1.0
            items.append((y, x, item[1], c))

    # Group lines: boxes with similar y = same line, then by x
    items.sort(key=lambda it: it[0])
    LINE_TOL = 20  # Pixel tolerance for "same line"
    items_sorted = []
    line = []
    cur_y = None
    for y, x, t, c in items:
        if cur_y is None or abs(y - cur_y) <= LINE_TOL:
            line.append((x, t, c))
            cur_y = y if cur_y is None else cur_y
        else:
            line.sort(key=lambda e: e[0])
            items_sorted += [(t, c) for _, t, c in line]
            line = [(x, t, c)]
            cur_y = y
    if line:
        line.sort(key=lambda e: e[0])
        items_sorted += [(t, c) for _, t, c in line]
    return items_sorted


times = []
found_frames = empty_frames = error_frames = 0
results = []
predictions = {}

run_start = time.perf_counter()

for idx, img_path in enumerate(image_files, start=1):
    filename = os.path.basename(img_path)
    t0 = time.perf_counter()
    try:
        lines = run_ocr(img_path)
        status = "ok"
    except Exception as e:
        lines, status, err = [], "error", str(e)
    elapsed = time.perf_counter() - t0

    if status != "ok":
        tag = f"[ERROR: {err}]"
        error_frames += 1
        predictions[filename] = "error"
    else:
        texts = [str(t).strip() for t, c in lines
                 if c >= MIN_CONF and not is_junk(str(t))]
        if texts:
            tag = "TEXT: " + " ".join(texts)
            found_frames += 1
            predictions[filename] = "text"
        else:
            tag = "[EMPTY]"
            empty_frames += 1
            predictions[filename] = "leer"
        times.append(elapsed)

    line = f"[{idx:>4}/{total_images}] {elapsed:6.3f}s  {filename}  ->  {tag}"
    print(line)
    results.append(line)

total_time = time.perf_counter() - run_start

if times:
    avg, med = statistics.mean(times), statistics.median(times)
    best, worst = min(times), max(times)
    fps = 1 / avg
else:
    avg = med = best = worst = fps = 0.0

summary_txt = f"""
{'=' * 60}
  CONCLUSION  –  {MODEL_NAME}
{'=' * 60}
  Frames total:    {total_images}
  With Text:       {found_frames}
  Empty:           {empty_frames}
  Errors:          {error_frames}
  ─────────────────────────────
  Fastest:         {best:.3f} s
  Slowest:         {worst:.3f} s
  Median:          {med:.3f} s
  Average:         {avg:.3f} s/Frame  (~{fps:.2f} FPS)
  Total time:      {total_time:.2f} s
{'=' * 60}
"""
print(summary_txt)

with open(log_file, "w", encoding="utf-8") as log:
    log.write(f"=== BENCHMARK START: {MODEL_NAME} ===\n\n")
    log.write("\n".join(results))
    log.write(summary_txt)

with open(json_file, "w", encoding="utf-8") as jf:
    json.dump({
        "model": MODEL_NAME, "frames_total": total_images,
        "with_text": found_frames, "empty": empty_frames, "errors": error_frames,
        "fastest_s": round(best, 3), "slowest_s": round(worst, 3),
        "median_s": round(med, 3), "avg_s": round(avg, 3), "fps": round(fps, 2),
        "total_time_s": round(total_time, 2), "predictions": predictions,
    }, jf, indent=2, ensure_ascii=False)

print(f"Log:  {log_file}")
print(f"JSON: {json_file}")
print("\nNow 'python vergleich.py' for the table. :3")
