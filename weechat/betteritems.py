try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False

SCRIPT_NAME    = "betteritems"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "20% cooler bar items"

DEFAULT_COLOR  = "lightred"
DEFAULT_UMODES = {
    "CALLERID=g": "214",
    "DEAF=D":     "lightred",
    "+o":         "blue",
}
DEFAULT_CMODE = {
    "i": "214",
    "m": "214"
}

def items_modes_update():
    w.bar_item_update("better_umodes")
    w.bar_item_update("better_cmodes")

def default_umodes(server):
    modes = {}
    for mode, color in DEFAULT_UMODES.items():
        if not mode[0] == "+":
            # ISUPPORT mode
            name, default = mode.split("=", 1)
            mode = w.info_get(
                "irc_server_isupport_value",
                f"{server},{name}"
            ) or default
        else:
            mode = mode[1:]

        modes[mode] = color
    return modes
def default_cmodes(server):
    return DEFAULT_CMODE

def mode_setting(type, server):
    smodes = w.config_get_plugin(f"{type}.{server}").split(";")
    modesf = {}

    for i, modes in enumerate(smodes):
        modes, _, color = modes.partition(":")
        color = color or DEFAULT_COLOR

        for mode in modes.strip():
            modesf[mode] = color.strip()
    return modesf

def bar_item_umodes(data, item, window):
    buffer = w.window_get_pointer(window, "buffer")
    server = w.buffer_get_string(buffer, "localvar_server")

    if server:
        uinfo = w.infolist_get("irc_Server", '', server)
        w.infolist_next(uinfo)
        modes = w.infolist_string(uinfo, "nick_modes")
        w.infolist_free(uinfo)

        modes  = list(sorted(modes))
        reset  = w.color("reset")
        modesf = mode_setting("umodes", server) or default_umodes(server)

        for i, mode in enumerate(modes):
            if mode in modesf:
                color = w.color(modesf[mode])
                modes[i] = f"{color}{mode}{reset}"

        return "".join(modes)
    else:
        return ""

def bar_item_cmodes(data, item, window):
    buffer  = w.window_get_pointer(window, "buffer")
    server  = w.buffer_get_string(buffer, "localvar_server")
    channel = w.buffer_get_string(buffer, "localvar_channel")

    if w.info_get("irc_is_channel", channel):
        cinfo = w.infolist_get("irc_channel", '', f"{server},{channel}")
        w.infolist_next(cinfo)
        modes = w.infolist_string(cinfo, "modes")
        w.infolist_free(cinfo)

        modes, _, args = modes.lstrip("+").partition(" ")
        args  = args.split(" ")
        modes = list(modes)

        isupport_chanmodes = w.info_get(
            "irc_server_isupport_value",
            f"{server},CHANMODES"
        ).split(",", 3)
        modes_with_args    = set("".join(isupport_chanmodes[:3]))

        for i, mode in enumerate(modes):
            if mode in modes_with_args and args:
                modes[i] = (mode, args.pop(0))
            else:
                modes[i] = (mode, None)
        args.clear()
        modes.sort(key=lambda m: m[0])

        reset  = w.color("reset")
        modesf = mode_setting("cmodes", server) or default_cmodes(server)
        for i, (mode, arg) in enumerate(modes):
            if mode in modesf:
                color = w.color(modesf[mode])
                mode = f"{color}{mode}{reset}"
                if arg:
                    arg  = f"{color}{arg}{reset}"
            if arg:
                args.append(arg)
            modes[i] = mode

        args = " ".join(args)
        if args:
            args = f" {args}"
        return "+" + "".join(modes) + args
    return ""

def config_all(data, buffer, args):
    items_modes_update()
def signal_mode(data, signal, signal_data):
    items_modes_update()
    return w.WEECHAT_RC_OK

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    w.bar_item_new("better_umodes", "bar_item_umodes", "")
    w.bar_item_new("better_cmodes", "bar_item_cmodes", "")
    items_modes_update()

    w.hook_config(f"plugins.var.python.{SCRIPT_NAME}.*", "config_all", '')
    w.hook_signal("*,irc_in_MODE", "signal_mode", '')
    w.hook_signal("*,irc_in_221", "signal_mode", '') # RPL_UMODEIS
    w.hook_signal("*,irc_in_324", "signal_mode", '') # RPL_CHANNELMODEIS
