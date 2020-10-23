try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False
import time

SCRIPT_NAME    = "statusmsg_action"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "make visually distinct STATUSMSG actions, add /action <target> <message>"

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

def _format_action(server, target, nick, text):
    snick = w.info_get("irc_nick", server)
    if snick == nick:
        nickc = w.color("white")
    else:
        nickc = w.color(w.info_get("nick_color_name", nick))
    chanc = w.color(w.config_string(w.config_get("weechat.color.chat_channel")))
    delim = w.color(w.config_string(w.config_get("weechat.color.chat_delimiters")))
    reset = w.color("reset")
    return f"* {delim}({reset}{target[0]}{delim}){nickc}{nick}{reset} {text}"

def _statusmsg(server):
    return w.info_get(
        "irc_server_isupport_value",
        f"{server},STATUSMSG"
    )

def modify_privmsg(data, signal, server, line):
    statusmsg = _statusmsg(server)

    source, command, args = tokenise_line(line)
    if (source and
            statusmsg and
            args[0][0] in statusmsg and
            args[-1].startswith("\x01ACTION ")):

        chan = args[0]
        buff = w.buffer_search("irc", f"{server}.{chan[1:]}")
        if buff:
            text = args[1].split(" ", 1)[1].rstrip("\x01")
            nick = source.split("!", 1)[0]
            out  = _format_action(server, chan, nick, text)
            w.prnt(buff, out)
            return ""

    return line

def on_command(data, buffer, args):
    server = w.buffer_get_string(buffer, 'localvar_server')
    if args.count(" ") > 0:
        target, _, message = args.partition(" ")
        if target[0] in _statusmsg(server):
            buff = w.buffer_search("irc", f"{server}.{target[1:]}")
            if buff:
                nick = w.info_get("irc_nick", server)
                out  = _format_action(server, target, nick, message)
                w.prnt(buff, out)
                w.command(buff, f"/quote PRIVMSG {target} :\x01ACTION {message}\x01")
        else:
            buff = w.buffer_search("irc", f"{server}.{target}")
            if buff:
                w.command(buff, f"/me {message}")
    return w.WEECHAT_RC_OK


if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    w.hook_modifier(
        "irc_in2_privmsg",
        "modify_privmsg",
        ""
    )
    w.hook_command("action", '', '', '', '', "on_command", '')

