from dataclasses import dataclass
from enum        import IntEnum
from typing      import List, Optional

@dataclass
class Config(object):
    db:       str
    channels: List[str]
    trigger:  str
    chanserv: bool
    enforce:  bool
    quiet:    Optional[str]

class Types(IntEnum):
    BAN   = 1
    QUIET = 2
