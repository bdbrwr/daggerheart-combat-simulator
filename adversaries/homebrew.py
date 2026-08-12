"""Our own adversaries - anything not out of a published book.

Same shape as srd.py: an Adversary literal per adversary, named whatever we
named it. The registry picks these up automatically, so a new one is usable
from an encounter the moment it's written here - nothing to register, no
import path for an encounter to know.

Names have to be unique across every module in this package, since that's what
encounters look them up by. Reusing a published adversary's name to mean a
tweaked version is the one thing not to do here: an encounter override is the
way to change a published stat block's numbers, which keeps srd.py matching the
book. Homebrew is for adversaries that don't exist in a book at all.
"""
