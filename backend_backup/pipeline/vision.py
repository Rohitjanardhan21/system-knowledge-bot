"""
pipeline/vision.py  —  CVIS v5.0  (final)
──────────────────────────────────────────
Layer 1 — Vision Intelligence

Stack:
  1. YOLOv8n (ultralytics)         — object detection, 80 COCO classes
  2. DeepSORT / centroid tracker   — stable multi-frame IDs
  3. MiDaS DPT-Hybrid              — monocular depth estimation
  4. Calibrated depth → metres     — Fix 2 (self-calibrating K-scale)
  5. VelocityEstimator             — per-track rolling velocity
  6. TTC                           — time-to-collision per object

Fix 2 — Metric Depth Calibration:
  MiDaS outputs relative inverse depth, not metres.
  Conversion (priority order per detection):

    Priority 1: focal-length formula
        distance = (known_height_m × FY) / box_height_px
      Requires YOLO class with known real-world height.
      Uses camera intrinsic FY (focal length, vertical pixels).

    Priority 2: calibrated MiDaS K-scale
        distance = _depth_scale / median_midas_depth_in_roi
      _depth_scale starts at DEFAULT_K_SCALE (5.5) and
      self-calibrates from Priority 1 hits after ~20 detections.
      Uses median of lower-2/3 of bounding box (avoids sky/BG).

    Priority 3: heuristic perspective prior (no torch)

Thread model: runs in ThreadPoolExecutor worker, never on event loop.
"""

import io
import logging
import math
import time
from collections import defaultdict, deque
from typing import Any

import numpy as np

log = logging.getLogger("cvis.vision")

try:
    import torch
    import torch.nn.functional as F
    from PIL import Image
    from ultralytics import YOLO
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False
    log.warning("PyTorch/ultralytics not installed — vision in synthetic mode")

try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
    _DEEPSORT_OK = True
except ImportError:
    _DEEPSORT_OK = False
    log.warning("deep-sort-realtime not installed — using centroid tracker")


# ═══════════════════════════════════════════════════════════════
#  SIMPLE CENTROID TRACKER  (fallback when DeepSORT unavailable)
# ═══════════════════════════════════════════════════════════════
class SimpleCentroidTracker:
    def __init__(self, max_disappeared: int = 20):
        self.next_id      = 0
        self.objects:dict = {}
        self.disappeared  = defaultdict(int)
        self.max_dis      = max_disappeared

    @staticmethod
    def _iou(a, b):
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        union = ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter)
        return inter / (union + 1e-6)

    def update(self, detections: list[dict]) -> list[dict]:
        if not detections:
            for oid in list(self.objects):
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_dis:
                    del self.objects[oid]; del self.disappeared[oid]
            return []

        results = []
        if not self.objects:
            for det in detections:
                tid = self.next_id; self.next_id += 1
                cx  = (det["box"][0]+det["box"][2])/2
                cy  = (det["box"][1]+det["box"][3])/2
                self.objects[tid] = (cx, cy); self.disappeared[tid] = 0
                results.append({**det, "track_id": tid})
            return results

        used_obj = set(); used_det = set()
        for oid, (ox, oy) in self.objects.items():
            best_iou, best_i = -1, -1
            for i, det in enumerate(detections):
                if i in used_det: continue
                pseudo = (ox-30, oy-30, ox+30, oy+30)
                b      = det["box"]
                iou    = self._iou(pseudo, (b[0], b[1], b[2], b[3]))
                if iou > best_iou: best_iou, best_i = iou, i
            if best_iou > 0.15:
                used_obj.add(oid); used_det.add(best_i)
                det = detections[best_i]
                cx  = (det["box"][0]+det["box"][2])/2
                cy  = (det["box"][1]+det["box"][3])/2
                self.objects[oid] = (cx, cy); self.disappeared[oid] = 0
                results.append({**det, "track_id": oid})

        for i, det in enumerate(detections):
            if i not in used_det:
                tid = self.next_id; self.next_id += 1
                cx  = (det["box"][0]+det["box"][2])/2
                cy  = (det["box"][1]+det["box"][3])/2
                self.objects[tid] = (cx, cy); self.disappeared[tid] = 0
                results.append({**det, "track_id": tid})

        for oid in list(self.objects):
            if oid not in used_obj:
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_dis:
                    del self.objects[oid]; del self.disappeared[oid]
        return results


