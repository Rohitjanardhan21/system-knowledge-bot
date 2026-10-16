import ast
import unittest
from pathlib import Path

ROOT = Path.cwd()

class TestApprovalBoundaryBaseline(unittest.TestCase):
    def test_executor_has_no_trusted_approval_parameter(self):
        path = ROOT / "backend" / "action_executor.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))

        matches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and node.name == "ActionExecutor"
        ]
        self.assertTrue(matches, "ActionExecutor class not found")

        execute = next(
            (
                node for node in matches[0].body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "execute"
            ),
            None,
        )
        self.assertIsNotNone(execute, "ActionExecutor.execute not found")

        print("\nActionExecutor.execute parameters:")
        print([arg.arg for arg in execute.args.args])

        print("This test is a baseline inspection, not proof of enforcement.")
        print("No actions or processes are executed.")

    def test_auto_remediation_allowlist_is_explicit(self):
        path = ROOT / "backend" / "core" / "actions" / "action_executor.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))

        allowlist = next(
            (
                node for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "AUTONOMOUS_ALLOWED_ACTIONS"
                    for target in node.targets
                )
            ),
            None,
        )
        self.assertIsNotNone(allowlist, "Autonomous allowlist not found")
        print("\nExisting autonomous allowlist assignment:")
        print(ast.unparse(allowlist))

    def test_agent_termination_requires_trusted_approval_at_gate(self):
        path = ROOT / "agent.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        branch = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "command_type"
                and any(
                    isinstance(value, ast.Constant)
                    and value.value == "kill_high_cpu"
                    for value in node.test.comparators
                )
            ),
            None,
        )
        self.assertIsNotNone(branch, "Agent process-remediation branch not found")

        payload_fields = [
            node.args[0].value
            for node in ast.walk(branch)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "payload"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ]
        trusted_approval_call = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "consume_process_approval"
            for node in ast.walk(branch)
        )
        print("\nAgent termination gate excerpt:")
        print(ast.unparse(branch))
        self.assertIn("approval_id", payload_fields)
        self.assertTrue(trusted_approval_call)
        self.assertNotIn("confirm", payload_fields)

        print("\nNo processes are started or terminated.")

if __name__ == "__main__":
    unittest.main(verbosity=2)
