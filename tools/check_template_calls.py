"""Flag OWL template expressions that call a method the component lacks.

OWL resolves a bare identifier in a template against the component, so a typo
or a renamed method fails at render, not at load. node --check proves the JS
parses; it cannot know the template opposite it calls money() when the class
defines formatMoney().

Pairs each .xml with the .js beside it and compares calls to methods, getters
and assigned properties. Over-approximates what the component provides, for
the same reason as the undefined-name sweep: a checker that cries wolf gets
ignored.
"""
import re
import sys
import xml.etree.ElementTree as ET

EXPR_ATTRS = ("t-esc", "t-out", "t-if", "t-elif", "t-value", "t-foreach", "t-key")
EXPR_PREFIXES = ("t-att-", "t-attf-", "t-on-")

# Identifiers that are language, not component surface.
LANGUAGE = {
    "this", "true", "false", "null", "undefined", "new", "typeof", "void",
    "return", "if", "else", "and", "or", "not", "in", "of", "function",
    "String", "Number", "Boolean", "Array", "Object", "Math", "JSON", "Date",
    "parseInt", "parseFloat", "isNaN",
    # CSS functions appear inside t-att-style / t-att-stroke expressions and
    # are not component methods.
    "var", "calc", "rgb", "rgba", "hsl", "hsla", "url", "translate", "rotate",
    "scale", "clamp", "minmax", "repeat",
}

CALL = re.compile(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(")


def template_facts(path):
    tree = ET.parse(path)
    calls, bound = set(), set()
    for node in tree.iter():
        for attr, value in node.attrib.items():
            if attr in ("t-set", "t-as"):
                bound.add(value.strip())
                continue
            if attr in EXPR_ATTRS or any(attr.startswith(p) for p in EXPR_PREFIXES):
                calls.update(CALL.findall(value))
        # OWL exposes <loop>_index and <loop>_value alongside t-as.
        if "t-as" in node.attrib:
            name = node.attrib["t-as"].strip()
            bound.update({f"{name}_index", f"{name}_value", f"{name}_first", f"{name}_last"})
    return calls, bound


def component_surface(path):
    source = open(path).read()
    names = set(re.findall(r"^\s{4}(?:async\s+)?(?:get\s+)?([a-zA-Z_$][\w$]*)\s*\(", source, re.M))
    names |= set(re.findall(r"^\s{4}get\s+([a-zA-Z_$][\w$]*)", source, re.M))
    names |= set(re.findall(r"this\.([a-zA-Z_$][\w$]*)\s*=", source))
    return names


failed = False
for xml_path in sys.argv[1:]:
    js_path = xml_path[:-4] + ".js"
    try:
        surface = component_surface(js_path)
    except FileNotFoundError:
        continue
    calls, bound = template_facts(xml_path)
    for name in sorted(calls - surface - bound - LANGUAGE):
        print(f"{xml_path}: calls {name}() — not found in {js_path.split('/')[-1]}")
        failed = True
sys.exit(1 if failed else 0)
