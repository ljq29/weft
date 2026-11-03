class EngineError(RuntimeError):
    pass


class UnconfiguredNodesError(EngineError):
    pass


class RunQueueFullError(EngineError):
    pass
