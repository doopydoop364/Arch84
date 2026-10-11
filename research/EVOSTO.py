"""Read-only TI-84 Evo storage API probe, independent of Arch84.

This program never writes or deletes calculator variables. It only attempts
to open an unlikely filename for reading and inspects known APIs.
"""
import sys

MISSING = "__evo_storage_probe_missing_84__"


def status(mod, name):
    return int(callable(getattr(mod, name, None))) if mod is not None else 0


def read_open_probe():
    fn = globals().get("open")
    if fn is None:
        try:
            fn = open
        except NameError:
            return "absent"
    try:
        handle = fn(MISSING, "rb")
        if handle is None:
            return "returned_none"
        try:
            handle.close()
        except Exception:
            pass
        return "unexpected_existing_file"
    except Exception as e:
        return type(e).__name__


def probe(ti=None):
    if ti is None:
        try:
            import ti_system as ti
        except ImportError:
            ti = None
    rows = [("runtime", getattr(sys.implementation, "name", "unknown")),
            ("ti_system", int(ti is not None)),
            ("store_list_api", status(ti, "store_list")),
            ("recall_list_api", status(ti, "recall_list")),
            ("open_missing_read", read_open_probe())]
    for name in ("store_string", "recall_string", "get_var", "get_storage_info"):
        rows.append((name + "_api", status(ti, name)))
    return rows


def main():
    for key, value in probe():
        print("EVO_STORAGE " + key + "=" + str(value))


if __name__ == "__main__" or sys.implementation.name == "tipython":
    main()
