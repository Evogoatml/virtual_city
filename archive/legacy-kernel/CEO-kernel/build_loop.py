"""
BuildLoop — autonomous self-assembly engine.

Reads the gap table from SYSTEM_MAP.md, picks the next disconnected
component, asks the LLM to generate wiring code, tests it in the
Sandbox, and if it passes writes the file permanently then marks the
gap as closed.

Run it once to close one gap:
    python core/build_loop.py --once

Run it continuously until all gaps are closed:
    python core/build_loop.py

Run it with a specific gap:
    python core/build_loop.py --gap "adap_pipeline tool system"
"""

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Project root
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.kernel.sandbox import Sandbox

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[BuildLoop] %(message)s")


@dataclass
class Gap:
    """A disconnected component identified in SYSTEM_MAP.md."""
    component: str      # e.g. "adap_pipeline tool system → GhostGoat orchestrator"
    description: str    # e.g. "Not bridged yet"
    priority: int = 5   # 1 (highest) to 10 (lowest)
    attempts: int = 0
    resolved: bool = False
    output_file: Optional[str] = None


@dataclass
class BuildRecord:
    gap: str
    attempt: int
    passed: bool
    file_written: Optional[str]
    sandbox_stdout: str
    sandbox_stderr: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class BuildLoop:
    """
    Reads SYSTEM_MAP.md → finds gaps → generates wiring → tests → applies.
    """

    # Class-level paths (pattable by tests via patch.object)
    ROOT       = _ROOT
    SYSTEM_MAP = _ROOT / "SYSTEM_MAP.md"
    BUILD_LOG  = _ROOT / "data" / "build_loop_log.json"
    WIRING_DIR = _ROOT / "core" / "wiring"
    MAX_ATTEMPTS = 3

    # Priority order for known gaps (lower number = do first)
    GAP_PRIORITIES = {
        "sandbox": 1,
        "adap": 2,
        "persistent": 3,
        "interpreter": 4,
        "crewai": 5,
        "langgraph": 5,
        "swarms": 5,
        "ssh": 6,
        "asi": 7,
    }

    def __init__(self, llm_call=None):
        """
        Args:
            llm_call: callable(prompt: str) -> str
                      If None, BuildLoop tries to initialise one from the
                      orchestrator. Without an LLM it can still parse gaps
                      and report them but cannot generate code.
        """
        self.sandbox = Sandbox(timeout=20, project_root=str(self.ROOT))
        self.llm_call = llm_call or self._init_llm()
        self.records: List[BuildRecord] = []
        self.WIRING_DIR.mkdir(parents=True, exist_ok=True)
        self.BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, max_cycles: Optional[int] = None, gap_filter: Optional[str] = None):
        """Run the build loop.

        Args:
            max_cycles:  Stop after this many gaps attempted. None = run until done.
            gap_filter:  Only work on gaps whose component contains this string.
        """
        logger.info("Starting build loop")
        gaps = self.load_gaps()

        if gap_filter:
            gaps = [g for g in gaps if gap_filter.lower() in g.component.lower()]

        if not gaps:
            logger.info("No open gaps found — system is fully wired!")
            return

        cycles = 0
        for gap in gaps:
            if max_cycles and cycles >= max_cycles:
                break
            if gap.resolved:
                continue

            logger.info("Working on gap: %s", gap.component)
            success = self._close_gap(gap)
            cycles += 1

            if success:
                self._mark_resolved(gap)
                logger.info("✓ Gap closed: %s", gap.component)
            else:
                logger.warning("✗ Could not close gap after %d attempts: %s", self.MAX_ATTEMPTS, gap.component)

        self._save_log()
        logger.info("Build loop finished. %d gaps attempted.", cycles)

    # ------------------------------------------------------------------
    # Gap management
    # ------------------------------------------------------------------

    def load_gaps(self) -> List[Gap]:
        """Parse SYSTEM_MAP.md and extract open gaps."""
        if not self.SYSTEM_MAP.exists():
            logger.error("SYSTEM_MAP.md not found")
            return []

        text = self.SYSTEM_MAP.read_text()

        # Find the disconnected section
        section_match = re.search(
            r"## What Exists but Isn.t Fully Connected Yet(.+?)(?=^##|\Z)",
            text, re.MULTILINE | re.DOTALL
        )
        if not section_match:
            logger.warning("Could not find gaps section in SYSTEM_MAP.md")
            return []

        section = section_match.group(1)

        # Parse markdown table rows: | Component | Gap |
        gaps = []
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("|") or "---" in line or "Component" in line:
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 2:
                continue
            component, description = parts[0], parts[1]
            if not component or component.startswith("-"):
                continue

            # Skip already-resolved gaps (marked with ✅ in the map)
            if "✅" in component or "✅" in description:
                continue

            priority = self._priority_for(component)
            gaps.append(Gap(component=component, description=description, priority=priority))

        gaps.sort(key=lambda g: g.priority)
        logger.info("Found %d open gaps", len(gaps))
        return gaps

    def _priority_for(self, component: str) -> int:
        comp_lower = component.lower()
        for keyword, priority in self.GAP_PRIORITIES.items():
            if keyword in comp_lower:
                return priority
        return 5

    # ------------------------------------------------------------------
    # Gap closing
    # ------------------------------------------------------------------

    def _close_gap(self, gap: Gap) -> bool:
        """Attempt to generate, test, and apply wiring for a gap."""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            gap.attempts = attempt
            logger.info("  Attempt %d/%d", attempt, self.MAX_ATTEMPTS)

            # Generate wiring code
            code = self._generate_wiring(gap, attempt)
            if not code:
                logger.warning("  LLM returned no code")
                continue

            # Test in sandbox
            result = self.sandbox.run(code, context=self._sandbox_context())
            record = BuildRecord(
                gap=gap.component,
                attempt=attempt,
                passed=result.passed,
                file_written=None,
                sandbox_stdout=result.stdout[:500],
                sandbox_stderr=result.stderr[:500],
            )

            if result.passed:
                # Write the wiring file
                output_path = self._write_wiring(gap, code)
                gap.output_file = output_path
                record.file_written = output_path

                # Ingest into knowledge
                self._ingest(output_path)

                self.records.append(record)
                return True
            else:
                logger.warning("  Sandbox FAIL: %s", result.stderr[:120] or result.error)
                self.records.append(record)

        return False

    def _generate_wiring(self, gap: Gap, attempt: int) -> Optional[str]:
        """Ask the LLM to generate Python wiring code for this gap."""
        if not self.llm_call:
            logger.warning("No LLM available — cannot generate code")
            return None

        system_context = self._read_system_context(gap)
        retry_note = ""
        if attempt > 1:
            # Include the last failure as context
            last = next((r for r in reversed(self.records) if r.gap == gap.component), None)
            if last:
                retry_note = f"\nPrevious attempt failed with: {last.sandbox_stderr[:300]}\nFix that issue.\n"

        prompt = f"""You are wiring together components in the GhostGoat AI system.

GAP TO CLOSE:
Component: {gap.component}
Description: {gap.description}
{retry_note}
SYSTEM CONTEXT:
{system_context}

Write Python code that bridges this gap. Requirements:
- The code must be self-contained and importable
- Use try/except around all imports so missing dependencies don't crash it
- End with a brief smoke test wrapped in: if __name__ == "__main__": ...
- Do not include markdown fences — return raw Python only
- Keep it focused: just the bridge/wiring, nothing else
"""

        try:
            response = self.llm_call(prompt)
            # Strip markdown fences if the LLM added them anyway
            response = re.sub(r"^```python\s*", "", response, flags=re.MULTILINE)
            response = re.sub(r"^```\s*", "", response, flags=re.MULTILINE)
            return response.strip()
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return None

    def _read_system_context(self, gap: Gap) -> str:
        """Build a context string with the most relevant existing code for this gap."""
        context_parts = []

        # Always include the gap table from SYSTEM_MAP
        if self.SYSTEM_MAP.exists():
            text = self.SYSTEM_MAP.read_text()
            # Just include the wired/not-wired tables
            match = re.search(r"## What.s Wired.+?(?=^##)", text, re.DOTALL | re.MULTILINE)
            if match:
                context_parts.append("=== Current wiring state ===\n" + match.group()[:1500])

        # Include files relevant to the gap based on keywords
        relevant_files = self._find_relevant_files(gap.component)
        for path in relevant_files[:3]:  # limit to 3 files to stay within context
            try:
                content = Path(path).read_text()[:1500]
                context_parts.append(f"=== {path} ===\n{content}")
            except Exception:
                pass

        return "\n\n".join(context_parts)

    def _find_relevant_files(self, component: str) -> List[str]:
        """Find existing source files relevant to a gap description."""
        keywords = re.findall(r"\b\w{4,}\b", component.lower())
        candidates = []

        search_dirs = [
            self.ROOT / "core",
            self.ROOT / "ACS_SYSTEM" / "adap_pipeline",
            self.ROOT / "frameworks",
            self.ROOT / "integrations",
        ]

        for d in search_dirs:
            if not d.exists():
                continue
            for py_file in d.rglob("*.py"):
                name_lower = py_file.stem.lower()
                if any(kw in name_lower for kw in keywords):
                    candidates.append(str(py_file))

        return candidates[:5]

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _write_wiring(self, gap: Gap, code: str) -> str:
        """Write generated wiring code to core/wiring/<slug>.py"""
        slug = re.sub(r"[^a-z0-9]+", "_", gap.component.lower()).strip("_")[:50]
        output_path = self.WIRING_DIR / f"{slug}.py"

        header = f'"""\nAuto-generated wiring: {gap.component}\nGenerated: {datetime.now().isoformat()}\nDo not edit manually — managed by BuildLoop.\n"""\n\n'
        output_path.write_text(header + code)
        logger.info("  Written: %s", output_path.relative_to(self.ROOT))
        return str(output_path)

    def _mark_resolved(self, gap: Gap):
        """Update SYSTEM_MAP.md to mark a gap as resolved."""
        if not self.SYSTEM_MAP.exists():
            return
        text = self.SYSTEM_MAP.read_text()
        updated = text.replace(
            f"| {gap.component} |",
            f"| ✅ {gap.component} |",
            1
        )
        self.SYSTEM_MAP.write_text(updated)

    def _ingest(self, path: str):
        pass

    def _sandbox_context(self) -> str:
        """Minimal context code prepended to every sandbox run."""
        return f"import sys\nsys.path.insert(0, {repr(str(self.ROOT))})\n"

    def _save_log(self):
        """Persist build records to data/build_loop_log.json."""
        existing = []
        if self.BUILD_LOG.exists():
            try:
                existing = json.loads(self.BUILD_LOG.read_text())
            except Exception:
                pass
        all_records = existing + [
            {
                "gap": r.gap,
                "attempt": r.attempt,
                "passed": r.passed,
                "file_written": r.file_written,
                "stdout": r.sandbox_stdout,
                "stderr": r.sandbox_stderr,
                "timestamp": r.timestamp,
            }
            for r in self.records
        ]
        self.BUILD_LOG.write_text(json.dumps(all_records, indent=2))

    # ------------------------------------------------------------------
    # LLM initialisation
    # ------------------------------------------------------------------

    def _init_llm(self):
        """Try to get an LLM call function from the orchestrator or env."""
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        # Pick provider based on available keys (Anthropic preferred)
        if anthropic_key:
            provider, api_key = "anthropic", anthropic_key
        elif openai_key:
            provider, api_key = "openai", openai_key
        else:
            provider, api_key = None, None

        if provider:
            try:
                from core.ghostgoat_core import LLMOrchestrator
                orch = LLMOrchestrator(llm_provider=provider, llm_api_key=api_key)
                return orch._call_llm
            except Exception:
                pass

        logger.warning("No LLM available — BuildLoop will parse gaps but cannot generate code")
        return None

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status(self):
        """Print current gap status."""
        gaps = self.load_gaps()
        print(f"\nGhostGoat Build Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"Open gaps: {len(gaps)}")
        for g in gaps:
            print(f"  [{g.priority}] {g.component} — {g.description}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GhostGoat autonomous self-assembly loop")
    parser.add_argument("--once", action="store_true", help="Close one gap then stop")
    parser.add_argument("--gap", type=str, help="Filter to gaps containing this string")
    parser.add_argument("--status", action="store_true", help="Show gap status and exit")
    parser.add_argument("--cycles", type=int, default=None, help="Max gaps to attempt")
    args = parser.parse_args()

    loop = BuildLoop()

    if args.status:
        loop.status()
        sys.exit(0)

    max_cycles = 1 if args.once else args.cycles
    loop.run(max_cycles=max_cycles, gap_filter=args.gap)
