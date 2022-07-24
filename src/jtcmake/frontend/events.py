from ..core.rule import Event

class Clean(Event):
    def __init__(self, path):
        self.path = path


class Touch(Event):
    def __init__(self, path):
        self.path = path
