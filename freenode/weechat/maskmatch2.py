try:
    import weechat as w
    import_ok = True
except ImportError:
    print("This script must be run under WeeChat")
    print("Get WeeChat now at: https://weechat.org/")
    import_ok = False

SCRIPT_NAME    = "maskmatch2"
SCRIPT_AUTHOR  = "jesopo"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "script to match charybdis mode change masks to users"

def _glob_collapse(pattern):
    out = ""
    i = 0
    while i < len(pattern):
        seen_ast = False
        while pattern[i:] and pattern[i] in ["*", "?"]:
            if pattern[i] == "?":
                out += "?"
            elif pattern[i] == "*":
                seen_ast = True
            i += 1
        if seen_ast:
            out += "*"

        if pattern[i:]:
            out += pattern[i]
            i   += 1
    return out

def _glob_match(pattern, s):
    i, j = 0, 0

    i_backup = -1
    j_backup = -1
    while j < len(s):
        p = (pattern[i:] or [None])[0]

        if p == "*":
            i += 1
            i_backup = i
            j_backup = j

        elif p in ["?", s[j]]:
            i += 1
            j += 1

        else:
            if i_backup == -1:
                return False
            else:
                j_backup += 1
                j = j_backup
                i = i_backup

    return i == len(pattern)

def _mode_tokens(modes, args, prefix, chanmodes):
    mode_a, mode_b, mode_c, mode_d = chanmodes.split(",", 3)
    arg_add    = prefix+mode_a+mode_b+mode_c
    arg_remove = prefix+mode_a+mode_b

    add = True
    out = []

    for char in modes:
        arg = None
        if char in "+-":
            add = char == "+"
        else:
            if add:
                if char in arg_add:
                    arg = args.pop(0)
            else:
                if char in arg_remove:
                    arg = args.pop(0)
            out.append((add, char, arg))
    return out

def _user_masks(server, channel):
    infolist = w.infolist_get("irc_nick", "", "{},{}".format(server, channel))

    out =  {}
    while w.infolist_next(infolist):
        name = w.infolist_string(infolist, "name")
        host = w.infolist_string(infolist, "host")
        real = w.infolist_string(infolist, "realname")
        acc  = w.infolist_string(infolist, "account")

        masks = []
        hostmask = f"{name}!{host}"
        masks.append(hostmask)
        masks.append(f"$x:{hostmask}#{real}")
        masks.append(f"$r:{real}")

        if acc:
            masks.append(f"$a:{acc}")

        out[name] = masks
    w.infolist_free(infolist)

    return out

def _match(match_mask, user_masks):
    affected = []
    for nick, masks in user_masks.items():
        for mask in masks:
            if ((not match_mask[0] == "$" or mask[0] == "$") and
                    _glob_match(match_mask, mask)):
                affected.append(nick)
                break
    return affected

def _print_matches(target, mode_tokens, user_masks):
    pcolor = w.color("green")
    reset  = w.color("reset")
    prefix = f"[{pcolor}maskmatch{reset}]"

    for add, mode, arg in mode_tokens:
        if arg is not None:
            collapsed = _glob_collapse(arg)
            affected = _match(collapsed, user_masks)
            for nick in affected:
                ncolor = w.color(w.info_get("irc_nick_color_name", nick))
                w.prnt(target, f"{prefix} {arg} matches {ncolor}{nick}{reset}")

def on_channel_mode(data, signal, signal_data):
    server = signal.split(",")[0]
    parsed = w.info_get_hashtable("irc_message_parse", {"message": signal_data})
    chan   = parsed["channel"]
    target = w.buffer_search("irc", f"{server}.{chan}")

    modes  = parsed["text"]
    args   = []
    if " " in modes:
        modes, _, args = modes.partition(" ")
        args = list(filter(bool, args.split(" ")))

    prefix    = w.info_get("irc_server_isupport_value", f"{server},PREFIX")
    prefix    = prefix.split(")", 1)[0][1:]
    chanmodes = w.info_get("irc_server_isupport_value", f"{server},CHANMODES")

    mode_tokens = _mode_tokens(modes, args, prefix, chanmodes)
    user_masks  = _user_masks(server, chan)

    _print_matches(target, mode_tokens, user_masks)

    return w.WEECHAT_RC_OK

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    w.hook_signal("*,irc_in_MODE", "on_channel_mode", "")
