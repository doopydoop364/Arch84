# A84C9: test [ expr (Arch84 module, lazily loaded). Registers itself into COMMANDS.
# Conditions for scripts:  test -e|-f|-d PATH   test -z|-n STR   test A = B | != | -eq -ne -lt -le -gt -ge
# with ! in front; `[ ... ]` is the same with a closing ]. expr A + B (also - * / %).
from A84CD import COMMANDS


def num(s):
    try:
        return int(s)
    except ValueError:
        raise ValueError("integer expression expected: " + s)


def evaluate(sh, a):
    if a and a[0] == "!":
        return not evaluate(sh, a[1:])
    n = len(a)
    if n == 0:
        return False
    if n == 1:
        return a[0] != ""
    if n == 2:
        op = a[0]
        if op == "-z":
            return a[1] == ""
        if op == "-n":
            return a[1] != ""
        p = sh.resolve(a[1])
        if op == "-e":
            return sh.vfs.exists(p)
        if op == "-f":
            return sh.vfs.isfile(p)
        if op == "-d":
            return sh.vfs.isdir(p)
        raise ValueError("unknown operator: " + op)
    if n == 3:
        x, op, y = a
        if op == "=" or op == "==":
            return x == y
        if op == "!=":
            return x != y
        x = num(x)
        y = num(y)
        if op == "-eq":
            return x == y
        if op == "-ne":
            return x != y
        if op == "-lt":
            return x < y
        if op == "-le":
            return x <= y
        if op == "-gt":
            return x > y
        if op == "-ge":
            return x >= y
    raise ValueError("unknown condition")


def cmd_test(sh, args):
    try:
        return 0 if evaluate(sh, args) else 1
    except ValueError as e:
        sh.err("test: " + str(e))
        return 2


def cmd_bracket(sh, args):
    if not args or args[-1] != "]":
        sh.err("[: missing ]")
        return 2
    return cmd_test(sh, args[:-1])


def cmd_expr(sh, args):
    try:
        if len(args) == 1:
            v = args[0]
        elif len(args) == 3:
            x = num(args[0])
            y = num(args[2])
            op = args[1]
            if op == "+":
                v = x + y
            elif op == "-":
                v = x - y
            elif op == "*":
                v = x * y
            elif op == "/" or op == "%":
                if y == 0:
                    sh.err("expr: division by zero")
                    return 2
                v = x // y if op == "/" else x % y
            else:
                raise ValueError("unknown operator: " + op)
        else:
            sh.err("usage: expr A + B   (+ - * / %, integers)")
            return 2
    except ValueError as e:
        sh.err("expr: " + str(e))
        return 2
    sh.out(str(v) + "\n")
    return 1 if str(v) in ("0", "") else 0


COMMANDS.update({"test": cmd_test, "[": cmd_bracket, "expr": cmd_expr})
