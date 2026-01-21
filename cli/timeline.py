from timeline.extractor import extract_posture_timeline
from timeline.summarizer import summarize_timeline

def show_timeline():
    timeline = extract_posture_timeline()
    summary = summarize_timeline(timeline)
    print(summary)