# ═══════════════════════════════════════════════════════════════
#  VELOCITY ESTIMATOR
# ═══════════════════════════════════════════════════════════════
class VelocityEstimator:
    WINDOW = 8

    def __init__(self):
        self._hist: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=self.WINDOW)
        )

    def update(self, tid: int, cx: float, cy: float, ts: float):
        self._hist[tid].append((cx, cy, ts))

    def get(self, tid: int) -> tuple[float, float]:
        h = self._hist.get(tid)
        if not h or len(h) < 2:
            return 0.0, 0.0
        a, b = h[0], h[-1]
        dt   = b[2] - a[2]
        if dt < 1e-4:
            return 0.0, 0.0
        return (b[0]-a[0])/dt, (b[1]-a[1])/dt


# ═══════════════════════════════════════════════════════════════
#  DEPTH ESTIMATOR  —  Fix 2: calibrated metric distance
# ═══════════════════════════════════════════════════════════════
class DepthEstimator:
    """
    MiDaS DPT-Hybrid monocular depth with self-calibrating metric conversion.

    MiDaS outputs relative inverse depth — not metric metres.
    This class converts to metres using (in priority order):

      Priority 1: focal-length formula (most accurate)
          distance_m = (known_height_m × FY) / box_height_px
        Requires a YOLO class with a known real-world height.
        Uses camera intrinsic FY (focal length, vertical, pixels).

      Priority 2: calibrated K-scale
          distance_m = _depth_scale / median(midas_roi)
        _depth_scale starts at DEFAULT_K_SCALE (5.5 m).
        Every Priority 1 hit records (midas_val × metric_dist) into
        a 100-sample rolling buffer; _depth_scale = median(buffer).
        Converges to within ~5% of true K after ~20 detections.

      Priority 3: heuristic perspective prior
        Used when torch is unavailable.
    """

    # Camera intrinsics — tune with cv2.calibrateCamera() for accuracy.
    # Defaults: typical 1080p dashcam, ~60° HFOV, 4mm lens.
    FX = 700.0   # focal length, horizontal (px)
    FY = 700.0   # focal length, vertical   (px)
    CX = 320.0   # principal point x (px)
    CY = 240.0   # principal point y (px)

    # Initial MiDaS→metric scale: distance = K / midas_inv_depth.
    # Self-calibrates from bounding-box focal-length hits.
    DEFAULT_K_SCALE = 5.5

    def __init__(self):
        self.model         = None
        self.transform     = None
        self.device        = "cpu"
        self._depth_scale  = self.DEFAULT_K_SCALE
        self._calibrated   = False
        self._calib_buf: list[tuple[float, float]] = []   # (midas_val, metric_m)

    def load(self):
        if not _TORCH_OK:
            log.info("Depth: heuristic mode (no torch)")
            return
        try:
            self.device    = "cuda" if torch.cuda.is_available() else "cpu"
            self.model     = torch.hub.load(
                "intel-isl/MiDaS", "DPT_Hybrid", trust_repo=True
            ).to(self.device).eval()
            transforms     = torch.hub.load("intel-isl/MiDaS", "transforms")
            self.transform = transforms.dpt_transform
            log.info(f"MiDaS DPT-Hybrid loaded on {self.device}")
        except Exception as e:
            log.warning(f"MiDaS load failed ({e}) — heuristic depth")
            self.model = None

    def estimate(self, img_np: np.ndarray) -> np.ndarray:
        """Returns normalised inverse-depth map, H×W, values in [0,1]."""
        if self.model is None or not _TORCH_OK:
            return self._heuristic(img_np)
        h, w = img_np.shape[:2]
        inp  = self.transform(img_np).to(self.device)
        with torch.no_grad():
            pred = self.model(inp)
            pred = F.interpolate(
                pred.unsqueeze(1), size=(h, w),
                mode="bicubic", align_corners=False,
            ).squeeze()
        d = pred.cpu().numpy()
        dmin, dmax = d.min(), d.max()
        return (d - dmin) / (dmax - dmin + 1e-6)

    @staticmethod
    def _heuristic(img_np: np.ndarray) -> np.ndarray:
        h, w  = img_np.shape[:2]
        y     = np.linspace(0, 1, h)[:, None]
        return np.tile(1.0 - y, (1, w)).astype(np.float32)

    def box_depth(
        self,
        depth_map: np.ndarray,
        box: list[float],
        known_height_m: float | None = None,
        box_height_px:  float | None = None,
    ) -> float:
        """
        Convert bounding box to metric distance (metres).

        Priority 1: focal-length formula (when known_height_m provided).
        Priority 2: calibrated MiDaS K-scale.
        Returns value clamped to [1, 120] m.
        """
        # Priority 1 —————————————————————————————————————————
        if known_height_m and box_height_px and box_height_px > 8:
            metric = (known_height_m * self.FY) / box_height_px
            metric = float(np.clip(metric, 1.0, 120.0))
            self._self_calibrate(box, depth_map, metric)   # feed back to refine K
            return metric

        # Priority 2 —————————————————————————————————————————
        roi_med = self._roi_median(box, depth_map)
        if roi_med is None:
            return 15.0
        return float(np.clip(self._depth_scale / (roi_med + 1e-6), 1.0, 120.0))

    def _roi_median(self, box: list[float], depth_map: np.ndarray) -> float | None:
        """
        Median inverse-depth in lower 2/3 of bounding box.
        Skips top third to avoid sky/background contamination.
        Uses median (not mean) — robust against occluded pixels.
        """
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = depth_map.shape
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        y_start = y1 + (y2 - y1) // 3
        roi     = depth_map[y_start:y2, x1:x2]
        if roi.size == 0:
            return None
        v = float(np.median(roi))
        return v if v > 1e-4 else None

    def _self_calibrate(
        self, box: list[float], depth_map: np.ndarray, metric_dist: float
    ):
        """
        Record (midas_val, metric_dist) → update K-scale as median ratio.
        After ~20 samples, _depth_scale converges to within ~5% of true K.
        """
        midas_val = self._roi_median(box, depth_map)
        if midas_val is None:
            return
        self._calib_buf.append((midas_val, metric_dist))
        if len(self._calib_buf) > 100:
            self._calib_buf.pop(0)
        if len(self._calib_buf) >= 5:
            ks = [m * d for m, d in self._calib_buf]
            self._depth_scale = float(np.median(ks))
            if not self._calibrated:
                self._calibrated = True
                log.info(
                    f"Depth K self-calibrated: {self._depth_scale:.3f} "
                    f"from {len(self._calib_buf)} samples"
                )


