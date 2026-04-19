# ---------------------------------------------------------
# 👁️ YOLO PERCEPTION ENGINE (REAL DETECTION)
# ---------------------------------------------------------

from ultralytics import YOLO
import numpy as np

# load lightweight model (you can replace with custom later)
model = YOLO("yolov8n.pt")

# classes we care about (extend later with custom pothole model)
TARGET_CLASSES = ["car", "person", "truck", "motorbike"]  # placeholder

def detect_obstacle_yolo(frame):

    try:
        results = model(frame, verbose=False)[0]

        detections = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])

            label = model.names[cls_id]

            if conf < 0.4:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                "object": label,
                "confidence": round(conf, 2),
                "bbox": [x1, y1, x2, y2]
            })

        # simple logic: return closest / most confident
        if detections:
            return max(detections, key=lambda x: x["confidence"])

    except Exception:
        return None

    return None
