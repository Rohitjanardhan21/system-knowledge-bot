import ast
from pathlib import Path

path = Path("backend/action_executor.py")
source = path.read_text(encoding="utf-8-sig")
tree = ast.parse(source)

execute = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef)
    and node.name == "ActionExecutor"
    for node in node.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "execute"
)

names = {
    node.id for node in ast.walk(execute)
    if isinstance(node, ast.Name)
}

print("=== EXECUTION AUTHORIZATION BASELINE ===")
print("Function: ActionExecutor.execute")
print("Approval-related fields referenced:")
for field in ("approved", "approval_id", "requires_confirmation", "auto_execute"):
    print(f"  {field}: {field in names}")

calls = []
for node in ast.walk(execute):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "_execute_action":
            calls.append(node.lineno)

print("Execution-dispatch call lines:", sorted(calls))
print("No processes were started or terminated.")
print("RESULT: BASELINE CAPTURED")
