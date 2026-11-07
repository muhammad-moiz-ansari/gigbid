from agent.marketplace_port import Capabilities, Unavailable


class GigSimAdapter:
    capabilities = Capabilities()

    def __getattr__(self, name):
        def unavailable(*args, **kwargs):
            raise Unavailable("Official GigSim contract is missing; adapter mapping is not implemented")
        return unavailable
