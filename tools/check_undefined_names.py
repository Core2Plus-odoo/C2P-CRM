"""Flag names that are read but never bound anywhere in a module.

Deliberately over-approximates what counts as "defined" -- every assignment,
import, parameter, comprehension target and except-alias anywhere in the file.
That misses shadowing and scope subtleties, which is fine: the goal is to catch
a name that appears from nowhere, like a defaultdict that was used four times
and imported zero.
"""
import ast
import builtins
import sys

SAFE = set(dir(builtins)) | {"self", "cls", "__name__", "__file__", "__doc__"}


def defined_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # Lambdas have no name but do bind parameters.
            if not isinstance(node, ast.Lambda):
                names.add(node.name)
            args = node.args
            for arg in list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs):
                names.add(arg.arg)
            if args.vararg:
                names.add(args.vararg.arg)
            if args.kwarg:
                names.add(args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global):
            names.update(node.names)
    return names


def check(path):
    tree = ast.parse(open(path).read(), path)
    known = defined_names(tree) | SAFE
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in known:
                problems.append((node.lineno, node.id))
    return sorted(set(problems))


failed = False
for path in sys.argv[1:]:
    for line, name in check(path):
        print(f"{path}:{line}: undefined name {name!r}")
        failed = True
sys.exit(1 if failed else 0)
