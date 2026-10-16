import ast
from pathlib import Path


def test_remote_command_reachability_safety_guards():
    repo_root = Path(__file__).resolve().parents[1]
    service_path = repo_root / "backend" / "core" / "devices" / "command_service.py"
    agent_path = repo_root / "agent.py"

    service_tree = ast.parse(
        service_path.read_text(encoding="utf-8-sig", errors="replace")
    )

    allowed_value = None

    for node in service_tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue

        if any(
            isinstance(target, ast.Name)
            and target.id == "ALLOWED_COMMANDS"
            for target in targets
        ):
            value_node = node.value
            is_frozenset_call = (
                isinstance(value_node, ast.Call)
                and isinstance(value_node.func, ast.Name)
                and value_node.func.id == "frozenset"
                and len(value_node.args) == 1
                and not value_node.keywords
            )
            if is_frozenset_call:
                value_node = value_node.args[0]

            allowed_value = ast.literal_eval(value_node)
            if is_frozenset_call:
                allowed_value = frozenset(allowed_value)
            break

    assert allowed_value is not None, "ALLOWED_COMMANDS was not found"

    if isinstance(allowed_value, dict):
        allowed_commands = set(allowed_value)
    else:
        allowed_commands = set(allowed_value)

    assert "drop_caches" not in allowed_commands
    assert "clear_logs" not in allowed_commands

    agent_source = agent_path.read_text(
        encoding="utf-8-sig", errors="replace"
    )

    assert "trusted_approval_not_implemented" in agent_source
    assert "trusted_log_path_policy_not_implemented" in agent_source
