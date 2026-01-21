from cli.can_run import can_run
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: sysbot preflight <workload>")
        return

    can_run(sys.argv[1])

if __name__ == "__main__":
    main()
