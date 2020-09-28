from __future__ import annotations

import discord
import logging
import asyncio
import contextlib

from discord.ext import tasks
from random import choice
from itertools import islice
from datetime import datetime, timedelta
from babel.dates import format_date, format_time
from typing import Optional, Tuple, List, Union

from redbot.core import Config
from redbot.core.i18n import Translator, get_babel_locale
from redbot.core.data_manager import cog_data_path

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)

MAX_ERRORS = 5
TIME_UNTIL_CHANNEL_DELETION = 300
TIME_UNTIL_TIMEOUT_DQ = 300


class Participant(discord.Member):
    def __init__(self, member: discord.Member, tournament: Tournament):
        # code from discord.Member._copy
        self._roles = discord.utils.SnowflakeList(member._roles, is_sorted=True)
        self.joined_at = member.joined_at
        self.premium_since = member.premium_since
        self._client_status = member._client_status.copy()
        self.guild = member.guild
        self.nick = member.nick
        self.activities = member.activities
        self._state = member._state
        # Reference will not be copied unless necessary by PRESENCE_UPDATE
        self._user = member._user
        # now our own stuff
        self.tournament = tournament
        self._player_id = None
        self.checked_in = False
        self.match: Optional[Match] = None
        self.spoke = False  # True as soon as the participant sent a message in his channel
        # used to detect inactivity after the launch of a set

    def __repr__(self):
        return (
            "<Participant player_id={0.player_id} tournament_name={0.tournament.name} "
            "tournament_id={0.tournament.id} spoke={0.spoke} id={1.id} name={1.name!r}>"
        ).format(self, self._user)

    @classmethod
    def from_saved_data(cls, tournament: Tournament, data: dict):
        member = tournament.guild.get_member(data["discord_id"])
        if member is None:
            log.warning(f"[Guild {tournament.guild.id}] Lost participannt {data['discord_id']}")
            return None
        participant = cls(member, tournament)
        participant._player_id = data["player_id"]
        participant.spoke = data["spoke"]
        return participant

    def to_dict(self) -> dict:
        return {
            "discord_id": self.id,
            "player_id": self.player_id,
            "spoke": self.spoke,
        }

    def reset(self):
        self.match = None
        self.spoke = False

    async def check(self):
        self.checked_in = True
        log.debug(f"[Guild {self.guild.id}] Player {self} registered.")
        await self.send(
            _("You successfully checked in for the tournament **{name}**!").format(
                name=self.tournament.name
            )
        )

    @property
    def player_id(self):
        raise NotImplementedError

    async def destroy(self):
        """
        Removes the participant from the tournament.
        """
        raise NotImplementedError


