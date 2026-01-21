import sys

from cli.audit import show_audit
from cli.can_run import can_run
from cli.timeline import show_timeline
from cli.replay import run_replay

def main():
    if len(sys.argv) < 2:
        print("""
Usage: sysbot <command> [args]

Available commands:
  audit                 Show audit & suppressed decisions
  can-run <job>          Check if system can handle a workload
  timeline               Show posture changes over time
  replay <date-prefix>   Replay system behavior (YYYY-MM-DD)
""")
        return

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "audit":
        show_audit()

    elif command == "can-run":
        if not args:
            print("Usage: sysbot can-run <job>")
            return
        can_run(args[0])

    elif command == "timeline":
        show_timeline()

    elif command == "replay":
        run_replay(args)

    else:
        print(f"Unknown command: {command}")
        print("Run `sysbot` for help.")

if __name__ == "__main__":
    main()
