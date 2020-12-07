try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False
import time

SCRIPT_NAME    = "snotebuf"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "why cant i hold all these snotes"

SETTINGS = {}

def tokenise_line(line):
    if line.startswith("@"):
        # discard tags
        tags, line = line.split(" ", 1)

    trailing = None

    if " :" in line:
        line, trailing = line.rsplit(" :", 1)

    args = line.split(" ")

    source = None
    if args[0].startswith(":"):
        source = args.pop(0)[1:]

    command = args.pop(0).upper()

    if trailing is not None:
        args.append(trailing)

    return source, command, args

def modify_notice(data, signal, network, line):
    infolist  = w.infolist_get("irc_server", "", network)
    w.infolist_next(infolist)
    connected = w.infolist_integer(infolist, "is_connected")
    w.infolist_free(infolist)

    if connected:
        source, command, args = tokenise_line(line)

        if (source is not None and
                not "!" in source and
                "." in source and
                args[0] == "*"):

            buf   = w.buffer_search("", "snotebuf")
            nickc = w.color(w.info_get("nick_color_name", source))
            reset = w.color("reset")

            w.prnt(buf, f"-{nickc}{source}{reset}- {args[-1]}")
            return ""

    return line

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    buf = w.buffer_search("", "snotebuf")
    if len(buf) == 0:
        buf = w.buffer_new("snotebuf", "", "", "", "")

    w.buffer_set(buf, "name", "snotebuf")

    w.hook_modifier(
        "irc_in2_notice",
        "modify_notice",
        ""
    )
