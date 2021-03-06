# aban_check

## requirements

> $ pip3 install ircrobots pyyaml

## usage
> $ ./python3 -m aban_check mybotnick "#mychan" out.yaml

## behaviour

this bot will connect to freenode, query the banlist for the given channel,
pick out the account (`$a:`) bans and then query NickServ for each account to
see which are still registered and which are not. the outfile will be a yaml
dictionary of nicknames, whether they are registered or not, and what channel
the ban comes from (for `$j:` ban trees.)

## beware

doing this on a massive ban list will, obviously, generate a lot of queries
to NickServ in relatively quick succession. there is throttling and the bot
waits until each query is finished before starting the new one, but
**you should mention what you are going to do to a staffer before using this
tool so you don't end up klined for creating flood warnings**
