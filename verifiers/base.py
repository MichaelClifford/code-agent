"""
Base verifier interface.

All verifiers implement this interface. A verifier takes a patch and repo
context, runs a check, and returns a VerifierResult with a score and metadata.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class VerifierStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"       # verifier itself crashed
    TIMEOUT = "timeout"
    SKIPPED = "skipped"   # skipped due to early exit in prior stage


@dataclass
class VerifierResult:
    """Result from a single verifier run."""
    name: str
    status: VerifierStatus
    score: float                          # normalized to [0.0, 1.0]
    wall_clock_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    # Raw output for debugging
    stdout: str = ""
    stderr: str = ""

    @property
    def passed(self) -> bool:
        return self.status == VerifierStatus.PASS

    def __repr__(self) -> str:
        return (
            f"VerifierResult(name={self.name!r}, status={self.status.value}, "
            f"score={self.score:.3f}, time={self.wall_clock_seconds:.1f}s)"
        )


@dataclass
class PatchContext:
    """Everything a verifier needs to check a patch."""
    repo_path: Path                       # path to the repo with patch applied
    patch_diff: str                       # the raw unified diff
    changed_files: list[str]              # list of files modified by the patch
    task_id: str                          # SWE-bench task identifier
    test_cmd: str | None = None           # repo-specific test command
    ground_truth_patch: str | None = None # for differential comparison
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVerifier(ABC):
    """Abstract base class for all verifiers."""

    def __init__(self, config: dict[str, Any] | None = None, timeout: float = 60.0):
        self.config = config or {}
        self.timeout = timeout

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this verifier."""
        ...

    @abstractmethod
    async def verify(self, ctx: PatchContext) -> VerifierResult:
        """
        Run the verification check.

        Args:
            ctx: The patch context containing repo path, diff, etc.

        Returns:
            VerifierResult with status, score, and details.
        """
        ...

    async def safe_verify(self, ctx: PatchContext) -> VerifierResult:
        """
        Run verify() with timeout and error handling.
        Subclasses should not override this.
        """
        import asyncio

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.verify(ctx),
                timeout=self.timeout
            )
            result.wall_clock_seconds = time.monotonic() - start
            return result
        except asyncio.TimeoutError:
            return VerifierResult(
                name=self.name,
                status=VerifierStatus.TIMEOUT,
                score=0.0,
                wall_clock_seconds=time.monotonic() - start,
                details={"timeout": self.timeout},
            )
        except Exception as e:
            return VerifierResult(
                name=self.name,
                status=VerifierStatus.ERROR,
                score=0.0,
                wall_clock_seconds=time.monotonic() - start,
                details={"error": str(e), "error_type": type(e).__name__},
            )