class Match:
    def __init__(
        self,
        tournament: Tournament,
        round: int,
        set: str,
        id: int,
        underway: bool,
        player1: Participant,
        player2: Participant,
    ):
        self.guild: discord.Guild = tournament.guild
        self.tournament = tournament
        self.round = round
        self.set = set
        self.id = id
        self.underway = underway
        self.player1 = player1
        self.player2 = player2
        self.is_top8 = (
            round >= tournament.top_8["winner"]["top8"]
            or round <= tournament.top_8["loser"]["top8"]
        )
        self.is_bo5 = (
            round >= tournament.top_8["winner"]["bo5"] or round <= tournament.top_8["loser"]["bo5"]
        )
        self.round_name = self._get_name()
        self.channel: Optional[discord.TextChannel] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.status = "pending"  # can be "pending" "ongoing" "finished"
        self.checked_dq = True if self.is_top8 else False
        self.streamer: Optional[Streamer] = None
        self.on_hold = False  # True if this is match is awaiting for a stream
        # one or more players can be None
        # if this is the case, the bot will most likely close the match right after this
        with contextlib.suppress(AttributeError):
            player1.match = self
            player2.match = self

    def __repr__(self):
        return (
            "<Match status={0.status} round={0.round} set={0.set} id={0.id} underway={0.underway} "
            "channel={0.channel} start={0.start_time} tournament={0.tournament.name} "
            "guild_id={0.guild.id} player1={0.player1.name} player2={0.player2.name}>"
        ).format(self)

    def __del__(self):
        if self.streamer is not None:
            self.streamer.current_match = None
            self.streamer.matches.remove(self)

    @classmethod
    def from_saved_data(cls, tournament: Tournament, player1, player2, data: dict) -> Match:
        match = cls(
            tournament, data["round"], data["set"], data["id"], data["underway"], player1, player2
        )
        match.channel = tournament.guild.get_channel(data["channel"])
        if match.channel is None:
            match.status = "pending"
        else:
            match.status = data["status"]
            match.checked_dq = data["checked_dq"]
            match.start_time = (
                datetime.fromtimestamp(data["start_time"]) if data["start_time"] else None
            )
            match.end_time = datetime.fromtimestamp(data["end_time"]) if data["end_time"] else None
        return match

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "set": self.set,
            "id": self.id,
            "underway": self.underway,
            "player1": self.player1.player_id,
            "player2": self.player2.player_id,
            "channel": self.channel.id if self.channel else None,
            "start_time": self.start_time.timestamp() if self.start_time else None,
            "end_time": self.end_time.timestamp() if self.end_time else None,
            "status": self.status,
            "checked_dq": self.checked_dq,
        }

    def _get_name(self) -> str:
        if self.round > 0:
            max_round = self.tournament.top_8["winner"]["top8"]
            return {
                max_round: _("Grand Final"),
                max_round - 1: _("Winners Final"),
                max_round - 2: _("Winners Semi-Final"),
                max_round - 3: _("Winners Quarter-Final"),
            }.get(self.round, _("Winners round {round}").format(round=self.round))
        elif self.round < 0:
            max_round = self.tournament.top_8["loser"]["top8"]
            return {
                max_round: _("Losers Final"),
                max_round + 1: _("Losers Semi-Final"),
                max_round + 2: _("Losers Quarter-Final"),
            }.get(self.round, _("Losers round {round}").format(round=self.round))

    async def _dm_players(self, message: str):
        players = (self.player1, self.player2)
        for player in players:
            try:
                await player.send(message)
            except discord.HTTPException as e:
                log.warning(f"Can't send a DM to {str(player)} for his set.", exc_info=e)

    async def send_message(self, reset: bool = False) -> bool:
        """
        Send a message in the created channel.

        Parameters
        ----------
        reset: bool
            ``True`` if the match is started because of a reset.

        Returns
        -------
        bool
            ``False`` if the message couldn't be sent, and was sent in DM instead.
        """
        if reset is True:
            message = _(
                ":warning: **The bracket was modified!** This results in this match having to be "
                "replayed. Please check your new position on the bracket.\n\n"
            )
        else:
            message = ""
        top8 = _("**(top 8)** :fire:") if self.is_top8 else ""
        message += _(
            ":arrow_forward: **{0.set}** : {0.player1.mention} vs {0.player2.mention} {top8}\n"
        ).format(self, top8=top8)
        if self.tournament.ruleset_channel:
            message += _(
                ":white_small_square: The rules must follow the ones given in {channel}\n"
            ).format(channel=self.tournament.ruleset_channel.mention)
        if self.tournament.stages:
            message += _(
                ":white_small_square: The list of legal stages "
                "is available with `{prefix}stages` command.\n"
            ).format(prefix=self.tournament.bot_prefix)
        if self.tournament.counterpicks:
            message += _(
                ":white_small_square: The list of counter stages "
                "is available with `{prefix}counters` command.\n"
            ).format(prefix=self.tournament.bot_prefix)
        score_channel = (
            _("in {channel}").format(channel=self.tournament.scores_channel.mention)
            if self.tournament.scores_channel
            else ""
        )
        message += _(
            ":white_small_square: In case of lag making the game unplayable, use the "
            "`{prefix}lag` command to call the T.O. and solve the problem.\n"
            ":white_small_square: **As soon as the set is done**, the winner sets the "
            "score {score_channel} with the `{prefix}win` command.\n"
            ":arrow_forward: You will play this set as a {type}.\n"
        ).format(
            prefix=self.tournament.bot_prefix,
            score_channel=score_channel,
            type=_("**BO5** *(best of 5)*") if self.is_bo5 else _("**BO3** *(best of 3)*"),
        )
        if self.tournament.baninfo:
            chosen_player = choice([self.player1, self.player2])
            message += _(
                ":game_die: **{player}** was picked to begin the bans *({baninfo})*.\n"
            ).format(player=chosen_player.mention, baninfo=self.tournament.baninfo)
        if self.streamer is not None:
            message += _("**\nYou will be on stream on {streamer}!**\n").format(
                streamer=self.streamer.link
            )
            if self.on_hold is True:
                message += _(
                    ":warning: **Do not play your set for now and wait for your turn.** "
                    "I will send a message once it is your turn with instructions."
                )
            # else, we're about to send another message with instructions

        async def send_in_dm():
            nonlocal message
            message += _(
                "\n\n**You channel can't be created because of a problem. "
                "Do your set in DM and come back to set the result.**"
            )
            await self._dm_players(message)
            if self.tournament.queue_channel is not None:
                await self.tournament.queue_channel.send(
                    _("{player1} {player2} Play your set in DM").format(
                        player1=self.player1.mention, player2=self.player2.mention
                    )
                )

        if self.channel is None:
            await send_in_dm()
            return False
        try:
            await self.channel.send(message)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Can't create a channel for the set {self.set}",
                exc_info=e,
            )
            await send_in_dm()
            return False
        else:
            if self.tournament.queue_channel is not None:
                await self.tournament.queue_channel.send(
                    _(
                        ":arrow_forward: **{name}** ({bo_type}): {player1} vs {player2}"
                        "{on_stream} {top8} in {channel}"
                    ).format(
                        name=self.round_name,
                        bo_type=_("BO5") if self.is_bo5 else _("BO3"),
                        player1=self.player1.mention,
                        player2=self.player2.mention,
                        on_stream=_(" **on stream!**") if self.streamer else "",
                        top8=top8,
                        channel=self.channel.mention,
                    )
                )
            return True

    async def start_stream(self):
        destination = self.channel or self._dm_players
        if self.streamer.room_id:
            access = _("\n\nHere are the access codes:\nID: {id}\nPasscode: {passcode}").format(
                id=self.streamer.room_id, passcode=self.streamer.room_code
            )
        else:
            access = ""
        if self.status != "ongoing":
            await self._start()
        self.on_hold = False
        self.checked_dq = True
        await destination.send(
            _("You can go on stream on {channel} !{access}").format(
                channel=self.streamer.link, access=access
            )
        )

    async def cancel_stream(self):
        destination = self.channel or self._dm_players
        self.streamer = None
        self.on_hold = False
        await self._start()
        await destination.send(
            _(
                "{player1} {player2} The stream was cancelled. You can start you match normally.\n"
                ":warning: AFK checks are re-enabled."
            ).format(player1=self.player1.mention, player2=self.player2.mention)
        )

    async def create_channel(
        self, category: discord.CategoryChannel, *allowed_roles: list
    ) -> discord.TextChannel:
        """
        Creates a channel for the match and returns its object.

        Returns
        -------
        discord.TextChannel
            The created text channel
        """
        overwrites = {
            self.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.player1: discord.PermissionOverwrite(read_messages=True),
            self.player2: discord.PermissionOverwrite(read_messages=True),
        }
        for role in allowed_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True)
        return await self.guild.create_text_channel(
            self.set, category=category, overwrites=overwrites, reason=_("Lancement du set")
        )

    async def _start(self):
        await self.mark_as_underway()
        self.status = "ongoing"
        self.underway = True
        self.checked_dq = False
        self.start_time = datetime.utcnow()

    async def launch(
        self,
        *,
        category: Optional[discord.CategoryChannel] = None,
        restart: bool = False,
        allowed_roles: List[discord.Role] = [],
    ):
        """
        Launches the set.

        This does the following:

        *   Try to create a text channel with permissions for the two players and the given roles
        *   Send a DM to both members
        *   Mark the set as ongoing

        Parameters
        ----------
        category: Optional[discord.CategoryChannel]
            The category where to put the channel. If this is not provided, one will be found.
            If you're launching multiple sets at once with asyncio.gather, use this to prevent
            seeing one category per channel
        restart: bool
            If the match is restarted.
        allowed_roles: List[discord.Role]
            A list of roles with read_messages permission in the text channel.
        """
        if category is None:
            category = await self.tournament._get_available_category(
                "winner" if self.round > 0 else "loser"
            )
        allowed_roles = list(allowed_roles)
        allowed_roles.extend(self.tournament.allowed_roles)
        try:
            channel = await self.create_channel(category, *allowed_roles)
        except discord.HTTPException as e:
            log.error(
                f"[Guild {self.guild.id}] Couldn't create a channel for the set {self.set}.",
                exc_info=e,
            )
        else:
            self.channel = channel
        await self.send_message(reset=restart)
        if self.on_hold is False:
            await self._start()
            if self.streamer is not None:
                await self.start_stream()

    async def relaunch(self):
        """
        This is called in case of a match reset (usually from remote).

        We inform the players they need to play their set again, eventually re-use their old
        channel if it still exists.
        """
        if self.channel is not None:
            await self.mark_as_underway()
            self.status = "ongoing"
            await self.channel.send(
                _(
                    "{player1} {player2}\n"
                    ":warning: The score of this set was reset on the bracket. "
                    "Therefore, **the set must be replayed**. Ask the T.O. if you have "
                    "questions or believe this is a mistake."
                ).format(player1=self.player1.mention, player2=self.player2.mention)
            )
            self.underway = True
            self.start_time = datetime.utcnow()
        else:
            await self.launch(restart=True)

    async def check_inactive(self):
        self.checked_dq = True
        players = (self.player1, self.player2)
        if all((x.spoke is False for x in players)):
            log.debug(
                f"[Guild {self.guild.id}] Both players inactive, DQing "
                f"both and cancelling set #{self.set}."
            )
            await self.player1.destroy()
            await self.player2.destroy()
            await self.channel.delete()
            await self.tournament.to_channel.send(
                _(
                    ":information_source: **Automatic DQ** of {player1} and {player2} for "
                    "inactivity, the set #{set} is cancelled."
                ).format(player1=self.player1.mention, player2=self.player2.mention, set=self.set)
            )
            self.channel = None
            self.cancel()
            return
        for player in players:
            if player.spoke is False:
                log.debug(
                    f"[Guild {self.guild.id}] DQing player {player} "
                    f"for inactivity (set #{self.set})"
                )
                await player.destroy()
                await self.channel.send(
                    _(":timer: **Automatic DQ of {player} for inactivity.**").format(
                        player=player.mention
                    )
                )
                await self.tournament.to_channel.send(
                    _(
                        ":information_source: **Automatic DQ** of {player} "
                        "for inactivity, set #{set}."
                    ).format(player=player.mention, set=self.set)
                )
                try:
                    await player.send(
                        _(
                            "Sorry, you were disqualified from this tournament "
                            "because you weren't active in your channel. Contact the T.O. "
                            "if you believe this is a mistake."
                        )
                    )
                except discord.HTTPException:
                    # blocked or DMs not allowed
                    pass
                self.cancel()
                break

    async def end(self, player1_score: int, player2_score: int, upload: bool = True):
        """
        Set the score and end the match.
        """
        if upload is True:
            await self.set_scores(player1_score, player2_score)
        winner = self.player1 if player1_score > player2_score else self.player2
        score = (
            f"{player1_score}-{player2_score}"
            if player1_score > player2_score
            else f"{player2_score}-{player1_score}"
        )
        if self.channel is not None:
            await self.channel.send(
                _(
                    ":bell: __Score reported__ : **{winner}** wins **{score}** !\n"
                    "*In case of a problem, call a T.O. to fix the score.*\n"
                    "*Note : this channel will be deleted after 5 minutes of inactivity.*{remote}"
                ).format(
                    winner=winner.mention,
                    score=score,
                    remote=_("\n\n:information_source: The score was directly set on the bracket.")
                    if upload is False
                    else "",
                )
            )
        self.cancel()

    async def force_end(self):
        """
        Called when a set is cancelled (remove bracket modifications or reset).

        The channel is deleted, a DM is sent, and the instance will most likely be deleted soon
        after.
        """
        self.player1.reset()
        self.player2.reset()
        for player in (self.player1, self.player2):
            try:
                await player.send(
                    _(
                        ":warning: **Your set is cancelled!** This is probably because of "
                        "manual bracket modifications.\nCheck the bracket, and contact a T.O. "
                        "if you believe this is a problem."
                    )
                )
            except discord.HTTPException:
                pass
        if self.channel is not None:
            await self.channel.delete(
                reason=_(
                    "Remote returned a different match list, or the bracket was reset. I am "
                    "therefore clearing the outdated matches. Check the bracket for details."
                )
            )

    async def disqualify(self, player: Union[Participant, int]):
        """
        Called when a player in the set is destroyed.

        There is no API call, just messages sent to the players.
        """
        self.cancel()
        if isinstance(player, int):
            winner = self.player1 if self.player1 is not None else self.player2
            player = _("Player with ID {id} (lost on Discord) ").format(id=player)
        else:
            winner = self.player1 if self.player1.id != player.id else self.player2
            player = _("Player {player}").format(player=player.mention)
        if self.channel is not None:
            await self.channel.send(
                _(
                    "Player {player} was disqualified from the tournament.\n"
                    "{winner.mention} is winning this set!"
                ).format(player=player, winner=winner)
            )
        else:
            try:
                await winner.send(
                    _(
                        "Your opponent was disqualified from the tournament.\n"
                        "You are winning this set!"
                    )
                )
            except discord.HTTPException:
                pass

    async def forfeit(self, player: Participant):
        """
        Called when a player in the set forfeits this match.

        This doesn't always mean that the player quits the tournament, he may continue in the
        loser bracker.

        Sets a score of -1 0
        """
        if player.id == self.player1.id:
            score = (-1, 0)
        else:
            score = (0, -1)
        await self.set_scores(*score)
        self.cancel()
        winner = self.player1 if self.player1.id != player.id else self.player2
        if self.channel is not None:
            await self.channel.send(
                _(
                    "Player {player.mention} forfeits this set.\n{winner.mention} is winning!"
                ).format(player=player, winner=winner)
            )
        else:
            try:
                await winner.send(_("Your opponent forfeited.\nYou are winning this set!"))
            except discord.HTTPException:
                pass

    def cancel(self):
        with contextlib.suppress(AttributeError):
            self.player1.reset()
            self.player2.reset()
        self.status = "finished"
        self.end_time = datetime.utcnow()

    async def set_scores(
        self, player1_score: int, player2_score: int, winner: Optional[Participant] = None
    ):
        """
        Set the score for the set.

        Parameters
        ----------
        player1_score: int
            The score of the first player.
        player2_score: int
            The score of the second player.
        winner: Optional[Participant]
            The winner of the set. If not provided, the player with the highest score will be
            selected.
        """
        raise NotImplementedError

    async def mark_as_underway(self):
        """
        Marks the match as underway.
        """
        raise NotImplementedError

    async def unmark_as_underway(self):
        """
        Unmarks the match as underway.

        This shouldn't ever be needed, just here in case of.
        """
        raise NotImplementedError


