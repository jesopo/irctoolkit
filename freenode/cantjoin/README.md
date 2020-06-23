# cantjoin

A bot to tell you why a given user can't join a given channel

## requirements

> $ pip3 install ircrobots

## running the bot
> $ python3 -m cantjoin mybot --sasl myaccount:hunter2

## usage
> /msg mybot cantjoin baduser ##channel

The bot will query the given channel's ban list and modes, and try to determine
why the user cannot join the given channel, and then `NOTICE` you that info.
