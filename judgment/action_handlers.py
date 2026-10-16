from __future__ import annotations


def handle_reduce_memory_pressure(dry_run=True):
    if dry_run:
        return {
            "status": "simulated",
            "result": "memory-pressure-reduction-simulated",
            "modified": False,
        }

    return {
        "status": "blocked",
        "result": "real-execution-disabled",
        "modified": False,
    }


def handle_free_disk_space(dry_run=True):
    if dry_run:
        return {
            "status": "simulated",
            "result": "disk-cleanup-simulated",
            "modified": False,
        }

    return {
        "status": "blocked",
        "result": "real-execution-disabled",
        "modified": False,
    }


def handle_avoid_heavy_workloads(dry_run=True):
    if dry_run:
        return {
            "status": "simulated",
            "result": "workload-avoidance-simulated",
            "modified": False,
        }

    return {
        "status": "blocked",
        "result": "real-execution-disabled",
        "modified": False,
    }


ACTION_HANDLERS = {
    "reduce-memory-pressure": handle_reduce_memory_pressure,
    "free-disk-space": handle_free_disk_space,
    "avoid-heavy-workloads": handle_avoid_heavy_workloads,
}


def execute_action_handler(action, dry_run=True):
    handler = ACTION_HANDLERS.get(action)

    if handler is None:
        return {
            "status": "rejected",
            "result": "unknown-action",
            "modified": False,
        }

    return handler(dry_run=dry_run)