class Tournament:
    def __init__(
        self,
        guild: discord.Guild,
        config: Config,
        name: str,
        game: str,
        url: str,
        id: str,
        limit: Optional[int],
        status: str,
        tournament_start: datetime,
        bot_prefix: str,
        data: dict,
    ):
        self.guild = guild
        self.data = config
        self.name = name
        self.game = game
        self.url = url
        self.id = id
        self.limit = limit
        self.status = status
        self.tournament_start = tournament_start
        self.bot_prefix = bot_prefix
        self.participants: List[Participant] = []
        self.matches: List[Match] = []
        self.streamers: List[Streamer] = []
        self.winner_categories: List[discord.CategoryChannel] = []
        self.loser_categories: List[discord.CategoryChannel] = []
        self.category: discord.CategoryChannel = guild.get_channel(
            data["channels"].get("category")
        )
        self.announcements_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("announcements")
        )
        self.checkin_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("checkin")
        )
        self.queue_channel: discord.TextChannel = guild.get_channel(data["channels"].get("queue"))
        self.register_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("register")
        )
        self.scores_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("scores")
        )
        self.stream_channel: discord.TextChannel = guild.get_channel(
            data["channels"].get("stream")
        )
        self.to_channel: discord.TextChannel = guild.get_channel(data["channels"].get("to"))
        self.participant_role: discord.Role = guild.get_role(data["roles"].get("participant"))
        self.streamer_role: discord.Role = guild.get_role(data["roles"].get("streamer"))
        self.to_role: discord.Role = guild.get_role(data["roles"].get("to"))
        self.delay: int = data["delay"]
        self.register: dict = data["register"]
        self.checkin: dict = data["checkin"]
        self.start_bo5: int = data["start_bo5"]
        if data["register"]["opening"] != 0:
            self.register_start: datetime = tournament_start - timedelta(
                hours=data["register"]["opening"]
            )
        else:
            self.register_start = None
        if data["register"]["closing"] != 0:
            self.register_stop: datetime = tournament_start - timedelta(
                minutes=data["register"]["closing"]
            )
        else:
            self.register_stop = None
        if data["checkin"]["opening"] != 0:
            self.checkin_start: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["opening"]
            )
        else:
            self.checkin_start = None
        if data["checkin"]["closing"] != 0:
            self.checkin_stop: datetime = tournament_start - timedelta(
                minutes=data["checkin"]["closing"]
            )
        else:
            self.checkin_stop = None
        self.ruleset_channel: discord.TextChannel = guild.get_channel(data["ruleset"])
        self.game_role = guild.get_role(data["role"])  # this is the role assigned to the game
        self.baninfo: str = data["baninfo"]
        self.ranking: dict = data["ranking"]
        self.stages: list = data["stages"]
        self.counterpicks: list = data["counterpicks"]
        self.phase = "pending"  # can be "pending" "register" "checkin" "ongoing" "finished"
        self.register_message: Optional[discord.Message] = None  # message being updated
        # loop task things
        self.task: Optional[asyncio.Task] = None
        self.task_errors = 0
        self.top_8 = {
            "winner": {"top8": None, "bo5": None},
            "loser": {"top8": None, "bo5": None},
        }
        self.debug_task = asyncio.get_event_loop().create_task(self.debug_loop_task())

    def __repr__(self):
        return (
            "<Tournament name={0.name} phase={0.phase} status={0.status} url={0.url} "
            "game={0.game} limit={0.limit} id={0.id} guild_id={0.guild.id}>"
        ).format(self)

    participant_object = Participant
    match_object = Match
    tournament_type = "base"  # should be "challonge", or "smash.gg"...

    @classmethod
    async def from_saved_data(
        cls, guild: discord.Guild, config: Config, data: dict, config_data: dict,
    ):
        tournament_start = datetime.utcfromtimestamp(int(data["tournament_start"]))
        participants = data["participants"]
        matches = data["matches"]
        streamers = data["streamers"]
        winner_categories = data["winner_categories"]
        loser_categories = data["loser_categories"]
        phase = data["phase"]
        del data["tournament_start"], data["participants"], data["matches"], data["streamers"]
        del data["winner_categories"], data["loser_categories"], data["phase"]
        del data["tournament_type"]
        tournament = cls(
            guild, config, **data, tournament_start=tournament_start, data=config_data
        )
        if type:
            tournament.type = type
        if phase == "ongoing":
            await tournament._get_top8()
        tournament.participants = list(
            filter(
                None,
                [
                    tournament.participant_object.from_saved_data(tournament, data)
                    for data in participants
                ],
            )
        )
        for data in matches:
            player1 = tournament.find_participant(player_id=data["player1"])[1]
            player2 = tournament.find_participant(player_id=data["player2"])[1]
            match = tournament.match_object.from_saved_data(tournament, player1, player2, data)
            if player1 is None and player2 is None:
                if match.channel:
                    await tournament.destroy_player(data["player1"])
                    await tournament.destroy_player(data["player2"])
                    await match.channel.delete()
                    await tournament.to_channel.send(
                        _(":information_source: Set {match} cancelled, both players left.").format(
                            set=match.set
                        )
                    )
                    continue
            stop = False
            for i, player in enumerate((player1, player2), start=1):
                if player is None:
                    await tournament.destroy_player(data[f"player{i}"])
                    await match.disqualify(data[f"player{i}"])
                    await tournament.to_channel.send(
                        _(
                            ":information_source: Set {set} finished, "
                            "player with ID {player} can't be found."
                        ).format(set=match.set, player=data[f"player{i}"])
                    )
                    stop = True
            if stop:
                continue
            tournament.matches.append(match)
        tournament.streamers = [Streamer.from_saved_data(tournament, x) for x in streamers]
        tournament.winner_categories = list(
            filter(None, [guild.get_channel(x) for x in winner_categories])
        )
        tournament.loser_categories = list(
            filter(None, [guild.get_channel(x) for x in loser_categories])
        )
        tournament.phase = phase
        return tournament

    def to_dict(self) -> dict:
        """Returns a dict ready for Config."""
        data = {
            "name": self.name,
            "game": self.game,
            "url": self.url,
            "id": self.id,
            "limit": self.limit,
            "status": self.status,
            "tournament_start": int(self.tournament_start.timestamp()),
            "bot_prefix": self.bot_prefix,
            "participants": [x.to_dict() for x in self.participants],
            "matches": [x.to_dict() for x in self.matches],
            "streamers": [x.to_dict() for x in self.streamers],
            "winner_categories": [x.id for x in self.winner_categories],
            "loser_categories": [x.id for x in self.loser_categories],
            "phase": self.phase,
            "tournament_type": self.tournament_type,
        }
        return data

    async def save(self):
        data = self.to_dict()
        await self.data.guild(self.guild).tournament.set(data)

    @property
    def allowed_roles(self):
        allowed_roles = []
        if self.to_role is not None:
            allowed_roles.append(self.to_role)
        if self.streamer_role is not None:
            allowed_roles.append(self.streamer_role)
        return allowed_roles

    async def _get_available_category(self, dest: str):
        position = self.category.position + 1 if self.category else len(self.guild.categories)
        if dest == "winner":
            categories = self.winner_categories
        else:
            categories = self.loser_categories
        try:
            return next(filter(lambda x: len(x.channels) < 50, categories))
        except StopIteration:
            if categories:
                position = categories[-1].position + 1
            else:
                position += 1
            if dest == "winner":
                name = "Winner bracket"
            else:
                name = "Loser bracket"
            channel = await self.guild.create_category(
                name, reason=_("New category of sets."), position=position
            )
            if dest == "winner":
                self.winner_categories.append(channel)
            else:
                self.loser_categories.append(channel)
            return channel

    async def _clear_categories(self):
        categories = self.winner_categories + self.loser_categories
        for category in categories:
            try:
                await category.delete()
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {self.guild.id}] Can't delete category {category} "
                    "(_clear_categories was called).",
                    exc_info=e,
                )
        self.winner_categories = []
        self.loser_categories = []

    async def _get_top8(self):
        # if you're wondering how this works, well I have no idea :D
        # this was mostly taken from the original bot this cog is based on, ATOS by Wonderfall
        # https://github.com/Wonderfall/ATOS/blob/master/bot.py#L1355-L1389
        rounds = await self._get_all_rounds()
        top8 = self.top_8
        # calculate top 8
        top8["winner"]["top8"] = max(rounds) - 2
        top8["loser"]["top8"] = min(rounds) + 2
        # minimal values, in case of a small tournament
        if top8["winner"]["top8"] < 1:
            top8["winner"]["top8"] = 1
        if top8["loser"]["top8"] > -1:
            top8["loser"]["top8"] = -1
        # calculate bo5 start
        if self.start_bo5 > 0:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5 - 1
        elif self.start_bo5 in (0, 1):
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5
        else:
            top8["winner"]["bo5"] = top8["winner"]["top8"] + self.start_bo5 + 1
        if self.start_bo5 > 1:
            top8["loser"]["bo5"] = min(rounds)  # top 3 is loser final anyway
        else:
            top8["loser"]["bo5"] = top8["loser"]["top8"] - self.start_bo5
        # avoid aberrant values
        if top8["winner"]["bo5"] > max(rounds):
            top8["winner"]["bo5"] = max(rounds)
        if top8["winner"]["bo5"] < 1:
            top8["winner"]["bo5"] = 1
        if top8["loser"]["bo5"] < min(rounds):
            top8["loser"]["bo5"] = min(rounds)
        if top8["loser"]["bo5"] > -1:
            top8["loser"]["bo5"] = -1

    def find_participant(
        self, *, player_id: Optional[str] = None, discord_id: Optional[int] = None
    ) -> Tuple[int, Participant]:
        if player_id:
            try:
                return next(
                    filter(lambda x: x[1].player_id == player_id, enumerate(self.participants))
                )
            except StopIteration:
                return None, None
        elif discord_id:
            try:
                return next(filter(lambda x: x[1].id == discord_id, enumerate(self.participants)))
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either player_id or discord_id")

    def find_match(
        self,
        *,
        match_id: Optional[int] = None,
        match_set: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> Tuple[int, Match]:
        if match_id:
            try:
                return next(filter(lambda x: x[1].id == match_id, enumerate(self.matches)))
            except StopIteration:
                return None, None
        elif match_set:
            try:
                return next(filter(lambda x: x[1].set == match_set, enumerate(self.matches)))
            except StopIteration:
                return None, None
        elif channel_id:
            try:
                return next(
                    filter(
                        lambda x: x[1].channel and x[1].channel.id == channel_id,
                        enumerate(self.matches),
                    )
                )
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either match_id, match_set or channel_id")

    def find_streamer(
        self, *, channel: Optional[str] = None, discord_id: Optional[int] = None
    ) -> Tuple[int, Streamer]:
        if channel:
            try:
                return next(filter(lambda x: x[1].channel == channel, enumerate(self.streamers)))
            except StopIteration:
                return None, None
        elif discord_id:
            try:
                return next(
                    filter(lambda x: x[1].member.id == discord_id, enumerate(self.streamers))
                )
            except StopIteration:
                return None, None
        raise RuntimeError("Provide either channel or discord_id")

    async def register_participant(self, member: discord.Member):
        await member.add_roles(self.participant_role, reason=_("Registering to tournament."))
        participant = self.participant_object(member, self)
        if self.phase == "checkin":
            # registering during check-in, count as already checked
            participant.checked_in = True
        self.participants.append(participant)
        log.debug(f"[Guild {self.guild.id}] Player {member} registered.")

    async def send_start_messages(self):
        scores_channel = (
            _(" in {channel}").format(channel=self.scores_channel.mention)
            if self.scores_channel
            else ""
        )
        messages = {
            self.announcements_channel: _(
                "The tournament **{tournament}** has started! Bracket: {bracket}\n"
                ":white_small_square: You can access it "
                "anytime with the `{prefix}bracket` command.\n"
                ":white_small_square: You can check the current "
                "streams with the `{prefix}streams` command.\n\n"
                "{participant} Please read the instructions :\n"
                "{queue_channel}"
                "{rules_channel}"
                ":white_small_square: The winner of a set must report the score **as soon as "
                "possible**{scores_channel} with the `{prefix}win` command.\n"
                ":white_small_square: You can disqualify from the tournament with the "
                "`{prefix}dq` command, or just abandon your current set with the `{prefix}ff` "
                "command.\n"
                ":white_small_square: In case of lag making the game unplayable, use the `{prefix}"
                "lag` command to call the T.O.\n"
                "{delay}."
            ).format(
                tournament=self.name,
                bracket=self.url,
                participant=self.participant_role.mention,
                queue_channel=_(
                    ":white_small_square: Your sets are announced in {channel}.\n"
                ).format(channel=self.queue_channel.mention)
                if self.queue_channel
                else "",
                rules_channel=_(
                    ":white_small_square: The ruleset is available in {channel}.\n"
                ).format(channel=self.ruleset_channel.mention)
                if self.ruleset_channel
                else "",
                scores_channel=scores_channel,
                delay=_(
                    ":timer: **You will automatically be disqualified if you don't talk in your "
                    "channel within the first {delay} minutes.**"
                ).format(delay=self.delay)
                if self.delay != 0
                else "",
                prefix=self.bot_prefix,
            ),
            self.scores_channel: _(
                ":information_source: Management of the scores for the "
                "tournament **{tournament}** is automated:\n"
                ":white_small_square: Only **the winner of the set** "
                "sends his score with the `{prefix}win` command.\n"
                ":white_small_square: You must follow this "
                "format: `{prefix}win 2-0, 3-2, 3-1, ...`.\n"
                ":white_small_square: Look at the bracket to **check** the informations: {url}\n"
                ":white_small_square: In case of a wrong input, contact a T.O. for a manual fix."
            ).format(tournament=self.name, url=self.url, prefix=self.bot_prefix),
            self.queue_channel: _(
                ":information_source: **Set launch is automated.** "
                "Please follow the instructions in this channel.\n"
                ":white_small_square: Any streamed set will be "
                "announced here, and in your channel.\n"
                ":white_small_square: Any BO5 set will be precised here and in your channel.\n"
                ":white_small_square: The player beginning the bans is picked and "
                "annonced in your channel (you can also use `{prefix}flip`).\n\n"
                ":timer: **You will be disqualified if you were not active in your channel** "
                "within the {delay} first minutes after the set launch."
            ).format(delay=self.delay, prefix=self.bot_prefix),
        }
        for channel, message in messages.items():
            if channel is None:
                continue
            try:
                await channel.send(message)
            except discord.HTTPException as e:
                log.error(f"[Guild {self.guild.id}] Can't send message in {channel}.", exc_info=e)

    def _prepare_register_message(self):
        def format_datetime(date: datetime, only_time=False):
            date = format_date(date, format="full", locale=locale)
            time = format_time(date, format="short", locale=locale)
            if only_time:
                return time
            return _("{date} at {time}").format(date=date, time=time)

        locale = get_babel_locale()
        if self.checkin_start:
            checkin = _(":white_small_square: __Check-in:__ From {begin} to {end}\n").format(
                begin=format_datetime(self.checkin_start, True),
                end=format_datetime(self.checkin_stop or self.tournament_start, True),
            )
        else:
            checkin = ""
        if self.limit:
            limit = _("{registered}/{limit} participants registered").format(
                registered=len(self.participants), limit=self.limit
            )
        else:
            limit = _("{registered} participants registered *(no limit set)*").format(
                registered=len(self.participants)
            )
        if self.ruleset_channel:
            ruleset = _(":white_small_square: __Ruleset:__ See {channel}\n").format(
                channel=self.ruleset_channel.mention
            )
        else:
            ruleset = ""
        return _(
            "**{t.name}** | *{t.game}*\n\n"
            ":white_small_square: __Date:__ {date}\n"
            ":white_small_square: __Register:__ Closing at {time}\n"
            "{checkin}"
            ":white_small_square: __Participants:__ {limit}\n"
            ":white_small_square: __Bracket:__ {t.url}\n"
            "{ruleset}\n"
            "You can register/unregister to this tournament with "
            "the `{t.bot_prefix}in` and `{t.bot_prefix}out` commands.\n"
            "*Note: your Discord username will be used in the bracket.*"
        ).format(
            t=self,
            date=format_datetime(self.tournament_start),
            time=format_datetime(self.register_stop or self.tournament_start, True),
            checkin=checkin,
            limit=limit,
            ruleset=ruleset,
        )

    async def send_register_message(self):
        self.register_message = await self.register_channel.send(self._prepare_register_message())

    async def launch_sets(self):
        match: Match
        coros = []
        # islice will limit the output to 20. see this as list[:20] but with a generator
        for match in islice(
            filter(lambda x: x.status == "pending" and x.channel is None, self.matches), 20
        ):
            # we get the category in the iteration instead of the gather
            # because if all functions call _get_available_category at the same time,
            # a new category will be returned for each
            category = await self._get_available_category("winner" if match.round > 0 else "loser")
            coros.append(match.launch(category=category))
        results = await asyncio.gather(*coros, return_exceptions=True)
        for result in filter(None, results):
            log.error(f"[Guild {self.guild.id}] Can't launch a set.", exc_info=result)

    def update_streamer_list(self):
        for streamer in self.streamers:
            streamer._update_list()

    async def launch_streams(self):
        match: Match
        for match in filter(lambda x: x.streamer and x.on_hold, self.matches):
            if match.streamer.current_match.id == match.id:
                await match.start_stream()

    async def check_for_channel_timeout(self):
        match: Match
        for i, match in filter(
            lambda x: x[1].status != "pending" and x[1].channel is not None,
            enumerate(self.matches),
        ):
            if match.status == "ongoing":
                if (
                    not match.checked_dq
                    and (match.start_time + timedelta(minutes=self.delay)) < datetime.utcnow()
                ):
                    log.debug(f"Checking inactivity for match {match.set}")
                    await match.check_inactive()
            elif match.status == "finished":
                if match.channel and (match.end_time + timedelta(minutes=5)) < datetime.utcnow():
                    log.debug(f"Checking deletion for match {match.set}")
                    await match.channel.delete(reason=_("5 minutes passed after set end."))
                    del self.matches[i]

    async def warn_bracket_change(self, *sets):
        await self.to_channel.send(
            _(
                ":information_source: Changes were detected on the upstream bracket.\n"
                "This may result in multiple sets ending, relaunch or cancellation.\n"
                "Affected sets: {sets}"
            ).format(sets=", ".join([f"#{x}" for x in sets]))
        )

    @tasks.loop(seconds=15)
    async def loop_task(self):
        try:
            await self._update_participants_list()
            await self._update_match_list()
            self.update_streamer_list()
        except Exception as e:
            log.error(
                f"[Guild {self.guild.id}] Can't update internal match and participant list! "
                "This may be an error from the upstream bracket, or the bot failed when "
                "checking for changes.",
                exc_info=e,
            )
            self.task_errors += 1
            return
        coros = [self.launch_sets(), self.check_for_channel_timeout()]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for i, result in enumerate(results):
            if result is None:
                continue
            log.warning(f"[Guild {self.guild.id}] Failed with coro {coros[i]}.", exc_info=result)
        try:
            await self.launch_streams()
        except Exception as e:
            log.error(f"[Guild {self.guild.id}] Can't update streams.", exc_info=e)
            self.task_errors += 1
        # saving is done after all of our jobs, so the data shouldn't move too much
        await self.save()

    @loop_task.error
    async def on_loop_task_error(self, exception):
        self.task_errors += 1
        if self.task_errors >= MAX_ERRORS:
            log.critical(
                f"[Guild {self.guild.id}] Error in loop task. 3rd error, cancelling the task",
                exc_info=exception,
            )
        else:
            log.error(
                f"[Guild {self.guild.id}] Error in loop task. Resuming...", exc_info=exception
            )
            self.start_loop_task()

    def start_loop_task(self):
        self.task = self.loop_task.start()

    def stop_loop_task(self):
        self.loop_task.cancel()

    def _debug_dump(self):
        file = open(cog_data_path(raw_name="Tournaments") / "debug.txt", "w+")
        content = ""
        m: Match
        for i, m in enumerate(self.matches):
            if m.start_time and m.checked_dq is False:
                time_until_dq_check = (
                    m.start_time + timedelta(minutes=self.delay)
                ) - datetime.utcnow()
            else:
                time_until_dq_check = None
            if m.end_time:
                time_until_delete = (m.end_time + timedelta(minutes=5)) - datetime.utcnow()
            else:
                time_until_delete = None
            content += (
                f"----- MATCH {i} -----\n"
                f"status={m.status} round={m.round} set={m.set} id={m.id}\n"
                f"start_time={m.start_time.strftime('%H:%M:%S') if m.start_time else None} "
                f"end_time={m.end_time.strftime('%H:%M:%S') if m.end_time else None} "
                f"underway={m.underway} channel={m.channel.id if m.channel else None}\n"
                f"checked_dq={m.checked_dq} time_until_dq_check={time_until_dq_check} "
                f"time_until_delete={time_until_delete}\n"
                f"player1= name={m.player1} player_id={m.player1.player_id} spoke="
                f"{m.player1.spoke} discord_id={m.player1.id}\n"
                f"player1= name={m.player2} player_id={m.player2.player_id} spoke="
                f"{m.player2.spoke} discord_id={m.player2.id}\n\n"
            )
        content += "\n\n\n"
        s: Streamer
        for i, s in enumerate(self.streamers):
            content += (
                f"----- STREAMER {i} -----\n"
                f"link={s.link} room_id={s.room_id} room_code={s.room_code}\n"
                f"member={s.member}\n"
                f"current_match={s.current_match}\n"
                f"matches={s.matches}\n\n"
            )
        content += "\n\n\n"
        p: Participant
        for i, p in enumerate(self.participants):
            content += (
                f"----- PARTICIPANT {i} -----\n"
                f"name={p} id={p.id} player_id={p.player_id}\n"
                f"match_set={p.match.set if p.match else None} match_id="
                f"{p.match.id if p.match else None} spoke={p.spoke}\n\n"
            )
        file.write(content)
        file.close()

    async def debug_loop_task(self):

        while True:
            self._debug_dump()
            await asyncio.sleep(1)

    async def _get_all_rounds(self) -> List[int]:
        """
        Return a list of all rounds in the bracket. This is used to determine the top 8.

        This is a new method because our Match class will not be created without players, so
        we add this new method which only fetch what we need.

        Returns
        -------
        List[int]
            The list of rounds.
        """
        raise NotImplementedError

    async def _update_participants_list(self):
        """
        Updates the internal list of participants, checking for changes such as:

        *   Player DQ/removal
        *   New player added (pre game)

        .. warning:: A name change on remote is considered as a player removal + addition. If the
            name doesn't match any member, he will be rejected.
        """
        raise NotImplementedError

    async def _update_match_list(self):
        """
        Updates the internal list of changes, checking for changes such as:

        *   Score set manually

        *   Score modified (if there are ongoing/finished sets beyond this match in the bracket,
            they will be reset)

        *   Match reset (the set will be relaunched, ongoing/finished sets beyond this match in
            the bracket will be reset)
        """
        raise NotImplementedError

    async def start(self):
        """
        Starts the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already started.
        """
        raise NotImplementedError

    async def stop(self):
        """
        Stops the tournament.

        Raises
        ------
        RuntimeError
            The tournament is already stopped or not started.
        """
        raise NotImplementedError

    async def add_participant(self, name: str, seed: Optional[int] = None):
        """
        Adds a participant to the tournament.

        Parameters
        ----------
        name: str
            The name of the participant
        seed: int
            The participant's new seed. Must be between 1 and the current number of participants
            (including the new record). Omit to place at the bottom.
        """
        raise NotImplementedError

    async def add_participants(self, *participants: str):
        """
        Adds a list of participants to the tournament, ordered as you want them to be seeded.

        Parameters
        ----------
        participants: List[str]
            The list of participants. The first element will be seeded 1.
        """
        raise NotImplementedError

    async def destroy_player(self, player_id: str):
        """
        Destroys a player. This is the same call as Player.destroy, but only the player ID is
        needed. Useful for unavailable discord member.

        Parameters
        ----------
        player_id: str
            The player to remove.
        """

    async def list_participants(self) -> List[Participant]:
        """
        Returns the list of participants from the tournament host.

        Returns
        -------
        List[str]
            The list of participants.
        """
        raise NotImplementedError

    async def list_matches(self) -> List[Match]:
        """
        Returns the list of matches from the tournament host.

        Returns
        -------
        List[str]
            The list of matches.
        """
        raise NotImplementedError

    async def reset(self):
        """
        Resets the bracket.
        """
        raise NotImplementedError


class Streamer:
    """
    Represents a streamer in the tournament. Will be assigned to matches. Does not necessarily
    exists on remote depending on the provider.
    """

    def __init__(
        self,
        tournament: Tournament,
        member: discord.Member,
        channel: str,
        respect_order: bool = False,
    ):
        self.tournament = tournament
        self.member = member
        self.channel = channel
        self.respect_order = respect_order
        self.link = f"https://www.twitch.tv/{channel}/"
        self.room_id = None
        self.room_code = None
        self.matches: List[Union[Match, int]] = []
        self.current_match: Optional[Match] = None

    @classmethod
    def from_saved_data(cls, tournament: Tournament, data: dict):
        guild = tournament.guild
        member = guild.get_member(data["member"])
        if member is None:
            raise RuntimeError("Streamer member lost.")
        cls = cls(tournament, member, data["channel"], data["respect_order"])
        cls.room_id = data["room_id"]
        cls.room_code = data["room_code"]
        cls.matches = list(
            filter(None, [tournament.find_match(match_set=x)[1] or x for x in data["matches"]])
        )
        if data["current_match"]:
            cls.current_match = tournament.find_match(match_set=data["current_match"])[1]
            if cls.current_match is not None:
                cls.current_match.streamer = cls
        return cls

    def to_dict(self) -> dict:
        return {
            "member": self.member.id,
            "channel": self.channel,
            "respect_order": self.respect_order,
            "room_id": self.room_id,
            "room_code": self.room_code,
            "matches": [self.get_set(x) for x in self.matches],
            "current_match": self.current_match.id if self.current_match else None,
        }

    def get_set(self, x):
        return x.set if hasattr(x, "set") else x

    def __str__(self):
        return self.link

    def set_room(self, room_id: str, code: Optional[str] = None):
        self.room_id = room_id
        self.room_code = code

    def add_matches(self, *sets: int):
        errors = {}
        for _set in sets:
            if _set in [self.get_set(x) for x in self.matches]:
                errors[_set] = _("You already have that set in your queue.")
                continue
            for streamer in self.tournament.streamers:
                if _set in [self.get_set(x) for x in streamer.matches]:
                    errors[_set] = _(
                        "That set already has a streamer defined *(<{streamer}>)*."
                    ).format(streamer=streamer)
                    continue
            match = self.tournament.find_match(match_set=str(_set))[1]
            if match:
                if match.status == "ongoing":
                    errors[_set] = _("That match is already ongoing.")
                    continue
                elif match.status == "finished":
                    errors[_set] = _("That match is finished.")
                    continue
                match.streamer = self
            self.matches.append(match or _set)
        return errors

    def remove_matches(self, *sets: int):
        new_list = [x for x in self.matches if self.get_set(x) not in sets]
        if len(new_list) == len(self.matches):
            raise KeyError("None of the given sets found.")
        else:
            self.matches = new_list

    def swap_match(self, set1: str, set2: str):
        try:
            i1, match1 = next(enumerate(filter(lambda x: set1 == self.get_set(x), self.matches)))
            i2, match2 = next(enumerate(filter(lambda x: set2 == self.get_set(x), self.matches)))
        except StopIteration as e:
            raise KeyError("One set not found.") from e
        self.matches[i1] = match2
        self.matches[i2] = match1

    async def end(self):
        for match in filter(lambda x: isinstance(x, Match), self.matches):
            await match.cancel_stream()

    def _update_list(self):
        matches = []
        for match in self.matches:
            if isinstance(match, Match):
                matches.append(match)
                continue
            match_object = self.tournament.find_match(match_set=str(match))[1]
            if match_object:
                if match_object.status != "pending":
                    continue
                match_object.streamer = self
                match_object.on_hold = True
                matches.append(match_object)
            else:
                matches.append(match)
        self.matches = matches
        if self.current_match:
            if self.current_match.status != "finished":
                return  # wait for it to end
            self.matches.remove(self.current_match)
        self.current_match = None
        try:
            next_match = self.matches[0]
        except IndexError:
            return
        if isinstance(next_match, int):
            return
        self.current_match = next_match