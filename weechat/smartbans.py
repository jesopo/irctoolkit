try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False
import ipaddress, string

SCRIPT_NAME    = "smartbans"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "compute good ban/quiet masks"

WAITING = {}

def _multi_replace(s, upper, lower):
    s_l = list(s)
    for i, char in enumerate(s):
        if char in upper:
            s_l[i] = lower[upper.index(char)]
    return "".join(s_l)

ASCII_UPPER   = list(string.ascii_uppercase)
ASCII_LOWER   = list(string.ascii_lowercase)
RFC1459_UPPER = ASCII_UPPER+list("[]~\\")
RFC1459_LOWER = ASCII_LOWER+list("{}^|")
def _fold_rfc1459(s):
    return _multi_replace(s, RFC1459_UPPER, RFC1459_LOWER)
def _fold_ascii(s):
    return _multi_replace(s, ASCII_UPPER, ASCII_LOWER)

def _waiting_key(server, nick):
    key = f"{server}.{nick}"

    casemap = w.info_get(
        "irc_server_isupport_value",
        f"{server},CASEMAPPING"
    ) or "rfc1459"

    if casemap == "rfc1459":
        return _fold_rfc1459(key)
    elif casemap == "ascii":
        return _fold_ascii(key)
    else:
        raise ValueError(f"Unknown casemap {casemap}")

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

def do_action(server, channel, actions, nick, user, host, reason):
    if host.startswith("gateway/web/irccloud.com"):
        user = f"?{user[1:]}"
    elif user.startswith("~"):
        user = "*"

    if "/" in host:
        parts = host.split("/")
        if parts[-1].startswith("ip."):
            host = f"*/{parts[-1]}"
            user = "*"
        elif (parts[-1].startswith("x-") and
                parts[-1][2:].isalpha()):
            # cut off /x-abcd but not /x-1234,
            # the former is a session token
            host, _ = host.rsplit("/", 1)
            host += "/*"
        else:
            # unlikely a gateway/nat cloak, dont trust identd
            user = "*"
    else:
        # just a plain IP/rDNS. dont trust identd
        user = "*"

    mask  = f"*!{user}@{host}"
    lines = []
    if "ban" in actions:
        lines.append(f"MODE {channel} +b {mask}")
    if "quiet" in actions:
        lines.append(f"MODE {channel} +q {mask}")
    if "kick" in actions:
        line = f"KICK {channel} {nick}"
        if reason:
            line += f" :{reason}"
        lines.append(line)
    if "debug" in actions or True:
        cbuf  = w.buffer_search("irc", f"{server}.{channel}")
        color = w.color("green")
        reset = w.color("reset")

        line  = f"[{color}smartban{reset}] "
        line += f"channel: {channel} / nick: {nick} / mask: {mask}"
        w.prnt(cbuf, line)

    for line in lines:
        w.command('', f"/quote -server {server} {line}")

def modify_whox(data, signal, server, line):
    source, command, args = tokenise_line(line)
    if args[1] == "582" and len(args) == 6:
        nick = args[5]
        key  = _waiting_key(server, nick)

        global WAITING
        if key in WAITING:
            user = args[2]
            ip   = args[3]
            host = args[4]
            chan, actions, reason = WAITING[key][0]

            if not "/" in host:
                host = ip

            do_action(server, chan, actions, nick, user, host, reason)
            return ""
    return line

def modify_endwho(data, signal, server, line):
    source, command, args = tokenise_line(line)
    nick = args[1]
    key  = _waiting_key(server, nick)

    global WAITING
    if key in WAITING:
        WAITING[key].pop(0)
        if not WAITING[key]:
            del WAITING[key]
        return ""
    return line

def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False

def on_command(buffer, args, actions):
    channel = w.buffer_get_string(buffer, 'localvar_channel')
    if not w.info_get("irc_is_channel", channel):
        w.prnt(buffer, "error: Active buffer does not appear to be a channel.")
        return w.WEECHAT_RC_ERROR
    server  = w.buffer_get_string(buffer, 'localvar_server')

    nick, _, reason = args.partition(" ")

    info = w.infolist_get("irc_nick", '', f"{server},{channel},{nick}")
    w.infolist_next(info)
    host = w.infolist_string(info, "host")
    w.infolist_free(info)

    user, sep, host = host.rpartition("@")

    if sep and ("/" in host or _is_ip(host)):
        do_action(server, channel, actions, nick, user, host, reason)
    else:
        key = _waiting_key(server, nick)
        global WAITING
        if not key in WAITING:
            WAITING[key] = []
        WAITING[key].append((channel, actions, reason))

        w.command('', f"/quote -server {server} WHO {nick} %ihntu,582")
    return w.WEECHAT_RC_OK

def on_sban_command(data, buffer, args):
    return on_command(buffer, args, ["ban"])
def on_skb_command(data, buffer, args):
    return on_command(buffer, args, ["kick", "ban"])
def on_squiet_command(data, buffer, args):
    return on_command(buffer, args, ["quiet"])
def on_sdebug_command(data, buffer, args):
    return on_command(buffer, args, ["debug"])

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):

    w.hook_command("sban",   "smartbans", '', '', '', "on_sban_command", "")
    w.hook_command("skb",    "smartbans", '', '', '', "on_skb_command", "")
    w.hook_command("squiet", "smartbans", '', '', '', "on_squiet_command", "")
    w.hook_command("sdebug", "smartbans", '', '', '', "on_sdebug_command", "")

    w.hook_modifier(
        "irc_in2_354",
        "modify_whox",
        ""
    )
    w.hook_modifier(
        "irc_in2_315",
        "modify_endwho",
        ""
    )
