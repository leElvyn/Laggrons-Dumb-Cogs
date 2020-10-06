===========
Tournaments
===========

This is the guide for the ``tournaments`` cog. Everything you need is here.

``[p]`` is considered as your prefix.

------------
Installation
------------

To install the cog, first load the downloader cog, included
in core Red.::

    [p]load downloader

Then you will need to install the Laggron's Dumb Cogs repository::

    [p]repo add Laggrons-Dumb-Cogs https://github.com/retke/Laggrons-Dumb-Cogs

Finally, you can install the cog::

    [p]cog install Laggrons-Dumb-Cogs tournaments

.. warning:: The cog is not loaded by default.
    To load it, type this::

        [p]load tournaments

-----
Usage
-----

The tournaments cog provides advanced tools for organizing your
`Challonge <https://challonge.com/>`_) tournaments on your Discord server!

From the beginning to the end of your tournament, members of your server will
be able to join and play in your tournaments without even creating a
Challonge account.

The cog supports the registration and check-in of the tournament, including
seeding with Braacket.

Then, once the game starts, just sit down and watch ~~the magic~~ the bot
manage everything:

*   For each match, a channel will be created with the two players of this
    match.

*   They have their own place for discussing about the tournament, checking
    the stage list, banning stages/characters...

*   The bot checks activity in the channels. If one player doesn't talk within
    the first minutes, he will be disqualified.

*   Once the players have done their match, they can set their score with a
    command.

*   Players can also forfeit a match, or disqualify themselves.

*   As the tournament goes on, outdated channels will be deleted, and new ones
    will be created for the upcoming matches, the bot is constantly
    checking the bracket.


The T.O.s, short for Tournament Organizers, also have their set of tools:

*   Being able to see all the channels and directly talk in one in case of a
    problem makes their job way easier

*   If a match takes too long, they will be warned in their channel to prevent
    slowing down the bracket

*   They can directly modify the bracket on Challonge (setting scores,
    resetting a match), and the bot will handle the changes, warning players
    if their match is cancelled or has to be replayed. A warning is also
    sent in the T.O. channel.

*   Players can call a T.O. for a lag test for example, and a message will
    be sent in the defined T.O. channel


Add to all of this tools for streamers too!

*   Streamers can add themselves to the tournament (not as a player) and
    comment some matches

*   They will choose the matches they want to cast, and also provide
    informations to players (for example, the room code and ID for smash bros)

*   If a match is launched but attached to a streamer, it will be paused until
    it is their turn. They will then receive the informations set above.

*   The streamer has access to the channels, so that he can also communicate
    with the players.

This was tested with tournaments up to 256 players, and I can personnaly
confirm this makes the organizers' job way easier.

^^^^^^^^^^^^^^^^^^
Setting up the cog
^^^^^^^^^^^^^^^^^^

There are multiple settings to configure before starting your tournament.

Most of these settings are optional, unless told.

First, set your Challonge credentials! This is specific to your server.

Use ``[p]challongeset username <your_challonge_username>``, then
``[p]challongeset api``. **Do not directly provide your token with the
command**, the bot will ask for it in DM, with the instructions.

.. warning:: Your token must stay secret, as it gives access to your account.

----

Then you can set the following channels with ``[p]tset channels``:

*   ``announcements``, where the bot announces registration, start and end of
    the tournament.

*   ``checkin``, where members will have to check (includes announcement).
    If this isn't set, members will be able to check everywhere.

*   ``queue``, where the bot announces the started matches.

*   ``register``, where members will be able to register (includes a pinned
    message with the count of participants updated in real time).
    If this isn't set, members will be able to register everywhere.

*   ``scores``, where participants will use the ``[p]win`` command to set their
    score. If this isn't set, participants will be able to
    use this command everywhere.

*   ``stream``, where sets going on stream will be announced.

*   ``to``, where the bot warns the T.O.s about important info (bracket
    modifications, participants asking for help). **Setting this is required.**

