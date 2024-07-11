from aiida.engine import WorkChain, append_
from aiida.plugins.factories import CalculationFactory

SomeOtherWorkChain = CalculationFactory('some.module')


class SomeWorkChain(WorkChain):
    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.outline(
            cls.submit_workchains,
            cls.inspect_workchains,
        )

    def submit_workchains(self):
        for i in range(3):
            future = self.submit(SomeOtherWorkChain)
            self.to_context(workchains=append_(future))

    def inspect_workchains(self):
        for workchain in self.ctx.workchains:
            assert workchain.is_finished_ok
