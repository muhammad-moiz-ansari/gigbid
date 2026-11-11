"""Job categories from skills (configured in config.yaml); used by outcome memory and analytics."""
from agent.model import config


def category(skills):
    wanted = {skill.casefold() for skill in skills}
    best, score = "other", 0
    for name, words in config()["categories"].items():
        overlap = len(wanted & {word.casefold() for word in words})
        if overlap > score:
            best, score = name, overlap
    return best
