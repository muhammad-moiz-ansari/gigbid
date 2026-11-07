from agent.marketplace_port import Capabilities, Unavailable


class UpworkAdapter:
    """Fail closed. No guessed tool names, OAuth registration or live side effects."""
    capabilities = Capabilities()

    def __getattr__(self, name):
        def unavailable(*args, **kwargs):
            raise Unavailable("Upwork OAuth and capability mappings await verified contract and authorization")
        return unavailable
