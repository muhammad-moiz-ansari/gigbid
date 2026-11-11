from agent.nodes.workflow import Nodes
from tests.support import TestModels


class WarningModel(TestModels):
    async def complete(self, node, data, schema):
        result, usage = await super().complete(node, data, schema)
        if node == "compliance":
            result = {"passed": False, "reasons": ["Claim may be fabricated"]}
        return result, usage


def state(text):
    return {"draft": {"text": text, "screening_answers": {}}, "critique": {"passed": True}}


async def test_model_concerns_are_warnings_not_blocks():
    result = await Nodes(None, WarningModel()).compliance(state("I would test the API."))
    assert result["status"] == "running" and result["compliance"]["passed"]
    assert result["compliance"]["warnings"] == ["Claim may be fabricated"]


async def test_rule_violations_still_block():
    result = await Nodes(None, TestModels()).compliance(state("I would test the API and guarantee success."))
    assert result["status"] == "blocked" and "guarantee" in result["compliance"]["reasons"]
    assert result["compliance"]["warnings"] == []
