"""Optional, bounded TI-84 Evo scratch-list write/read test.

Importing this file does nothing. In the Python app call preview() first.
Only run("WRITE_Z84P") writes a new list named Z84P. It never deletes it.
If Z84P already exists, it refuses to write. See docs/evo-memory-research.md.
"""

NAME = "Z84P"
TOKEN = "WRITE_Z84P"
COUNT = 16


def _exists(ti):
    try:
        value = ti.recall_list(NAME)
    except NameError:
        # The project emulator uses NameError for a missing list. Verify the
        # name is absent with the desktop directory query before device use.
        return False
    except Exception:
        raise RuntimeError("cannot establish whether scratch name is free")
    return value is not None


def preview(ti=None):
    if ti is None:
        import ti_system as ti
    exists = _exists(ti)
    print("EVO_SCRATCH name=" + NAME)
    print("EVO_SCRATCH exists=" + str(int(exists)))
    print("EVO_SCRATCH elements=" + str(COUNT))
    print("EVO_SCRATCH write_requires=" + TOKEN)
    return not exists


def run(token=None, ti=None):
    if token != TOKEN:
        print("EVO_SCRATCH skipped=explicit_opt_in_required")
        return False
    if ti is None:
        import ti_system as ti
    if _exists(ti):
        print("EVO_SCRATCH stopped=name_collision")
        return False
    values = [i * 1048576.0 + 0.5 for i in range(COUNT)]
    # One 16-element list only; no retries or capacity-filling loop.
    ti.store_list(NAME, values)
    actual = ti.recall_list(NAME)
    ok = actual is not None and len(actual) == COUNT
    if ok:
        for i in range(COUNT):
            if actual[i] != values[i]:
                ok = False
                break
    print("EVO_SCRATCH verified=" + str(int(ok)))
    print("EVO_SCRATCH retained=" + NAME)
    return ok
