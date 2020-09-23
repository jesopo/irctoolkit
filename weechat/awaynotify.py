try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False
import time

SCRIPT_NAME    = "awaynotify"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "RPL_AWAY prints to queries so why not away-notify"

def tokenise(line):
    if line.startswith("@"):
        tags, _, line = line.partition(" ")

    args = []
    if " :" in line:
        line, _, trailing = line.partition(" :")
        args.append(trailing)

    args    = list(filter(bool, line.split(" "))) + args
    source  = None
    if args[0].startswith(":"):
        source = args.pop(0)[1:]
    command = args.pop(0).upper()

    return (source, command, args)

def signal_away(data, signal, signal_data):
    server = signal.split(",")[0]
    source, command, args = tokenise(signal_data)
    nick   = source.split("!", 1)[0]

    target = w.buffer_search("irc", f"{server}.{nick}")
    if target:
        delim = w.color(w.config_string(w.config_get("weechat.color.chat_delimiters")))
        out   = w.prefix("network")
        out  += f"{delim}["
        out  += w.color(w.info_get("irc_nick_color_name", nick))
        out  += nick
        out  += f"{delim}]"
        out  += w.color("reset")
        if args:
            out += f" is away: {args[0]}"
        else:
            out +=  " is back"
        w.prnt(target, out)

    return w.WEECHAT_RC_OK

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    w.hook_signal(
        "*,irc_in_AWAY",
        "signal_away",
        ""
    )
