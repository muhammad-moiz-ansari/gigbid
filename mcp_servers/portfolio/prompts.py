import json

from agent.model import prompt


def screening(question):
    return prompt("screening") + "\n" + json.dumps({"untrusted_question": question})


def summary(skill):
    return prompt("portfolio_summary") + "\n" + json.dumps({"untrusted_skill": skill})
