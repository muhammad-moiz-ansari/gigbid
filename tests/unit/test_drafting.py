from agent.nodes.workflow import Nodes
from tests.support import TestModels


class SkippingWriter(TestModels):
    calls = []

    async def complete(self, node, data, schema):
        self.calls.append(node)
        result, usage = await super().complete(node, data, schema)
        if node == "writer":
            result["screening_answers"] = {}
        return result, usage


async def test_writer_asks_separately_for_missing_screening_answers():
    model = SkippingWriter()
    state = {"tenant": "t", "job_spec": {"screening_questions": ["How will you test?"]},
             "fit": {"evidence": []}, "price": {}, "draft": {}}
    result = await Nodes(None, model).writer(state)
    assert model.calls == ["writer", "answer"] and len(result["usage"]) == 2
    assert result["draft"]["screening_answers"] == {"How will you test?": "I would test each requirement."}


def test_every_configured_node_has_a_prompt():
    from agent.model import config, prompt
    for node in config()["profiles"]["open"]["nodes"]:
        assert prompt(node).startswith("Version")
