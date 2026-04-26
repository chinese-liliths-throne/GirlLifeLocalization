from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class QsrcLogicalLine:
    index: int
    start_line: int
    end_line: int
    text: str
    token_kind: str
    is_multiline: bool = False


@dataclass(slots=True)
class QsrcNode:
    kind: str
    line: int = 0
    end_line: int = 0
    text: str = ""
    children: list["QsrcNode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LabelNode(QsrcNode):
    label_name: str = ""


@dataclass(slots=True)
class CommentNode(QsrcNode):
    comment_text: str = ""


@dataclass(slots=True)
class StringNode(QsrcNode):
    quote: str = "'"


@dataclass(slots=True)
class TemplateExprNode(QsrcNode):
    expression: str = ""


@dataclass(slots=True)
class CallNode(QsrcNode):
    call_name: str = ""
    arguments: tuple[str, ...] = ()


@dataclass(slots=True)
class ArrayAccessNode(QsrcNode):
    target_name: str = ""
    index_expr: str = ""


@dataclass(slots=True)
class CommandNode(QsrcNode):
    command_name: str = ""
    arguments: tuple[str, ...] = ()


@dataclass(slots=True)
class AssignmentNode(QsrcNode):
    target_name: str = ""
    operator: str = "="
    value_expr: str = ""


@dataclass(slots=True)
class ActNode(QsrcNode):
    label_expr: str = ""


@dataclass(slots=True)
class IfNode(QsrcNode):
    condition_expr: str = ""


@dataclass(slots=True)
class ElseIfNode(QsrcNode):
    condition_expr: str = ""


@dataclass(slots=True)
class ElseNode(QsrcNode):
    pass


@dataclass(slots=True)
class ForNode(QsrcNode):
    header_expr: str = ""


@dataclass(slots=True)
class BlockNode(QsrcNode):
    pass


@dataclass(slots=True)
class PassageNode(QsrcNode):
    location_name: str = ""


@dataclass(slots=True)
class QsrcDocument:
    passages: list[PassageNode] = field(default_factory=list)
    logical_lines: list[QsrcLogicalLine] = field(default_factory=list)
    comments: list[CommentNode] = field(default_factory=list)

