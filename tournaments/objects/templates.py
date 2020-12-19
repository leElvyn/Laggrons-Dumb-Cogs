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
    
    def challonge():
        pass

template = None
#blank object to import it befor it is created