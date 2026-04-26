from __future__ import annotations

from dataclasses import dataclass

from lark import Transformer, Tree

from .ast import BlockNode, CommentNode, PassageNode, QsrcDocument, QsrcLogicalLine, QsrcNode


@dataclass(slots=True)
class TransformContext:
    logical_lines: list[QsrcLogicalLine]


class QsrcTreeTransformer(Transformer):
    def __init__(self, context: TransformContext):
        super().__init__()
        self.context = context
        self._cursor = 0

    def start(self, items):
        flattened: list[object] = []
        for item in items:
            if isinstance(item, list):
                flattened.extend(item)
            else:
                flattened.append(item)
        passages = [item for item in flattened if isinstance(item, PassageNode)]
        comments = [
            CommentNode(
                kind="COMMENT",
                line=line.start_line,
                end_line=line.end_line,
                text=line.text,
                comment_text=line.text,
            )
            for line in self.context.logical_lines
            if line.token_kind == "COMMENT"
        ]
        return QsrcDocument(passages=passages, logical_lines=self.context.logical_lines, comments=comments)

    def document(self, items):
        return items

    def passage(self, items):
        consumed = self._consume_until("FOOTER")
        header = consumed[0] if consumed else None
        footer = consumed[-1] if consumed else header
        body = [
            QsrcNode(kind=line.token_kind, line=line.start_line, end_line=line.end_line, text=line.text)
            for line in consumed[1:-1]
        ]
        location_name = header.text.split("#", 1)[1].strip() if header and "#" in header.text else ""
        return PassageNode(
            kind="PASSAGE",
            line=header.start_line if header else 0,
            end_line=footer.end_line if footer else 0,
            text=header.text if header else "",
            children=[
                BlockNode(
                    kind="BLOCK",
                    line=header.start_line if header else 0,
                    end_line=footer.end_line if footer else 0,
                    children=body,
                )
            ],
            location_name=location_name,
        )

    def __default__(self, data, children, meta):
        return Tree(data, children)

    def _consume_until(self, final_kind: str) -> list[QsrcLogicalLine]:
        result: list[QsrcLogicalLine] = []
        while self._cursor < len(self.context.logical_lines):
            line = self.context.logical_lines[self._cursor]
            result.append(line)
            self._cursor += 1
            if line.token_kind == final_kind:
                break
        return result


def transform_tree(tree: Tree, logical_lines: list[QsrcLogicalLine]) -> QsrcDocument:
    return QsrcTreeTransformer(TransformContext(logical_lines)).transform(tree)
