from enum import StrEnum


class PortType(StrEnum):
    TABLE = "table"
    EXCEL = "excel"
    VARIABLE = "variable"
    MESSAGE = "message"
    TOOL = "tool"
    FLOW = "flow"


def is_compatible(source: PortType | str, target: PortType | str) -> bool:
    source_type = PortType(source)
    target_type = PortType(target)
    return source_type == target_type or (
        target_type == PortType.FLOW and source_type not in {PortType.TOOL, PortType.FLOW}
    )
