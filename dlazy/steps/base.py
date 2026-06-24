from abc import ABC, abstractmethod


class Step(ABC):
    name: str = ""
    type: str = ""

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    @abstractmethod
    def prepare(self):
        """Return list of dpdispatcher Task, or empty list if nothing to do."""

    @abstractmethod
    def collect(self):
        """Post-process after all tasks finish. Update ctx."""
