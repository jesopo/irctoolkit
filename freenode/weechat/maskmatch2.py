import string
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
    return _mutli_replace(s, ASCII_UPPER, ASCII_LOWER)

def _fold(casemap, s):
    if casemap == "rfc1459":
        return _fold_rfc1459(s)
    elif casemap == "ascii":
        return _fold_ascii(s)
    else:
        raise ValueError(f"Unknown casemap {casemap}")

def _mode_tokens(modes, args, prefix, chanmodes):
    mode_a, mode_b, mode_c, mode_d = chanmodes
    arg_add    = mode_a+mode_b+mode_c
    arg_remove = mode_a+mode_b

    add = True
    out = []

    for char in modes:
        if char in "+-":
            add = char == "+"
        elif char in prefix:
            args.pop(0) # discard!
        elif args:
            if add:
                has_arg = char in arg_add
            else:
                has_arg = char in arg_remove

            if has_arg:
                out.append((add, char, args.pop(0)))
    return out

def _user_masks(server, channel, casemap):
    infolist = w.infolist_get("irc_nick", "", f"{server},{channel}")

    out =  {}
    while w.infolist_next(infolist):
        name = w.infolist_string(infolist, "name")
        host = w.infolist_string(infolist, "host")
        real = w.infolist_string(infolist, "realname")
        acc  = w.infolist_string(infolist, "account")

        masks = []
        fold_hostmask = _fold(casemap, f"{name}!{host}")
        fold_realname = _fold(casemap, real)
        masks.append((False, fold_hostmask))
        masks.append((True,  f"$x:{fold_hostmask}#{fold_realname}"))
        masks.append((True,  f"$r:{fold_realname}"))

        if acc:
            fold_account = _fold(casemap, acc)
            masks.append((True, f"$a:{fold_account}"))

        out[name] = masks
    w.infolist_free(infolist)

    return out

def _unique_masks(mode_tokens, casemap):
    seen         = set([])
    unique_masks = []
    for add, mode, mode_arg in mode_tokens:
        extban = False
        if ":" in mode_arg:
            extban = True
            prefix, sep, mask = mode_arg.partition(":")
            mask = prefix + sep + _fold(casemap, mask)
        else:
            mask = _fold(casemap, arg)
        mask = _glob_collapse(mask)

        if not mask in seen:
            seen.add(mask)
            unique_masks.append((extban, mask))
    return unique_masks

def _match_one(extban, mask, users_masks):
    affected = []
    for nickname in sorted(users_masks.keys()):
        user_masks = users_masks[nickname]
        for user_extban, user_mask in user_masks:
            if ((not extban or user_extban) and
                    _glob_match(mask, user_mask)):
                affected.append(nickname)
                break
    return affected

def _match_many(masks, users_masks):
    matches = []
    for extban, mask in masks:
        affected = _match_one(extban, mask, users_masks)
        for nickname in affected:
            matches.append((mask, nickname))
    return matches

def _print_matches(target, matches):
    pcolor = w.color("green")
    reset  = w.color("reset")
    prefix = f"[{pcolor}maskmatch{reset}]"
    for mask, nickname in matches:
        ncolor = w.color(w.info_get("irc_nick_color_name", nickname))
        w.prnt(target, f"{prefix} {mask} matches {ncolor}{nickname}{reset}")

def _is_whitelisted(server, target):
    whitelist   = w.config_get_plugin("whitelist")
    whitelist_l = [w.strip() for w in whitelist.split(",")]
    whitelist_l = list(filter(bool, whitelist_l))

    return (server in whitelist_l or
        target in whitelist_l)

def on_channel_mode(data, signal, signal_data):
    server = signal.split(",")[0]
    parsed = w.info_get_hashtable(
        "irc_message_parse", {"message": signal_data}
    )
    chan   = parsed["channel"]
    target = w.buffer_search("irc", f"{server}.{chan}")

    if _is_whitelisted(server, target):
        modes  = parsed["text"]
        args   = []
        if " " in modes:
            modes, _, args = modes.partition(" ")
            args = list(filter(bool, args.split(" ")))

        casemap = w.info_get(
            "irc_server_isupport_value", f"{server},CASEMAPPING"
        ) or "rfc1459"

        prefix = w.info_get(
            "irc_server_isupport_value", f"{server},PREFIX"
        ).split(")", 1)[0][1:]

        chanmodes = w.info_get(
            "irc_server_isupport_value", f"{server},CHANMODES"
        ).split(",", 3)

        mode_tokens  = _mode_tokens(modes, args, prefix, chanmodes)
        unique_masks = _unique_masks(mode_tokens, casemap)
        users_masks  = _user_masks(server, chan, casemap)
        matches      = _match_many(unique_masks, users_masks)
        _print_matches(target, matches)

    return w.WEECHAT_RC_OK

SETTINGS = {
    "whitelist": ["", "CSV servers and buffer names to enable mask matching on"]
}

if import_ok and w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
    for name, (default, description) in SETTINGS.items():
        if not w.config_is_set_plugin(name):
            w.config_set_plugin(name, default)
            w.config_set_desc_plugin(name, description)
    w.hook_signal("*,irc_in_MODE", "on_channel_mode", "")
