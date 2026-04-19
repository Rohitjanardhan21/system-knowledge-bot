import cv2
import numpy as np

def detect_obstacle(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # simple heuristic: strong contours ahead
    edge_density = np.sum(edges) / edges.size

    if edge_density > 0.15:
        return {
            "object": "road_anomaly",
            "confidence": 0.6
        }

    return None