----

Next step, the roles with ``[p]tset roles``:

*   ``participant``, the role given to all participants when they register.
    **Setting this is required.**

*   ``streamer``, the role that gives access to the streamer commands.

*   ``to``, gives access to the T.O. commands. **This does not include the
    ``[p]tset`` command.**

.. attention:: The ``to`` role is available **if your T.O.s aren't
    moderators in your server**. If your T.O.s are moderators or
    administrators, use the core commands ``[p]set addmodrole`` and
    ``[p]set addadminrole`` instead, which will adapt the permissions of
    the entire bot to your mods and admins.

----

Some additional settings you can set:

*   ``[p]tset delay`` defines when a player is considered AFK and must be
    disqualified. This only listens for his first message in his channel, once
    someone spoke, he's safe. Defaults to 10 minutes.

*   ``[p]tset start_bo5`` defines at what point you want to move from BO3
    format to BO5.

*   ``[p]tset register`` defines when the registration should start and stop.
    See details in the commands section.

*   ``[p]tset checkin`` defines when the check-in should start and stop.
    See details in the commands section.

----

Finally, we can add our first game!

Some settings are dependant to a specific game, and this is where you set them.

Use ``[p]tset games add <name>`` to start. The name of the game must be the
same as the one provided by Challonge.

The bot will then give you the next commands to use. You can also type
``[p]help tset games``.

You will be able to define the legal stage list, list of counters, channel of
rules, role allowed to register (also pinged on registration start), info on
the mode of bans (like 3-4-1), and even braacket informations for seeding.

----

All good! We went across all settings, you can check those with the
``[p]tset settings`` and ``[p]tset games show`` commands.

You can now start your first tournament with ``[p]setup``.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Registration and check-in phases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Start and manage the tournament
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once you consider everything is good (check the bracket online to make sure),
start the tournament with ``[p]start``.

Multiple things will occur: first the tournament will be marked as started on
Challonge, then the bot will send all the initial messages in the defined
channels, and finally, the matchs will be launched.

The beginning is pretty impressive, because a lot of channels will start being
created. If you host a 128 players tournament, except 64 new channels in new
categories.

----

First thing to note: if a player does not talk in his channel within the 10
first minutes after the channel creation, he will be disqualified (you can
customize or disable this delay with ``[p]tset delay``). You are warned of this
in the T.O. channel.

If the bot somehow fails to create a channel, the match will be moved in DM
(the bot announces the set in DM, timers and AFK check are therefore disabled).

Players are able to use the ``[p]lag`` command, asking for a lag test. A
message will then be sent in the T.O. channel.

If a set takes too much time, the players will be warned first, then if it is
still not done, a message is sent in the T.O. channel.

You can edit things in the bracket yourself, such as setting a score or even
resetting a match. The bot should handle all changes, resulting in matches
being terminated (score set), relaunched (score reset) or even cancelled
(score reset with child matches ongoing). This will also be announced in the
T.O. channel.

The winner of a match will set his score with the ``[p]win`` command, inside
the scores channel if set.

Players can use at any time ``[p]ff`` for forfeiting a match (they can still
continue depending on the tournament mode, such as the usage of a loser
bracket), or ``[p]dq`` for completly disqualifying themselves.

T.O.s can disqualify players with ``[p]rm``.

.. tip:: To re-enable a disqualified player (because of an AFK check, or the
    ``[p]dq``/``[p]rm`` commands), do this directly on the bracket.

    On Challonge, go to the participants tab, and click on the "Reactivate"
    button.

If you need to restart the tournament, use the ``[p]resetbracket`` command.
Channels will be deleted, and the tournament will fall back to its previous
state. You can then either start again with ``[p]start`` or just remove it
with ``[p]reset``.

--------------------
Additional resources
--------------------

^^^^^^^^^^^^^^^
Troubleshooting
^^^^^^^^^^^^^^^

