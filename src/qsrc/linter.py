from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .ast import QsrcDocument
from .config import QsrcLintConfig, load_qsrc_lint_config
from .context import LintContext
from .errors import QsrcIssue
from .ignore import build_ignore_map
from .passes import QsrcStatementPass, QsrcStructurePass, QsrcStylePass


@dataclass(slots=True)
class QsrcLintResult:
    issues: list[QsrcIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class QsrcLinter:
    def __init__(self) -> None:
        self._passes = (
            QsrcStructurePass(),
            QsrcStatementPass(),
            QsrcStylePass(),
        )

    def lint_document(
        self,
        document: QsrcDocument,
        *,
        relative_path: Path | None = None,
        location_name: str = "",
        source_text: str = "",
        config: QsrcLintConfig | None = None,
    ) -> QsrcLintResult:
        active_config = config or load_qsrc_lint_config(relative_path.parent if relative_path else None)
        active_location = location_name or (document.passages[0].location_name if document.passages else "")
        context = LintContext(
            document=document,
            source_text=source_text,
            location_name=active_location,
            relative_path=relative_path,
            config=active_config,
            ignore_map=build_ignore_map(document.logical_lines),
        )

        issues: list[QsrcIssue] = []
        for lint_pass in self._passes:
            if lint_pass.rule_id in active_config.disabled_rules:
                continue
            if lint_pass.rule_id == "style" and not active_config.enable_project_style_passes:
                continue
            issues.extend(lint_pass.run(context))

        if active_config.warning_as_error:
            issues = [
                QsrcIssue(
                    error_code=issue.error_code,
                    error_desc=issue.error_desc,
                    line=issue.line,
                    column=issue.column,
                    location_name=issue.location_name,
                    act_index=issue.act_index,
                    relative_path=issue.relative_path,
                    severity="error" if issue.severity == "warning" else issue.severity,
                    details=issue.details,
                    context_diff=issue.context_diff,
                )
                for issue in issues
            ]
        return QsrcLintResult(issues=issues)