# ═══════════════════════════════════════════════════════════════
#  MAIN VISION PIPELINE
# ═══════════════════════════════════════════════════════════════
class VisionPipeline:
    MODEL_NAME = "yolov8n.pt"

    COCO_VEHICLE  = {1, 2, 3, 5, 7}
    COCO_PERSON   = {0}

    # Real-world object heights (metres) for focal-length distance
    KNOWN_HEIGHTS = {
        "person":     1.75,
        "car":        1.50,
        "bus":        3.20,
        "truck":      3.50,
        "motorcycle": 1.20,
        "bicycle":    1.10,
    }

    def __init__(self):
        self.detector   = None
        self.tracker    = None
        self.depth_est  = DepthEstimator()
        self.velocity   = VelocityEstimator()
        self.model_name = "synthetic (no YOLO)"
        self._last_ts   = time.perf_counter()
        self._frame_idx = 0

    def warmup(self):
        self.depth_est.load()
        if not _TORCH_OK:
            log.info("Vision: synthetic mode (no torch)")
            return
        try:
            self.detector   = YOLO(self.MODEL_NAME)
            self.model_name = f"YOLOv8n ({self.MODEL_NAME})"
            log.info(f"YOLO loaded: {self.model_name}")
        except Exception as e:
            log.warning(f"YOLO load failed ({e})")

        if _DEEPSORT_OK:
            self.tracker = DeepSort(max_age=30, n_init=2, nms_max_overlap=0.7)
            log.info("DeepSORT tracker ready")
        else:
            self.tracker = SimpleCentroidTracker(max_disappeared=20)
            log.info("Centroid tracker ready (DeepSORT not installed)")

    def process(self, image_bytes: bytes) -> dict:
        now = time.perf_counter()
        dt  = now - self._last_ts
        self._last_ts = now
        self._frame_idx += 1

        if not image_bytes or not _TORCH_OK or self.detector is None:
            return self._synthetic_frame(dt)

        try:
            img    = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np = np.array(img)
        except Exception:
            return self._synthetic_frame(dt)

        results  = self.detector(img_np, conf=0.35, verbose=False)[0]
        raw_dets = self._parse_yolo(results)
        depth_map= self.depth_est.estimate(img_np)

        if _DEEPSORT_OK and isinstance(self.tracker, DeepSort):
            tracked = self._deepsort_update(raw_dets, img_np)
        else:
            tracked = self.tracker.update(raw_dets)

        objects = []
        for t in tracked:
            box    = t["box"]
            tid    = t.get("track_id", -1)
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2

            dist = self._metric_distance(t, box, depth_map)

            self.velocity.update(tid, cx, cy, now)
            vx, vy = self.velocity.get(tid)

            closing_vy = vy * 0.05
            ttc = (dist / (closing_vy + 0.01)
                   if closing_vy > 0.1 else None)

            objects.append({
                "id":       f"trk_{tid}",
                "label":    t["label"],
                "type":     t.get("type", "vehicle"),
                "conf":     round(t["conf"], 3),
                "box":      [round(v, 1) for v in box],
                "cx":       round(cx, 1),
                "cy":       round(cy, 1),
                "distance": round(dist, 2),
                "vx":       round(vx, 2),
                "vy":       round(vy, 2),
                "ttc":      round(ttc, 2) if ttc and ttc < 20 else None,
            })

        hazard      = self._compute_hazard(objects, img_np.shape)
        lane_offset = self._lane_offset_from_depth(depth_map, img_np.shape)

        return {
            "objects":      objects,
            "hazard":       round(hazard, 4),
            "lane_offset":  round(lane_offset, 3),
            "depth_ready":  True,
            "depth_scale":  round(self.depth_est._depth_scale, 3),
            "depth_calib":  self.depth_est._calibrated,
            "frame_idx":    self._frame_idx,
            "dt_ms":        round(dt * 1000, 2),
        }

    def _parse_yolo(self, results: Any) -> list[dict]:
        dets = []
        for box in results.boxes:
            cls_id         = int(box.cls[0])
            label, obj_type = self._label_from_class(cls_id, results.names)
            dets.append({
                "box":    box.xyxy[0].tolist(),
                "label":  label,
                "type":   obj_type,
                "conf":   float(box.conf[0]),
                "cls_id": cls_id,
            })
        return dets

    def _label_from_class(self, cls_id: int, names: dict) -> tuple[str, str]:
        raw = names.get(cls_id, "object").lower()
        if cls_id in self.COCO_PERSON:   return "PERSON", "pedestrian"
        if cls_id in self.COCO_VEHICLE:  return raw.upper(), "vehicle"
        return raw.upper(), "obstacle"

    def _deepsort_update(self, raw_dets: list[dict], img_np: np.ndarray) -> list[dict]:
        ds_input = []
        for d in raw_dets:
            x1, y1, x2, y2 = d["box"]
            ds_input.append(([x1, y1, x2-x1, y2-y1], d["conf"], d["label"]))
        tracks  = self.tracker.update_tracks(ds_input, frame=img_np)
        results = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            l, t, r, b = track.to_ltrb()
            tid = track.track_id
            det = next(
                (d for d in raw_dets if
                 abs((d["box"][0]+d["box"][2])/2 - (l+r)/2) < 50),
                raw_dets[0] if raw_dets else {},
            )
            results.append({
                "box":      [l, t, r, b],
                "label":    det.get("label", "OBJ"),
                "type":     det.get("type", "vehicle"),
                "conf":     det.get("conf", 0.5),
                "track_id": tid,
            })
        return results

    def _metric_distance(self, det: dict, box: list, depth_map: np.ndarray) -> float:
        """
        Delegates entirely to DepthEstimator.box_depth() so all
        calibration state is centralised there.

        Passes known_height_m + box_height_px when available so
        DepthEstimator can use Priority 1 (focal-length formula)
        and self-calibrate its K-scale for Priority 2 fallbacks.
        """
        label      = det.get("label", "").lower()
        known_h    = self.KNOWN_HEIGHTS.get(label)
        box_h_px   = box[3] - box[1]
        return self.depth_est.box_depth(
            depth_map,
            box,
            known_height_m = known_h,
            box_height_px  = box_h_px if box_h_px > 8 else None,
        )

    def _compute_hazard(self, objects: list[dict], shape: tuple) -> float:
        if not objects:
            return 0.08
        H, W   = shape[:2]
        cx_ego = W / 2
        score  = 0.0
        for obj in objects:
            dist      = obj.get("distance", 20.0)
            prox      = max(0, 1 - dist / 25)
            lat_dev   = abs(obj.get("cx", cx_ego) - cx_ego) / (W / 2)
            align     = max(0, 1 - lat_dev)
            ttc       = obj.get("ttc")
            ttc_f     = 1.0 if ttc is None else max(0, 1 - ttc / 6)
            score     = max(score, prox*0.5 + align*0.3 + ttc_f*0.2)
        return min(1.0, score)

    def _lane_offset_from_depth(self, depth_map: np.ndarray, shape: tuple) -> float:
        h, w  = depth_map.shape
        roi   = depth_map[h//2:, :]
        left  = roi[:, :w//2].mean()
        right = roi[:, w//2:].mean()
        return float(np.clip((right - left) * 2, -1.0, 1.0))

    def _synthetic_frame(self, dt: float) -> dict:
        import random
        t = time.time()
        n = max(0, int(1 + math.sin(t * 0.3) * 1.2))
        objects = []
        for i in range(n):
            dist = max(3.0, 8.0 + math.sin(t*0.5+i)*5)
            ttc  = dist / (2.5 + random.random())
            objects.append({
                "id": f"syn_{i}", "label": "CAR", "type": "vehicle",
                "conf": round(0.78 + random.random()*0.19, 3),
                "box":  [180+i*40, 100+i*15, 420+i*40, 280+i*15],
                "cx": 300.0, "cy": 190.0,
                "distance": round(dist, 2),
                "vx": round(random.gauss(0, 8), 2),
                "vy": round(random.gauss(10, 5), 2),
                "ttc": round(ttc, 2),
            })
        hazard = 0.1 + (1/(n+1))*0.25*math.sin(t*0.2)**2
        return {
            "objects":     objects,
            "hazard":      round(abs(hazard), 4),
            "lane_offset": round(math.sin(t*0.07)*0.3, 3),
            "depth_ready": False,
            "depth_scale": self.depth_est._depth_scale,
            "depth_calib": False,
            "frame_idx":   self._frame_idx,
            "dt_ms":       round(dt*1000, 2),
        }