Having a critical bug in the middle of your tournament can be very annoying,
so this cog provides you advanced tools to attempt a fix while the
tournament is running with the ``[p]tfix`` command.

.. warning:: Those commands are high-level, and not knowing what you do can
    ruin your entire tournament, so *please* make sure to read the description
    of each command with ``[p]help tfix <your command>``.

----

First, the commands with the lowest risk level.

One thing to note, the bot fetches informations about the tournament only
during inital setup with ``[p]setup``. If you changed things like the limit
of participants or the tournament's name, use ``[p]tfix refresh``.

.. attention:: The following things will not be updated with
    ``[p]tfix refresh``:

    *   The game of the tournament (settings are based on this)
    *   Custom URL (the bot will return 404 if you do this, so don't try)

    *   The tournament's start date and time. Since registration and check-in
        opening and closing times are already calculated on this, redoing this
        process would be too hard to implement, with the ton of additional
        checks that comes with it.

If anything doesn't work correctly, try ``[p]tfix reload`` first. This is the
command that does the most: save, delete all objects we have in memory, then
rebuild the objects from what's saved on disk. Sounds like a lot, but this one
of the most stable functions since I kept spamming reloads when coding and
testing, so any issue with this was quickly fixed. However, if something wrong
happens, don't panic, and use the next command.

``[p]tfix restore`` can be used to attempt loading a tournament that is
saved on disk but not on the bot. If your bot suddenly tells you "There is
no tournament setup" (or the previous command failed), then you're looking for
this. If there are more issues, check the details in the logs, or ask a bot
administrator to help you.

----

Before explaining the next commands, let me explain what is the background loop
task. This is a task launched when you start your tournament that runs every
15 seconds, and does the following things :

*   Update the internal list of participants
*   Update the internal list of matches
*   Launch pending matches

*   Check for AFK players (someone didn't talk within the first 10 minutes in
    his channel, configurable with ``[p]tset delay``), and delete inactive
    channels (score reported and no message sent for 5 minutes)

*   Call streams

If too many errors occur in this task, it will be stopped, and you may not be
aware of this until you see that new matches stop being launched. You can
check the status of the task with ``[p]tinfo``.

Suppose you want to edit a lot of things in the bracket yourself, and you don't
want the bot to create 25 new channels and immediatly delete them, so you want
to pause this background task. Use ``[p]tfix pausetask`` and the bot won't
start new matches or look for bracket changes anymore.

You can then either use ``[p]tfix runtaskonce`` to only refresh matches and
launch matches once to check, or use ``[p]tfix resumetask`` to fully resume
the task. You can also use this last command to restore a task that bugged.

----

Finally, the danger zone. Those commands will perform a hard reset and cannot
restore what you had, depending on what you chose.

During registration and check-in, you can use ``[p]tfix resetparticipants``,
which will remove all participants from memory (not from the bracket if already
uploaded). If you want the bot to also remove the members' participant role,
call ``[p]tfix resetparticipants yes``, else everyone will keep their roles.

During the tournament, you can use ``[p]tfix resetmatches`` which removes all
matches and participants objects from memory. If the background task is still
running, the list of participants and matches will quickly be fetched back
from the bracket, re-creating fresh objects and new channels. Note that all
match channels existing when you run this command will be forgotten by the bot
and unusable. Like the command above, you can call ``[p]tfix resetmatches yes``
to make the bot delete all channels.

At whatever phase of the tournament, you can use ``[p]tfix hardreset``. See
this as the latest possible option, as this will simply delete all
internal objects, without trying anything else. It's like a factory reset,
put the bot back to its initial state, regardless of the current state (does
not reset settings). There is no announcement, no DM, no channel
cleared/removed, the bot will just say "There is no tournament" on commands.
Channels and roles will still be in place, everything will just stop. No API
call is sent to the bracket, it will stay as it is.

Before considering this, you must be sure of the consequences. Try to look
into other options first, like ``[p]reset``, ``[p]resetbracket`` or other
``[p]tfix`` commands.