from __future__ import annotations

from pathlib import Path

from src.qsrc.context import LintContext
from src.qsrc.errors import QsrcErrorCode, QsrcIssue


class QsrcStylePass:
    rule_id = "style"

    def run(self, context: LintContext) -> list[QsrcIssue]:
        issues: list[QsrcIssue] = []
        issues.extend(self._check_location_name(context))
        issues.extend(self._check_indentation(context))
        issues.extend(self._check_line_length(context))
        return [issue for issue in issues if context.ignore_map.allows(str(issue.error_code), issue.line)]

    def _check_location_name(self, context: LintContext) -> list[QsrcIssue]:
        if not context.relative_path or not context.location_name:
            return []
        stem = Path(context.relative_path).stem.casefold()
        location_name = context.location_name.casefold()
        if stem == location_name:
            return []
        return [
            QsrcIssue(
                error_code=QsrcErrorCode.LOCATION_NAME_DRIFT,
                error_desc="文件名与 location 名称不一致。",
                line=1,
                location_name=context.location_name,
                relative_path=context.relative_path,
                severity="warning",
                details=(f"file stem: {Path(context.relative_path).stem}", f"location: {context.location_name}"),
            )
        ]

    def _check_indentation(self, context: LintContext) -> list[QsrcIssue]:
        issues: list[QsrcIssue] = []
        for line in context.document.logical_lines:
            raw = line.text
            if not raw:
                continue
            prefix = raw[: len(raw) - len(raw.lstrip(" \t"))]
            if " " in prefix and "\t" in prefix:
                issues.append(
                    QsrcIssue(
                        error_code=QsrcErrorCode.SYNTAX,
                        error_desc="缩进同时混用了空格和 Tab。",
                        line=line.start_line,
                        location_name=context.location_name,
                        relative_path=context.relative_path,
                        severity="warning",
                    )
                )
        return issues

    def _check_line_length(self, context: LintContext) -> list[QsrcIssue]:
        max_length = max(40, context.config.max_line_length)
        issues: list[QsrcIssue] = []
        for line in context.document.logical_lines:
            width = max(len(part) for part in line.text.splitlines()) if line.text else 0
            if width <= max_length:
                continue
            issues.append(
                QsrcIssue(
                    error_code=QsrcErrorCode.SYNTAX,
                    error_desc=f"逻辑行长度超过限制 {max_length}。",
                    line=line.start_line,
                    location_name=context.location_name,
                    relative_path=context.relative_path,
                    severity="warning",
                    details=(f"line length: {width}",),
                )
            )
        return issues
