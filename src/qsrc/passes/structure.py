from __future__ import annotations

from src.qsrc.context import LintContext
from src.qsrc.errors import QsrcErrorCode, QsrcIssue


class QsrcStructurePass:
    rule_id = "structure"

    def run(self, context: LintContext) -> list[QsrcIssue]:
        issues: list[QsrcIssue] = []
        logical_lines = context.document.logical_lines
        headers = [line for line in logical_lines if line.token_kind == "HEADER"]
        footers = [line for line in logical_lines if line.token_kind == "FOOTER"]
        if len(headers) != len(footers):
            culprit = headers[-1] if headers else (footers[-1] if footers else None)
            issues.append(
                QsrcIssue(
                    error_code=QsrcErrorCode.ENDNOTFOUND,
                    error_desc="location 头尾数量不匹配。",
                    line=culprit.start_line if culprit else 1,
                    location_name=context.location_name,
                    relative_path=context.relative_path,
                )
            )
        return [issue for issue in issues if context.ignore_map.allows(str(issue.error_code), issue.line)]
