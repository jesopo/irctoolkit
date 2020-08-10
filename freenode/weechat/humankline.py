try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False
import re, shlex

SCRIPT_NAME    = "humankline"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "a less irritating interface to charybdis klines"

REGEX_PRETTYTIME = re.compile(
    r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", re.I)
MINUTES_HOUR = 60
MINUTES_DAY  = MINUTES_HOUR*24
MINUTES_WEEK = MINUTES_DAY *7

def from_pretty_time(pretty_time):
    seconds = 0

    match = re.match(REGEX_PRETTYTIME, pretty_time)
    if match:
        seconds += int(match.group(1) or 0)*MINUTES_WEEK
        seconds += int(match.group(2) or 0)*MINUTES_DAY
        seconds += int(match.group(3) or 0)*MINUTES_HOUR
        seconds += int(match.group(4) or 0)

    if seconds >= 0:
        return seconds
    return None

def on_command(data, buffer, sargs):
    server  = w.buffer_get_string(buffer, 'localvar_server')
    args    = shlex.split(sargs)
    def_dur = w.config_get_plugin("default-duration")

    pieces = [
        "KLINE", # command
        def_dur, # duration
        None,    # user@host
        None,    # ON
        None,    # server
        None     # reason|operreason
    ]
    dryrun = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("+"):
            args.pop(i)
            arg_d = arg[1:]
            if not arg_d:
                duration = 0
            else:
                duration = from_pretty_time(arg_d)
                if duration is None:
                    raise ValueError("incorrect kline duration")
            pieces[1] = str(duration)
        elif arg in ["-t", "--target"]:
            args.pop(i)
            if args[i:]:
                pieces[3] = "ON"
                pieces[4] = args.pop(i)
            else:
                raise ValueError("please provide a target server")
        elif arg in ["-d", "--dry"]:
            args.pop(i)
            dryrun = True
        else:
            i += 1
    pieces[2] = args[0]
    if args[1:]:
        pieces[5] = args[1]
        if args[2:]:
            pieces[5] += f"|{args[2]}"

    pieces = list(filter(bool, pieces))
    if " " in pieces[-1] or pieces[-1].startswith(":"):
        pieces[-1] = f":{pieces[-1]}"
    line   = " ".join(pieces)

    if dryrun:
        color   = w.color("green")
        reset   = w.color("reset")
        sbuffer = w.info_get("irc_buffer", server)

        w.prnt(sbuffer, f"[{color}humankline{reset}] {line}")
    else:
        w.command("", f"/quote -server {server} {line}")
    return w.WEECHAT_RC_OK

SETTINGS = {
    "default-duration": [str(MINUTES_DAY), "default minutes for hklines"]
}


if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    for name, (default, description) in SETTINGS.items():
        if not w.config_is_set_plugin(name):
            w.config_set_plugin(name, default)
            w.config_set_desc_plugin(name, description)

    w.hook_command(
        "hkline",
        "human-friendly klines",
        "<user>@<host> [\"<reason>\" [\"<oper reason>\"]] [+<time>] [--target|-t <server>]",
        (
            "server: the server on which to set the k-line\n"
            "  time: a compact duration preprended with a +, e.g. +1w2d"
        ),
        "",
        "on_command",
        ""
    )
