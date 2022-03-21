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

def default_umodes(server):
    modes = {}
    for mode, color in DEFAULT_UMODES.items():
        if not mode[0] == "+":
            # ISUPPORT mode
            name, default = mode.split("=", 1)
            if w.info_get("irc_server_isupport", f"{server},{name}") == "1":
                mode = w.info_get(
                    "irc_server_isupport_value",
                    f"{server},{name}"
                ) or default
            else:
                continue
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
        uinfo = w.infolist_get("irc_server", '', server)
        w.infolist_next(uinfo)
        modes = w.infolist_string(uinfo, "nick_modes")
        w.infolist_free(uinfo)

        modes  = list(sorted(modes))
        modesf = mode_setting("umodes", server) or default_umodes(server)

        for i, mode in enumerate(modes):
            if mode in modesf:
                color = w.color(modesf[mode])
            else:
                color = w.color(w.config_string(w.config_get(
                    "irc.color.item_nick_modes"
                )))
            modes[i] = f"{color}{mode}"

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
        if w.config_get_plugin("args-first") == "yes":
            modes.sort(key=lambda m: 0 if m[1] else 1)

        modesf = mode_setting("cmodes", server) or default_cmodes(server)
        for i, (mode, arg) in enumerate(modes):
            if mode in modesf:
                color = w.color(modesf[mode])
            else:
                color = w.color(w.config_string(w.config_get(
                    "irc.color.item_channel_modes"
                )))

            mode = f"{color}{mode}"
            if arg:
                args.append(f"{color}{arg}")
            modes[i] = mode

        args = " ".join(args)
        if args:
            args = f" {args}"
        return "+" + "".join(modes) + args
    return ""

def bar_item_prefix(data, item, window):
    buffer  = w.window_get_pointer(window, "buffer")
    server  = w.buffer_get_string(buffer, "localvar_server")
    channel = w.buffer_get_string(buffer, "localvar_channel")
    if w.info_get("irc_is_channel", channel):
        nick   = w.info_get("irc_nick", server)
        ninfo  = w.infolist_get("nicklist", buffer, f"nick_{nick}")
        w.infolist_next(ninfo)
        prefix = w.infolist_string(ninfo, "prefix")
        pcolor = w.infolist_string(ninfo, "prefix_color")
        w.infolist_free(ninfo)

        pcolor = w.color(pcolor)
        return f"{pcolor}{prefix}"
    return ""

def bar_item_nick(data, item, window):
    buffer  = w.window_get_pointer(window, "buffer")
    server  = w.buffer_get_string(buffer, "localvar_server")
    if server:
        nick  = w.info_get("irc_nick", server)
        color = w.config_string(w.config_get("irc.color.input_nick"))

        color = w.color(color)
        return f"{color}{nick}"
    return ""

def bar_item_prompt(data, item, window):
    buffer  = w.window_get_pointer(window, "buffer")
    server  = w.buffer_get_string(buffer, "localvar_server")

    prompt  = ""
    prompt += bar_item_prefix(data, item, window)
    prompt += bar_item_nick(data, item, window)

    umodes  = bar_item_umodes(data, item, window)
    if umodes:
        delim   = w.config_string(w.config_get("weechat.bar.input.color_delim"))
        delim   = w.color(delim)
        reset   = w.color("reset")
        prompt += f"{delim}({reset}"
        prompt += umodes
        prompt += f"{delim})"
    return prompt

def items_update():
    w.bar_item_update("better_nick")
    w.bar_item_update("better_umodes")
    w.bar_item_update("better_cmodes")
    w.bar_item_update("better_prefix")
    w.bar_item_update("better_prompt")

def config_plugin(data, buffer, args):
    items_update()
    return w.WEECHAT_RC_OK
def config_channel(data, buffer, args):
    w.bar_item_update("better_cmodes")
    w.bar_item_update("better_prompt")
    return w.WEECHAT_RC_OK
def config_user(data, buffer, args):
    w.bar_item_update("better_umodes")
    w.bar_item_update("better_prompt")
    return w.WEECHAT_RC_OK
def config_prefix(data, buffer, args):
    w.bar_item_update("better_prefix")
    w.bar_item_update("better_prompt")
    return w.WEECHAT_RC_OK
def config_nick(data, buffer, args):
    w.bar_item_update("better_nick")
    w.bar_item_update("better_prompt")
    return w.WEECHAT_RC_OK
def config_delim(data, buffer, args):
    w.bar_item_update("better_prompt")
    return w.WEECHAT_RC_OK

def signal_mode(data, signal, signal_data):
    items_update()
    return w.WEECHAT_RC_OK

def signal_nick(data, signal, signal_data):
    items_update()
    return w.WEECHAT_RC_OK

SETTINGS = {
    "args-first": ["no", "whether or not to sort modes with args first"]
}

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    for name, (default, description) in SETTINGS.items():
        if not w.config_is_set_plugin(name):
            w.config_set_plugin(name, default)
            w.config_set_desc_plugin(name, description)

    w.bar_item_new("better_nick",   "bar_item_nick",   "")
    w.bar_item_new("better_umodes", "bar_item_umodes", "")
    w.bar_item_new("better_cmodes", "bar_item_cmodes", "")
    w.bar_item_new("better_prefix", "bar_item_prefix", "")
    w.bar_item_new("better_prompt", "bar_item_prompt", "")
    items_update()

    w.hook_config(f"plugins.var.python.{SCRIPT_NAME}.*", "config_plugin",  '')
    w.hook_config("irc.color.item_channel_modes",        "config_channel", '')
    w.hook_config("irc.color.item_nick_modes",           "config_user",    '')
    w.hook_config("irc.color.nick_prefixes",             "config_prefix",  '')
    w.hook_config("irc.color.input_nick",                "config_nick",    '')
    w.hook_config("weechat.bar.input.color_delim",       "config_delim",   '')

    w.hook_signal("*,irc_in_MODE", "signal_mode", '')
    w.hook_signal("*,irc_in_NICK", "signal_nick", '')
    w.hook_signal("*,irc_in_221", "signal_mode",  '') # RPL_UMODEIS
    w.hook_signal("*,irc_in_324", "signal_mode",  '') # RPL_CHANNELMODEIS
