"""Formula builder: turn ``[column] * 2`` style expressions into DuckDB SQL.

The grammar is the same as the browser formula builder: numbers, ``[column]``
references, ``+ - * / %`` and parentheses. Column values are read with
TRY_CAST so text that is not a number becomes NULL instead of an error.
"""

import re

from .util import UserError, qi

_TOKEN_RE = re.compile(
    r"\s*(?:(\d+(?:\.\d*)?|\.\d+)([eE][+-]?\d+)?|(@\d+)|([()+\-*/%]))"
)


def formula_to_sql(expression, columns):
    refs = []

    def sub(m):
        name = m.group(1).strip()
        if name not in columns:
            raise UserError("Unknown column reference: " + name)
        refs.append(name)
        return "@%d" % (len(refs) - 1)

    src = re.sub(r"\[([^\]]+)\]", sub, expression)
    toks, pos = [], 0
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = _TOKEN_RE.match(src, pos)
        if not m or m.end() == pos:
            raise UserError("Invalid formula near: " + src[pos:pos + 12])
        pos = m.end()
        if m.group(1) is not None:
            toks.append(("num", float(m.group(1) + (m.group(2) or ""))))
        elif m.group(3):
            toks.append(("ref", refs[int(m.group(3)[1:])]))
        else:
            toks.append((m.group(4), None))
    i = 0

    def peek():
        return toks[i][0] if i < len(toks) else None

    def atom():
        nonlocal i
        if i >= len(toks):
            raise UserError("Unexpected end of formula.")
        t, v = toks[i]
        i += 1
        if t == "num":
            return "CAST(%r AS DOUBLE)" % v
        if t == "ref":
            return "TRY_CAST(%s AS DOUBLE)" % qi(v)
        if t in ("-", "+"):
            inner = atom()
            return "(-(%s))" % inner if t == "-" else inner
        if t == "(":
            v2 = expr()
            if peek() != ")":
                raise UserError("Missing closing parenthesis.")
            i += 1
            return "(%s)" % v2
        raise UserError("Expected a number, column reference or parenthesis.")

    def term():
        nonlocal i
        v = atom()
        while peek() in ("*", "/", "%"):
            op = toks[i][0]
            i += 1
            n = atom()
            if op == "*":
                v = "(%s * %s)" % (v, n)
            elif op == "/":
                v = "(%s / NULLIF(%s, 0))" % (v, n)
            else:
                v = "fmod(%s, NULLIF(%s, 0))" % (v, n)
        return v

    def expr():
        nonlocal i
        v = term()
        while peek() in ("+", "-"):
            op = toks[i][0]
            i += 1
            v = "(%s %s %s)" % (v, op, term())
        return v

    if not toks:
        raise UserError("Enter an expression.")
    out = expr()
    if i != len(toks):
        raise UserError("Unexpected token in formula.")
    return out
