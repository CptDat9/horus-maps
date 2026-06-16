"""End-to-end verification on the REAL production code path with the live
profile config (TILE_SIZE/IMGSZ_SIZE/IDEAL_ZOOM read from the module). Runs each
test image through _detect_tiled + _filter_implausible at its production zoom.
No imagery fetch — the scene is resized to the zoom's mosaic scale where known."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from PIL import Image
from app.services.ml_service import (
    MLService, TILE_SIZE, IMGSZ_SIZE, OVERLAP_SIZE, IDEAL_ZOOM, CLASS_GROUPS,
    _DEFAULT_TILE, _DEFAULT_IMGSZ, _DEFAULT_OVERLAP, DOTA_CLASSES,
)

ml = MLService()

def counts(dets):
    c = {}
    for _, cid, _ in dets:
        c[DOTA_CLASSES[cid]] = c.get(DOTA_CLASSES[cid], 0) + 1
    return dict(sorted(c.items()))

def run(path, object_class, z, lat, conf, resize_w=None):
    classes = CLASS_GROUPS[object_class]
    profile = ml._profile_for_classes(classes)
    tile = TILE_SIZE.get(profile, _DEFAULT_TILE)
    imgsz = IMGSZ_SIZE.get(profile, _DEFAULT_IMGSZ)
    overlap = OVERLAP_SIZE.get(profile, _DEFAULT_OVERLAP)
    img = Image.open(path).convert("RGB")
    if resize_w:
        img = img.resize((resize_w, int(resize_w * img.size[1] / img.size[0])), Image.LANCZOS)
    t0 = time.perf_counter()
    dets = ml._detect_tiled(img, tile, overlap, conf, classes, 0.5, imgsz)
    kept = ml._filter_implausible(dets, z, lat, conf)
    el = time.perf_counter() - t0
    print(f"\n[{os.path.basename(path)}] {object_class}→{profile} z={z} "
          f"tile={tile} imgsz={imgsz} conf={conf} img={img.size} ({el:.0f}s)")
    print(f"   raw={sum(counts(dets).values())} {counts(dets)}  ->  "
          f"kept={sum(counts(kept).values())} {counts(kept)}")
    return counts(kept)

# 1) vehicles regression check (image.png ≈ z20 native)
c = run("docs/tests/image.png", "vehicles", 20, 16.05, 0.08)
print(f"   small-veh>5: {'PASS' if c.get('small-vehicle',0)>5 else 'FAIL'} ({c.get('small-vehicle',0)})")

# 2) THE FIX: port scene at vessels z17 (mosaic z19≈6912 → z17≈1728)
c = run("docs/tests/detection_56e45540-e1fe-426c-b7b3-1e551459bb33.png", "vessels", 17, 16.05, 0.08, resize_w=1728)
print(f"   ship>15: {'PASS' if c.get('ship',0)>15 else 'FAIL'} ({c.get('ship',0)}) | "
      f"harbor>=2: {'PASS' if c.get('harbor',0)>=2 else 'FAIL'} ({c.get('harbor',0)})")

# 3) don't-break check: aoi_C_ng with the new vessels config, native + 2x-coarser
for w in (None, 853):
    c = run("docs/tests/aoi_C_ng.png", "vessels", 17, 16.05, 0.08, resize_w=w)
    print(f"   ship>9: {'PASS' if c.get('ship',0)>9 else 'FAIL'} ({c.get('ship',0)})")
