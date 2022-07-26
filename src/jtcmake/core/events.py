from .rule import Event, IRule

class RuleEvent(Event):
    def __init__(self, rule):
        super().__init__()
        self._rule = rule

    @property
    def rule(self):
        return self._rule


    def __repr__(self):
        return f'{type(self).__name__}({self.rule})'


class ErrorRuleEvent(RuleEvent):
    def __init__(self, rule, err: Exception):
        super().__init__(rule)
        self._error = err

    @property
    def err(self):
        return self._error


    def __repr__(self):
        return f'{type(self).__name__}(rule={self.rule}, err={self.err})'


class Skip(RuleEvent):
    def __init__(self, rule, is_direct_target):
        super().__init__(rule)
        self.is_direct_target = is_direct_target

class Start(RuleEvent): ...

class Done(RuleEvent): ...

class DryRun(RuleEvent): ...

class StopOnFail(Event): ...

class UpdateCheckError(ErrorRuleEvent): ...

class PreProcError(ErrorRuleEvent): ...

class ExecError(ErrorRuleEvent): ...

class PostProcError(ErrorRuleEvent): ...

class FatalError(ErrorRuleEvent): ...

