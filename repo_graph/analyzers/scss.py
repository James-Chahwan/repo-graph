"""
SCSS/CSS file analyzer.

Supplementary analyzer — provides file-level analysis only (bloat_report,
split_plan), no graph nodes. Detects repos containing .scss files.
"""

import re
from pathlib import Path

from .base import AnalysisResult, LanguageAnalyzer


_SELECTOR_PATTERN = re.compile(r"^([.&:@#\w][\w\-.*,\s&:()>+~]*)\s*\{")


class ScssAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        # Quick check — look for .scss files without full tree walk
        for d in [repo_root / "src", repo_root / "styles", repo_root]:
            if d.exists() and any(d.rglob("*.scss")):
                return True
        return False

    def scan(self) -> AnalysisResult:
        # SCSS analyzer contributes no graph nodes — just file analysis
        return AnalysisResult()

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".scss", ".css"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".scss", ".css"):
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        blocks = []
        current_block = None
        depth = 0

        for i, line in enumerate(lines, 1):
            if depth == 0:
                m = _SELECTOR_PATTERN.match(line)
                if m:
                    if current_block:
                        current_block["end"] = i - 1
                        current_block["lines"] = (
                            current_block["end"] - current_block["start"] + 1
                        )
                        blocks.append(current_block)
                    current_block = {
                        "selector": m.group(1).strip(),
                        "start": i,
                        "end": total,
                        "lines": 0,
                    }
            depth += line.count("{") - line.count("}")

        if current_block:
            current_block["end"] = total
            current_block["lines"] = current_block["end"] - current_block["start"] + 1
            blocks.append(current_block)

        blocks.sort(key=lambda b: b["lines"], reverse=True)

        return {
            "type": "scss",
            "file": file_path.name,
            "total_lines": total,
            "block_count": len(blocks),
            "blocks": blocks,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "scss":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['block_count']} top-level blocks)\n",
            "SCSS blocks (largest first):",
        ]
        for b in analysis["blocks"][:15]:
            bar = "█" * (b["lines"] // 10)
            lines.append(
                f"  {b['lines']:>4} lines  {bar:30s}  "
                f"{b['selector']} (L{b['start']}-{b['end']})"
            )
        return "\n".join(lines)
