from judgment.engine import evaluate
from judgment.posture import resolve_posture
from judgment.suppression import should_speak
from output.renderer import render

def run(snapshot, baseline, user_asked=False):
    judgments = evaluate(snapshot, baseline)

    posture = resolve_posture(judgments)

    for j in judgments:
        if should_speak(j, user_asked):
            print(render(j, posture))
