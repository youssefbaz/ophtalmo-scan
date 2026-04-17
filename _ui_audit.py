"""Static UI audit — find onclick handlers without matching functions, and api() calls without matching routes."""
import os, re, glob, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
JS_FILES = sorted(glob.glob(os.path.join(ROOT, "static", "js", "*.js")))
HTML_FILES = sorted(glob.glob(os.path.join(ROOT, "templates", "*.html")))
ROUTE_FILES = sorted(glob.glob(os.path.join(ROOT, "routes", "*.py"))) + [os.path.join(ROOT, "app.py")]

# ─────────────────────── Collect function definitions ──────────────────────────
defined_funcs = set()
fn_patterns = [
    re.compile(r"\bfunction\s+([a-zA-Z_$][\w$]*)\s*\("),
    re.compile(r"\basync\s+function\s+([a-zA-Z_$][\w$]*)\s*\("),
    re.compile(r"^\s*(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()"),
    re.compile(r"^\s*(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:async\s*)?[a-zA-Z_$][\w$]*\s*=>"),
    re.compile(r"^\s*window\.([a-zA-Z_$][\w$]*)\s*="),
]
all_js = ""
for f in JS_FILES:
    with open(f, encoding="utf-8") as fh:
        all_js += "\n" + fh.read()
for line in all_js.split("\n"):
    for p in fn_patterns:
        for m in p.finditer(line):
            defined_funcs.add(m.group(1))

# Browser globals + common host-provided functions that are fine to call
BROWSER_GLOBALS = {
    "alert", "confirm", "prompt", "event", "this", "window", "document",
    "navigator", "console", "parseInt", "parseFloat", "setTimeout",
    "setInterval", "clearTimeout", "clearInterval", "Math", "Date",
    "Object", "Array", "String", "Number", "JSON", "Boolean", "RegExp",
    "encodeURIComponent", "decodeURIComponent", "fetch", "URL",
    "URLSearchParams", "FormData", "Promise",
}

# ─────────────────────── Collect onclick handlers ──────────────────────────────
all_content = all_js
for f in HTML_FILES:
    with open(f, encoding="utf-8") as fh:
        all_content += "\n" + fh.read()

# onclick="funcName(...)" or onchange/oninput/onsubmit etc.
handler_attr = re.compile(
    r'\bon(?:click|change|input|submit|keydown|keyup|keypress|blur|focus|mouseenter|mouseleave|mouseover|mouseout)\s*=\s*["\']([^"\']+)["\']'
)
called_funcs = set()  # func name -> set of contexts
handler_locations = {}
for f in JS_FILES + HTML_FILES:
    try:
        with open(f, encoding="utf-8") as fh:
            content = fh.read()
    except Exception:
        continue
    for lineno, line in enumerate(content.split("\n"), 1):
        for m in handler_attr.finditer(line):
            body = m.group(1)
            # Extract identifiers followed by (
            for fn in re.findall(r"\b([a-zA-Z_$][\w$]*)\s*\(", body):
                if fn in BROWSER_GLOBALS:
                    continue
                called_funcs.add(fn)
                handler_locations.setdefault(fn, []).append((os.path.relpath(f, ROOT), lineno))

missing = sorted(f for f in called_funcs if f not in defined_funcs)

print("=" * 72)
print("HANDLERS CALLED BUT NOT DEFINED")
print("=" * 72)
if not missing:
    print("  (none) — all handler calls resolve to a defined JS function")
else:
    for fn in missing:
        locs = handler_locations.get(fn, [])
        print(f"  {fn}  →  {locs[0][0]}:{locs[0][1]}" + (f"  (+{len(locs)-1} more)" if len(locs) > 1 else ""))

# ─────────────────────── Collect api() call paths ──────────────────────────────
api_calls = set()
api_call_locations = {}
api_pattern = re.compile(r"""\bapi\s*\(\s*(['"`])([^'"`]+)\1""")
for f in JS_FILES:
    with open(f, encoding="utf-8") as fh:
        content = fh.read()
    for lineno, line in enumerate(content.split("\n"), 1):
        for m in api_pattern.finditer(line):
            path = m.group(2)
            api_calls.add(path)
            api_call_locations.setdefault(path, []).append((os.path.relpath(f, ROOT), lineno))

# ─────────────────────── Collect Flask routes ──────────────────────────────────
route_patterns = [
    re.compile(r"""@\w+\.route\s*\(\s*(['"])([^'"]+)\1"""),
    re.compile(r"""@bp\.route\s*\(\s*(['"])([^'"]+)\1"""),
    re.compile(r"""@app\.route\s*\(\s*(['"])([^'"]+)\1"""),
]
routes = set()
for f in ROUTE_FILES:
    try:
        with open(f, encoding="utf-8") as fh:
            content = fh.read()
    except Exception:
        continue
    for p in route_patterns:
        for m in p.finditer(content):
            routes.add(m.group(2))

# Normalize a path like /api/patients/abc123/ordonnances → /api/patients/<pid>/ordonnances
def normalize(path: str) -> str:
    # Strip template-string expressions ${...}
    path = re.sub(r"\$\{[^}]+\}", "<var>", path)
    # Strip query strings
    path = path.split("?", 1)[0]
    return path

def route_to_regex(route: str) -> re.Pattern:
    # Convert Flask route with <foo> or <int:bar> placeholders to a regex
    pat = re.sub(r"<[^>]+>", r"[^/]+", route)
    return re.compile(r"^" + pat + r"$")

route_regexes = [(r, route_to_regex(r)) for r in routes]

def matches_any_route(path: str) -> bool:
    if "<var>" in path:
        # Replace <var> with a permissive match
        path_re = re.compile(r"^" + path.replace("<var>", "[^/]+") + r"$")
        for r in routes:
            if path_re.match(r):
                return True
        # Also try direct regex matching
        for r, rx in route_regexes:
            if rx.match(path.replace("<var>", "X")):
                return True
        return False
    for r, rx in route_regexes:
        if rx.match(path):
            return True
    return False

unresolved = sorted(p for p in api_calls if not matches_any_route(normalize(p)))

print()
print("=" * 72)
print("FRONT-END api() CALLS THAT DON'T MATCH ANY BACKEND ROUTE")
print("=" * 72)
if not unresolved:
    print(f"  (none) — all {len(api_calls)} distinct api() paths resolve to a route")
else:
    for p in unresolved:
        locs = api_call_locations.get(p, [])
        print(f"  {p}")
        print(f"    → {locs[0][0]}:{locs[0][1]}" + (f"  (+{len(locs)-1} more)" if len(locs) > 1 else ""))

print()
print("=" * 72)
print(f"SUMMARY: {len(defined_funcs)} JS funcs defined, {len(called_funcs)} referenced from handlers, "
      f"{len(missing)} unresolved. {len(api_calls)} distinct api() paths, {len(routes)} routes defined, "
      f"{len(unresolved)} unresolved.")
print("=" * 72)
