"""Read-only Evo Python probe for one archived scratch list, Z84A."""
import gc
import sys
import ti_system


def main():
    gc.collect()
    before = gc.mem_free() if hasattr(gc, "mem_free") else None
    print("EVO_COLD before=" + str(before))
    try:
        value = ti_system.recall_list("Z84A")
        print("EVO_COLD recall=ok")
        print("EVO_COLD count=" + str(len(value) if value is not None else -1))
        if value is not None and len(value) == 8:
            print("EVO_COLD first=" + str(value[0]))
            print("EVO_COLD last=" + str(value[-1]))
        del value
    except Exception as error:
        print("EVO_COLD recall=" + type(error).__name__)
    gc.collect()
    after = gc.mem_free() if hasattr(gc, "mem_free") else None
    print("EVO_COLD after=" + str(after))


if __name__ == "__main__" or sys.implementation.name == "tipython":
    main()
