"""Custom logging filter for PINT using `loguru`

If you want to customize more of this yourself (e.g., in a script)
the minimal pieces would be:

from loguru import logger as log




If you want to include custom filtering and other elements:

from loguru import logger as log
import pint.logging

logfilter = pint.logging.LogFilter()
log.remove()
log.add(sys.stderr, level=level, filter=logfilter, format=format, colorize=True)


Note that `loguru` does not allow you to change the properties of an existing logger.
Instead it's better to remove it and make another (e.g., if you want to change the level)

Defaults can be changed with environment variables like:
$LOGURU_LEVEL
$LOGURU_FORMAT
$LOGURU_DEBUG_COLOR
"""

import os
import re
import sys
import warnings
from loguru import logger as log

__all__ = [
    "LogFilter",
]

# defaults can be overridden using $LOGURU_LEVEL and $LOGURU_FORMAT
# default for an individual level can be overridden by $LOGURU_DEBUG_COLOR etc
# or just make a new logger
level = "INFO"
# default level for scripts
script_level = "WARNING"
# a full format that might be useful as a reference:
# format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"
format = "<level>{level: <8}</level> ({name: <30}): <level>{message}</level>"
debug_color = "<fg #b790d4><bold>"
# Other formatting:
# https://loguru.readthedocs.io/en/stable/api/logger.html#color

"""
Want loguru to capture warnings emitted by warnings.warn
See https://loguru.readthedocs.io/en/stable/resources/recipes.html#capturing-standard-stdout-stderr-and-warnings
"""
warn_ = warnings.warn


def warn(message, *args, **kwargs):
    if len(args) > 0:
        log.warning(f"{args[0]} {message}")
    elif "category" in kwargs:
        log.warning(f"{kwargs['category']} {message}")
    else:
        log.warning(f"{message}")
    warn_(message, *args, **kwargs)


warnings.warn = warn


class LogFilter:
    """Custom logging filter for loguru.
    Define some messages that are never seen (e.g., Deprecation Warnings).
    Others that will only be seen once.  Filtering of those is done on the basis of regex"""

    def __init__(self, onlyonce=None, never=None):
        """
        Define regexs for messages that will only be seen once.  Use "\S+" for a variable that might change
        If a message comes through with a new value for that variable, it will be seen
        Make sure to escape other regex commands like ()
        Each message starts with state = False
        Once it has been emitted, that changes to a list of the messages so that it can keep track
        These are only suppressed when issued at level INFO or lower (e.g., WARNINGs will always come through)

        They should be defined as:
        "Error message": False
        where the `False` tracks whether or not the message has been issued at all

        Parameters
        ----------
        onlyonce : list, optional
            list of messages that should only be issued once if at WARNING or below
        never : list, optional
            list of messages that should never be seen
        """
        self.onlyonce = {
            "Using EPHEM = \S+ for \S+ calculation": False,
            "Using CLOCK = \S+ from the given model": False,
            "Using PLANET_SHAPIRO = \S+ from the given model": False,
            "Applying clock corrections \(include_gps = \S+, include_bipm = \S+\)": False,
            "Applying observatory clock corrections.": False,
            "Applying GPS to UTC clock correction \(\~few nanoseconds\)": False,
            "Computing \S+ columns.": False,
            "Using EPHEM = \S+ for \S+ calculation.": False,
            "Planet PosVels will be calculated.": False,
            "Computing PosVels of observatories, Earth and planets, using \S+": False,
            "Computing PosVels of observatories and Earth, using \S+": False,
            "Set solar system ephemeris to \S+": False,
            "Adding column \S+": False,
            "Adding columns .*": False,
            "Applying TT\(\S+\) to TT\(\S+\) clock correction \(\~27 us\)": False,
            "No pulse number flags found in the TOAs": False,
            "SSB obs pos \[\S+ \S+ \S+\] m": False,
            "Column \S+ already exists. Removing...": False,
            "Skipping Shapiro delay for Barycentric TOAs": False,
            "Special observatory location. No clock corrections applied.": False,
        }
        # add in any more defined on init
        if onlyonce is not None:
            for m in onlyonce:
                self.onlyonce[m] = False
        # List of matching strings for messages never to be displayed
        self.never = [
            "MatplotlibDeprecationWarning",
            "DeprecationWarning",
            "ProvisionalCompleterWarning",
        ]
        # add in any more defined on init
        if never is not None:
            self.never += never

    def filter(self, record):
        """Filter the record based on record["message"] and record["level"]
        If this returns False, the message is not seen

        Parameters
        ----------
        record : dict
            should contain record["message"] and record["level"]

        Returns
        -------
        bool
            If True, message is seen.  If False, message is not seen
        """
        for m in self.never:
            if m in record["message"]:
                return False
        # display all warnings and above
        if record["level"].no >= log.level("WARNING").no:
            return True
        for m in self.onlyonce:
            if re.match(m, record["message"]):
                if not self.onlyonce[m]:
                    self.onlyonce[m] = [record["message"]]
                    return True
                elif not (record["message"] in self.onlyonce[m]):
                    self.onlyonce[m].append(record["message"])
                    return True
                return False
        return True

    def __call__(self, record):
        return self.filter(record)


# you can modify this instance to change the messages that are never seen/only seen once
logfilter = LogFilter()

# remove the default logger so we can put in one with a custom filter
# this can be done elsewhere if more/different customization is needed
log.remove()
# Keep these here to see what is set at the enrivonment level
# again, this isn't needed by default but if you are setting these explicitly
# then it can be good to check
if "LOGURU_LEVEL" in os.environ:
    level = os.environ["LOGURU_LEVEL"]
if "LOGURU_FORMAT" in os.environ:
    format = os.environ["LOGURU_FORMAT"]

# use colorize=True to force colors
# otherwise the default selection turns them off e.g., for a Jupyter notebook
# since it isn't a tty
log.add(sys.stderr, level=level, filter=logfilter, format=format, colorize=True)
# change default DEBUG color
log.level("DEBUG", color=debug_color)