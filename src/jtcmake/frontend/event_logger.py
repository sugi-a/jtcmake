from ..logwriter.writer import IWriter
from ..core import events


def create_event_callback(w: IWriter, rules, base):
    def callback(e):
        if isinstance(e, events.RuleEvent):
            w.info(str(e), e.rule.name)

        if isinstance(e, events.Skip):
            msg = 'Nothing to be done for ' # TODO
            if e.rule in rules:
                w.info(msg)
            else:
                w.debug(msg)
        elif isinstance(e, events.Start):
            ...
        elif isinstance(e, events.Done):
            ...
        elif isinstance(e, events.DryRun):
            ...
        elif isinstance(e, events.StopOnFail):
            ...
        elif isinstance(e, events.UpdateCheckError):
            ...
        elif isinstance(e, events.PreProcError):
            ...
        elif isinstance(e, events.ExecError):
            ...
        elif isinstance(e, events.PostProcError):
            ...
        elif isinstance(e, events.FatalError):
            ...
        else:
            writer.warning(f'Unhandled event: {e}')

    return callback
    
