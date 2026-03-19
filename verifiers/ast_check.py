"""
AST validity verifier.

Checks that all changed Python files parse successfully.
This is the cheapest possible check — catches syntax errors
that small models produce more frequently than frontier models.
"""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseVerifier, PatchContext, VerifierResult, VerifierStatus


class ASTCheckVerifier(BaseVerifier):
    @property
    def name(self) -> str:
        return "ast_check"

    async def verify(self, ctx: PatchContext) -> VerifierResult:
        python_files = [f for f in ctx.changed_files if f.endswith(".py")]

        #e.g. changed files are md files or JS files - patch is okay as far as py is concerned
        if not python_files:
            return VerifierResult(
                name=self.name,
                status=VerifierStatus.PASS,
                score=1.0,
                details={"message": "No Python files changed"},
            )

        errors: list[dict[str, Any]] = []
        parsed, deleted = 0, 0

        #py files only - three possible states
        #deleted by patch
        #ast parsing successful (parsed += 1)
        #ast parsing unsuccessful (errors)
        for filepath in python_files:
            full_path = ctx.repo_path / filepath
            if not full_path.exists():
                # File was deleted by patch — that's fine
                deleted += 1
                continue

            try:
                source = full_path.read_text(encoding="utf-8", errors="replace")
                ast.parse(source, filename=filepath)
                parsed += 1
            except SyntaxError as e:
                errors.append({
                    "file": filepath,
                    "line": e.lineno,
                    "offset": e.offset,
                    "message": e.msg,
                })

        assert deleted + parsed + len(errors) == len(python_files)

        status = VerifierStatus.FAIL if errors else VerifierStatus.PASS
        
        #score computation
        parsed_or_errored = parsed + len(errors) #can be zero if all py files deleted
        score = parsed / parsed_or_errored if parsed_or_errored > 0 else 1.0 #else if all files deleted

        return VerifierResult(
            name=self.name,
            status=status,
            score=score,
            details={
                    "errors": errors,
                    "files_total": len(python_files),
                    "files_checked": parsed_or_errored,
                    "files_parsed": parsed,
                    "files_deleted": deleted,
                    "files_errored": len(errors)
                },
        )