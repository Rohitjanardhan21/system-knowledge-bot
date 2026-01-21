from timeline.replay import replay

def run_replay(args):
    if not args:
        print("Usage: sysbot replay <date-prefix>")
        print("Example: sysbot replay 2026-01-19")
        return

    replay(args[0])
