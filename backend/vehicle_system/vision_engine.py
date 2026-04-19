# ---------------------------------------------------------
# 👁️ VISION ENGINE (COGNITIVE PERCEPTION - TRACKING + TTI)
# ---------------------------------------------------------

import time
import cv2
from ultralytics import YOLO
from collections import deque
from math import sqrt


class VisionEngine:

    def __init__(self, model_path="yolov8n.pt", target_fps=10):
        self.model = YOLO(model_path)

        self.last_inference_time = 0
        self.last_frame_time = 0
        self.target_delay = 1.0 / target_fps

        # tracking memory
        self.prev_objects = []
        self.track_id_counter = 0

        # temporal buffer
        self.history = deque(maxlen=10)

        self.relevant_classes = {
            "person", "car", "truck", "bus",
            "motorbike", "bicycle"
        }

    # -----------------------------------------------------
    # MAIN DETECTION + TRACKING
    # -----------------------------------------------------
    def detect(self, frame):

        current_time = time.time()
        if current_time - self.last_frame_time < self.target_delay:
            return {
                "objects": [],
                "latency": 0,
                "count": 0,
                "hazard_score": 0
            }

        self.last_frame_time = current_time
        start = time.time()

        try:
            results = self.model(frame, verbose=False)[0]
        except Exception:
            return {"objects": [], "latency": 0, "count": 0, "hazard_score": 0}

        detections = []
        frame_width = frame.shape[1]

        for box in results.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            if conf < 0.4:
                continue

            label = self.model.names[cls]
            if label not in self.relevant_classes:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            distance = self.estimate_distance([x1, y1, x2, y2], frame_width)
            risk = self.compute_risk(label, distance)

            detections.append({
                "label": label,
                "confidence": round(conf, 2),
                "bbox": [x1, y1, x2, y2],
                "center": (cx, cy),
                "distance": distance,
                "risk": risk
            })

        # 🔥 TRACKING
        tracked = self.assign_ids(detections)

        # 🔥 VELOCITY
        velocities = self.compute_velocity(tracked)

        # 🔥 ENRICH OBJECTS
        enriched = []
        for obj in tracked:
            v = velocities.get(obj["id"], 0)

            tti = None
            if v > 0:
                tti = round(max(0.1, obj["distance"] / (v + 1e-5)), 2)

            enriched.append({
                **obj,
                "velocity": round(v, 2),
                "time_to_impact": tti
            })

        self.history.append(enriched)

        self.last_inference_time = time.time() - start

        return {
            "objects": enriched,
            "latency": round(self.last_inference_time, 3),
            "count": len(enriched),
            "hazard_score": self.compute_hazard_score(enriched)
        }

    # -----------------------------------------------------
    # TRACKING (ID MATCHING)
    # -----------------------------------------------------
    def assign_ids(self, detections):
        updated = []

        for det in detections:
            cx, cy = det["center"]

            assigned = False

            for prev in self.prev_objects:
                px, py = prev["center"]

                dist = sqrt((cx - px)**2 + (cy - py)**2)

                if dist < 50:
                    det["id"] = prev["id"]
                    assigned = True
                    break

            if not assigned:
                det["id"] = self.track_id_counter
                self.track_id_counter += 1

            updated.append(det)

        self.prev_objects = updated
        return updated

    # -----------------------------------------------------
    # VELOCITY ESTIMATION
    # -----------------------------------------------------
    def compute_velocity(self, objects):
        velocities = {}

        if len(self.history) < 1:
            return velocities

        prev_frame = self.history[-1]

        for obj in objects:
            for prev in prev_frame:
                if obj["id"] == prev["id"]:
                    dx = obj["center"][0] - prev["center"][0]
                    dy = obj["center"][1] - prev["center"][1]

                    v = sqrt(dx**2 + dy**2)
                    velocities[obj["id"]] = v

        return velocities

    # -----------------------------------------------------
    # DISTANCE
    # -----------------------------------------------------
    def estimate_distance(self, bbox, frame_width):

        width = bbox[2] - bbox[0]
        if width <= 0:
            return 50

        relative_size = width / frame_width
        distance = max(1, 1 / (relative_size + 1e-5)) * 4

        return round(distance, 2)

    # -----------------------------------------------------
    # RISK
    # -----------------------------------------------------
    def compute_risk(self, label, distance):

        base_risk = {
            "person": 1.0,
            "motorbike": 0.9,
            "bicycle": 0.8,
            "car": 0.7,
            "truck": 0.9,
            "bus": 0.85
        }.get(label, 0.5)

        risk = base_risk * (1 / (distance + 1e-5)) * 10
        return round(min(risk, 1.0), 2)

    # -----------------------------------------------------
    # HAZARD (SMARTER)
    # -----------------------------------------------------
    def compute_hazard_score(self, detections):

        if not detections:
            return 0

        # prioritize closest + fastest
        weighted = []

        for d in detections:
            score = d["risk"]

            if d.get("time_to_impact") and d["time_to_impact"] < 3:
                score *= 1.5

            weighted.append(score)

        return round(min(1.0, sum(weighted) / len(weighted)), 2)


# ---------------------------------------------------------
# GLOBAL INSTANCE
# ---------------------------------------------------------
vision_engine = VisionEngine()


def detect_objects(frame):
    return vision_engine.detect(frame)


def estimate_distance(bbox, frame_width=640):
    return vision_engine.estimate_distance(bbox, frame_width)
