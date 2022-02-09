use strict;
use Irssi;

use vars qw($VERSION %IRSSI);
$VERSION = '1.0';
%IRSSI = (
    authors     => 'jess',
    contact     => 'contact@jesopo.uk',
    name        => 'smartkline',
    description => 'what the world needs is more k-line scripts',
    license     => 'MIT',
    url         => '',
    changed     => '25/04/2021'
);

my %REASONS = (
    'evasion' =>    'Ban evasion is not welcome on Libera Chat. Please email bans@libera.chat if you think this network ban has been set in error.',
    'harassment' => 'Harassment is not welcome on Libera Chat. Please email bans@libera.chat if you think this network ban has been set in error.',
    'sexual' =>     'Sexual harassment it not welcome on Libera Chat. Please email bans@libera.chat if you think network ban kline has been set in error.',
    'spam' =>       'Spam is not welcome on Libera Chat. Please email bans@libera.chat if you think this network ban has been set in error.',
    'tos' =>        'You have violated Libera Chat\'s terms of service. Please email bans@libera.chat if you think this network ban has been set in error.',
    'racist' =>     'Racial invective contravenes Libera Chat\'s network policies. Please email bans@libera.chat if you think this network ban has been set in error'
);

sub casefold {
    return shift =~ tr/A-Z\[\]\^\\/a-z{}~|/r;
}

my %WAIT_ETRACE = ();
my %WAIT_TESTMASK = ();

sub time_unit {
    my ($i, $unit) = @_;
    if    ($unit eq 'w') { return $i * (1440 * 7); }
    elsif ($unit eq 'd') { return $i * 1440; }
    elsif ($unit eq 'h') { return $i * 60; }
    elsif ($unit eq 'm') { return $i + 0; }
}

sub testmask {
    my ($server, $duration, $mask, $reason) = @_;

    $server->redirect_event("skline testmask", 1, "*!$mask", -1, undef, {
        '' => 'redir skline-testmask',
    });
    $WAIT_TESTMASK{casefold $mask} = "/quote KLINE $duration $mask :$reason";
    $server->send_raw("TESTMASK $mask");
}

Irssi::command_bind('skline', sub {
    my ($data, $server, $win) = @_;

    my $duration = 0;
    while ($data =~ m/^\+((\d+)([wdhm]))/) {
        $duration += time_unit $2, $3;
        $data =~ s/$1//;
    }
    $data =~ s/^\+\s*//;
    if ($duration == 0) {
        $duration = 1440;
    }

    if (my ($target, $reason, $oper_reason)
        = $data =~ m/^(\S+)\s+(.*?)(\|.*)?$/)
    {
        if (exists $REASONS{$reason}) {
            $reason = $REASONS{$reason};
        }
        $reason .= $oper_reason;

        if ($target =~ m/@/) {
            testmask $server, $duration, $target, $reason;
        }
        else {
            $WAIT_ETRACE{casefold $target} = [$duration, $reason];
            $server->redirect_event(
                "skline etrace",
                1,
                $target,
                -1,
                undef,
                {
                    'event 708' => 'redir skline-etrace',
                    ''          => 'event empty'
                }
            );
            $server->send_raw("ETRACE $target");
        }
    }
    else {
        Irssi::print('Usage: /skline [+<time>] <nick|user@host> <reason>[|<oper-reason>]');
        Irssi::print(' e.g.: /skline +2d jess tos|right bastard');
        Irssi::print('reason aliases:');
        foreach my $key (keys %REASONS) {
            my $text = $REASONS{$key};
            Irssi::print(" $key: $text");
        }
    }
});

Irssi::Irc::Server::redirect_register(
    "skline etrace",
    0,
    0,
    undef,
    { "event 708" => 3 },
    { "event 262" => 1 }
);
Irssi::Irc::Server::redirect_register(
    "skline testmask",
    0,
    0,
    undef,
    { "event 727" => 3 },
    undef
);

Irssi::signal_add('redir skline-testmask', sub {
    my $server = shift;
    my @parts = split m/ /, shift;

    my $mask = $parts[3] =~ s/^\*!//r;
    my $affected = $parts[1] + $parts[2]; # local + remote

    my $out = "skline mask \2$mask\2 matches \2$affected\2 users";
    Irssi::active_win->print($out);

    Irssi::gui_input_set delete $WAIT_TESTMASK{casefold $mask};
    Irssi::gui_input_set_pos 0;
});

Irssi::signal_add('redir skline-etrace', sub {
    my $server = shift;
    my @parts = split m/ /, (my $data = shift);
    my ($nickname, $username, $hostname, $address) = @parts[3..6];
    my $nickname_fold = casefold $nickname;

    if (exists $WAIT_ETRACE{$nickname_fold}) {
        my ($ban_user, $ban_host) = ($username, $hostname);


        # tor uses 127.0.6.10
        if ($address !~ m/^127\./) {
            $ban_host = $address;
        }

        # replace ~ident with *
        $ban_user =~ s/^~.*$/*/;

        my ($duration, $reason) = @{delete $WAIT_ETRACE{$nickname_fold}};
        testmask $server, $duration, "$ban_user\@$ban_host", $reason;
    }
});
