import os
import ast
import traceback

TARGET_PATH = "data/commands/pokemon/pokemon_names.csv"
ROOT_DIR = os.getcwd()

ghost_uses = []
direct_accesses = []

class AccessFinder(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath

    def visit_Call(self, node):
        # Check for file access functions
        if isinstance(node.func, ast.Name) and node.func.id in {"open"}:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and TARGET_PATH in str(arg.value):
                    direct_accesses.append((self.filepath, node.lineno, "open()"))
        elif isinstance(node.func, ast.Attribute):
            fname = node.func.attr
            if fname in {"read_csv", "exists", "loadtxt", "read"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and TARGET_PATH in str(arg.value):
                        call_type = f"{node.func.value.id}.{fname}" if hasattr(node.func.value, 'id') else fname
                        direct_accesses.append((self.filepath, node.lineno, call_type))

        self.generic_visit(node)

def scan_for_accesses():
    for root, _, files in os.walk(ROOT_DIR):
        for file in files:
            if file.endswith(".py"):
                fpath = os.path.join(root, file)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if TARGET_PATH in content:
                        tree = ast.parse(content, filename=fpath)
                        AccessFinder(fpath).visit(tree)
                        # Detect ghost code usage
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if TARGET_PATH in line and "open" not in line and "read_csv" not in line:
                                ghost_uses.append((fpath, i + 1, line.strip()))
                except Exception as e:
                    print(f"Failed to scan {fpath}: {e}")

def print_results():
    if direct_accesses:
        print("\n🔍 Direct file accesses found:")
        for file, line, method in direct_accesses:
            print(f" - {file}:{line} using {method}")
    else:
        print("✅ No direct access found to the missing file.")

    if ghost_uses:
        print("\n👻 Potential ghost references (not used directly):")
        for file, line, code in ghost_uses:
            print(f" - {file}:{line} → {code}")

if __name__ == "__main__":
    print("🔎 Deep scanning for causes of missing file errors...")
    scan_for_accesses()
    print_results()
