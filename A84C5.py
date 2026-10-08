# A84C5: date reboot poweroff (Arch84 module, split from A84C2 so each lazily loaded piece
# has a small compile-time memory peak). Registers itself into COMMANDS.

from A84FS import VFSError, mono_s
from A84CD import COMMANDS, pad


def days_from_civil(y, m, d):
    if m <= 2:
        y -= 1
    era = y // 400
    yoe = y - era * 400
    if m > 2:
        mm = m - 3
    else:
        mm = m + 9
    doy = (153 * mm + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    if mp < 10:
        m = mp + 3
    else:
        m = mp - 9
    if m <= 2:
        y += 1
    return y, m, d


DAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
          "Oct", "Nov", "Dec")
CLOCK_FILE = "/etc/clock"


def clock_now(sh):
    # (days_since_1970, seconds_of_day, None) or (None, None, reason)
    try:
        parts = sh.vfs.read(CLOCK_FILE).split()
        days = int(parts[0])
        secs = int(parts[1])
        mono = int(parts[2])
    except (VFSError, ValueError, IndexError):
        return None, None, "clock not set (date -s 'YYYY-MM-DD HH:MM:SS')"
    now = mono_s()
    if now is None:
        return None, None, "no clock available"
    el = now - mono
    if el < 0:
        return None, None, "clock lost, calculator restarted (date -s ...)"
    t = secs + el
    return days + t // 86400, t % 86400, None


def parse_stamp(parts):
    # ["2026-10-07", "17:20[:30]"] -> (days, secs) or None
    if len(parts) != 2:
        return None
    try:
        d = parts[0].split("-")
        t = parts[1].split(":")
        if len(d) != 3 or len(t) < 2 or len(t) > 3:
            return None
        y = int(d[0])
        mo = int(d[1])
        da = int(d[2])
        h = int(t[0])
        mi = int(t[1])
        se = 0
        if len(t) == 3:
            se = int(t[2])
    except ValueError:
        return None
    if y < 1970 or y > 2099 or not 1 <= mo <= 12 or not 1 <= da <= 31:
        return None
    if not (0 <= h < 24 and 0 <= mi < 60 and 0 <= se < 60):
        return None
    days = days_from_civil(y, mo, da)
    if civil_from_days(days) != (y, mo, da):      # e.g. Feb 30
        return None
    return days, h * 3600 + mi * 60 + se


def cmd_date(sh, args):
    # No wall clock exists in this Python, so the time is set by hand and
    # kept as (moment, monotonic counter) in /etc/clock. It survives
    # relaunching Arch84 but not a calculator restart, and may drift if
    # the counter pauses while the calculator sleeps.
    if args and args[0] == "-s":
        parts = args[1:]
        if len(parts) == 1:
            parts = parts[0].split(" ")
        st = parse_stamp(parts)
        now = mono_s()
        if st is None:
            sh.err("date: invalid date, use -s 'YYYY-MM-DD HH:MM[:SS]'")
            return 1
        if now is None:
            sh.err("date: no clock available")
            return 1
        try:
            sh.vfs.write(CLOCK_FILE, str(st[0]) + " " + str(st[1]) + " " + str(now) + "\n")
        except VFSError as e:
            sh.err("date: cannot save clock: " + str(e))
            return 1
    elif args:
        sh.err("usage: date [-s 'YYYY-MM-DD HH:MM[:SS]']")
        return 1
    days, secs, why = clock_now(sh)
    if why:
        sh.err("date: " + why)
        return 1
    y, m, d = civil_from_days(days)
    sh.out(DAYS[(days + 4) % 7] + " " + MONTHS[m - 1] + " " + pad(d, 2) + " "
           + ("0" + str(secs // 3600))[-2:] + ":" + ("0" + str(secs // 60 % 60))[-2:]
           + ":" + ("0" + str(secs % 60))[-2:] + " " + str(y) + "\n")


def cmd_reboot(sh, args):
    if not sh.shutdown("reboot"):
        return 1


def cmd_poweroff(sh, args):
    sh.shutdown("poweroff")

COMMANDS.update({
    "date": cmd_date, "reboot": cmd_reboot, "poweroff": cmd_poweroff,
})
