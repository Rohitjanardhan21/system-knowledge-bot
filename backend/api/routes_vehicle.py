from fastapi import APIRouter, UploadFile, File
from backend.vehicle_system.perception.vision_engine import VisionEngine
from backend.vehicle_system.intelligence.multimodal_engine import MultimodalEngine

router = APIRouter()

# Initialize ONCE
vision_engine = VisionEngine()
multimodal_engine = MultimodalEngine()


@router.post("/analyze-camera")
async def analyze_camera(file: UploadFile = File(...)):
    image_bytes = await file.read()

    # Vision
    detections = vision_engine.process(image_bytes)

    # Multimodal reasoning
    result = multimodal_engine.process(detections)

    return result
