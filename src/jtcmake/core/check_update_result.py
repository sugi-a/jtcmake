from abc import ABC


class IResult(ABC):
    ...


class UpToDate(IResult):
    ...


class Necessary(IResult):
    ...


class PossiblyNecessary(IResult):
    # dry_run only
    ...


class Infeasible(IResult):
    def __init__(self, reason):
        """
        Args:
            reason (str): reason
        """
        self.reason = reason
