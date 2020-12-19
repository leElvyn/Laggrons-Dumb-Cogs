import discord
import logging
import asyncio

from redbot.core.i18n import Translator, cog_i18n

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Templates():
    """
    this class is used to store and generate messages.
    it has to be initiallized at the bot init, and must be passed onto every objects that has user messages
    each method represent a template, and each method will return a formated string, or discord.Embed 

    Sometimes, it is easier to just pass the self object of the class calling the method. It is then refeared as ctxSelf

    #WILL BE IMPLEMENTED SOON :

    user can set their own messages. The message method will check when called if the config entry for the message is blank.
    If it is, it uses the default message template. If it isn't, it will format the stored value.
    User will be able to set either a message, either use json embed data. 
    I have no idea how to format a pre-existing string, and probably already escaped
    """

    def __init__(self, bot, data):
        self.data = data

    def tournaments_tournamentsinfo(self, ctxSelf):
        return _(
                "Laggron's Dumb Cogs V3 - tournaments\n\n"
                "Version: {0.__version__}\n"
                "Authors: {0.__author__[0]}, {0.__author__[1]} and {0.__author__[2]}\n\n"
                "Github repository: https://github.com/retke/Laggrons-Dumb-Cogs/tree/v3\n"
                "Discord server: https://discord.gg/AVzjfpR\n"
                "Documentation: http://laggrons-dumb-cogs.readthedocs.io/\n"
                "Help translating the cog: https://crowdin.com/project/laggrons-dumb-cogs/\n\n"
                "Support my work on Patreon: https://www.patreon.com/retke"
            ).format(ctxSelf)
    
    def base_send_message(self, ctxSelf, reset):
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
        if self.streamer is not None and self.on_hold is True:
            message += _(
                "**\nYou will be on stream on {streamer}!**\n"
                ":warning: **Do not play your set for now and wait for your turn.** "
                "I will send a message once it is your turn with instructions."
            ).format(streamer=self.streamer.link)
            # else, we're about to send another message with instructions

        async def send_in_dm():
            nonlocal message
            message += _(
                "\n\n**You channel can't be created because of a problem. "
                "Do your set in DM and come back to set the result.**"
            )
            await self._dm_players(message)

        if self.channel is None:
            await send_in_dm()
            result = False
        else:
            try:
                await self.channel.send(message)
            except discord.HTTPException as e:
                log.error(
                    f"[Guild {self.guild.id}] Can't create a channel for the set {self.set}",
                    exc_info=e,
                )
                await send_in_dm()
                result = False
            else:
                result = True
        self.tournament.matches_to_announce.append(
            _(
                ":arrow_forward: **{name}** ({bo_type}): {player1} vs {player2}"
                "{on_stream} {top8} {channel}."
            ).format(
                name=self.round_name,
                bo_type=_("BO5") if self.is_bo5 else _("BO3"),
                player1=self.player1.mention,
                player2=self.player2.mention,
                on_stream=_(" **on stream!**") if self.streamer else "",
                top8=top8,
                channel=_("in {channel}").format(channel=self.channel.mention)
                if result is True
                else _("in DM"),
            )
        )
        return result

template = None
#blank object to import it befor it is created