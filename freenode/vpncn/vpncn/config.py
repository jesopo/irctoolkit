import yaml, re
from dataclasses import dataclass
from typing      import Dict, List, Pattern, Tuple

from ircrobots.glob import Glob, compile as glob_compile

@dataclass
class Config(object):
    hostname: str
    nickname: str
    sasl:     Tuple[str, str]
    admins:   List[Glob]
    patterns: Dict[Pattern, str]
    act_sets: Dict[str, List[Tuple[bool, str]]]
    channels: Dict[str, List[str]]
    bad:      Dict[int, Dict[Pattern, str]]

def load_config(path: str) -> Config:
    with open(path) as f:
        config = yaml.safe_load(f.read())

    patterns: Dict[Pattern, str] = {}
    for key, value in config["patterns"].items():
        patterns[re.compile(key)] = value

    act_default = config["act-default"]
    chans: Dict[str, List[str]] = {}
    for chan in config["channels"]:
        if isinstance(chan, str):
            chans[chan]   = act_default
        elif isinstance(chan, dict):
            chan_k = list(chan.keys())[0]
            chans[chan_k] = chan[chan_k]

    bad_c = config["bad"]
    bad: Dict[int, Dict[Pattern, str]] = {}
    for port in bad_c:
        if (isinstance(port, int) and
                isinstance(bad_c[port], dict)):
            bad[port] = {}
            for key, value in bad_c[port].items():
                bad[port][re.compile(key)] = value

    return Config(
        config["hostname"],
        config["nickname"],
        (config["sasl"]["username"], config["sasl"]["password"]),
        [glob_compile(m) for m in config["admins"]],
        patterns,
        config["act-sets"],
        chans,
        bad
    )
