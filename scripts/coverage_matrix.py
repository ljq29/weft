"""Validate roadmap task state and US/AC test traceability."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

AC_REFERENCE = re.compile(r"US-[A-Z]{3}-\d{2}/AC-\d+")
AC_REFERENCE_PARTS = re.compile(r"(US-[A-Z]{3}-\d{2})/AC-(\d+)(\.\.(\d+))?((?:,\d+)*)")
STORY_RANGE = re.compile(r"(US-([A-Z]{3})-(\d{2}))\.\.(\d{2})")
STORY_REFERENCE = re.compile(r"US-[A-Z]{3}-\d{2}(?!/AC)(?!\.\.\d)")
TASK_LINE = re.compile(r"^- \[([ xX])\] \*\*(T\d+\.\d+)(?:\s+[^*]+)?\*\*")
TEST_TAGS = ("[unit]", "[int]", "[int-win]", "[e2e]")


@dataclass(frozen=True)
class StoryIndex:
    valid: frozenset[str]
    manual: frozenset[str]
    by_story: dict[str, frozenset[str]]


@dataclass(frozen=True)
class RoadmapTask:
    task_id: str
    completed: bool
    references: frozenset[str]


@dataclass(frozen=True)
class CoverageReport:
    story_count: int
    completed_tasks: tuple[RoadmapTask, ...]
    missing: dict[str, frozenset[str]] = field(default_factory=dict)
    unknown: frozenset[str] = frozenset()


def parse_user_stories(text: str) -> StoryIndex:
    valid: set[str] = set()
    manual: set[str] = set()
    by_story: dict[str, set[str]] = {}
    story_id: str | None = None
    manual_only_story = False
    for line in text.splitlines():
        heading = re.match(r"^### (US-[A-Z]{3}-\d{2})\s", line)
        if heading:
            story_id = heading.group(1)
            by_story[story_id] = set()
            manual_only_story = "[manual]" in line and not any(tag in line for tag in TEST_TAGS)
            continue
        acceptance = re.match(r"^\s*-\s*(AC-\d+)\b(.*)", line)
        if story_id and acceptance:
            reference = f"{story_id}/{acceptance.group(1)}"
            valid.add(reference)
            by_story[story_id].add(reference)
            if manual_only_story or "[manual]" in acceptance.group(2):
                manual.add(reference)
    return StoryIndex(
        valid=frozenset(valid),
        manual=frozenset(manual),
        by_story={key: frozenset(value) for key, value in by_story.items()},
    )


def expand_ac_references(text: str) -> set[str]:
    references: set[str] = set()
    for match in AC_REFERENCE_PARTS.finditer(text):
        story, first, _, last, additional = match.groups()
        start = int(first)
        numbers = range(start, int(last) + 1) if last else [start]
        references.update(f"{story}/AC-{number}" for number in numbers)
        references.update(f"{story}/AC-{number}" for number in additional.split(",") if number)
    return references


def expand_roadmap_references(text: str, stories: StoryIndex) -> frozenset[str]:
    references = expand_ac_references(text)
    for match in STORY_RANGE.finditer(text):
        first_story, epic, first, last = match.groups()
        for number in range(int(first), int(last) + 1):
            references.update(stories.by_story.get(f"US-{epic}-{number:02d}", ()))
    for story in STORY_REFERENCE.findall(text):
        references.update(stories.by_story.get(story, ()))
    return frozenset(references)


def parse_roadmap(text: str, stories: StoryIndex) -> tuple[RoadmapTask, ...]:
    tasks: list[RoadmapTask] = []
    task_id: str | None = None
    completed = False
    lines: list[str] = []

    def finish_task() -> None:
        if task_id is not None:
            tasks.append(
                RoadmapTask(
                    task_id, completed, expand_roadmap_references("\n".join(lines), stories)
                )
            )

    for line in text.splitlines():
        match = TASK_LINE.match(line)
        if match:
            finish_task()
            completed = match.group(1).lower() == "x"
            task_id = match.group(2)
            lines = [line]
        elif line.startswith("- [") and "**T" in line:
            raise ValueError(f"Malformed roadmap task checkbox: {line}")
        elif task_id is not None:
            lines.append(line)
    finish_task()
    return tuple(tasks)


def evaluate_coverage(
    stories_text: str, roadmap_text: str, test_texts: Iterable[str]
) -> CoverageReport:
    stories = parse_user_stories(stories_text)
    tasks = parse_roadmap(roadmap_text, stories)
    test_references = {reference for text in test_texts for reference in expand_ac_references(text)}
    roadmap_references = set().union(*(task.references for task in tasks)) if tasks else set()
    unknown = (roadmap_references | test_references) - stories.valid
    completed = tuple(task for task in tasks if task.completed)
    missing = {
        task.task_id: task.references - test_references - stories.manual
        for task in completed
        if task.references - test_references - stories.manual
    }
    return CoverageReport(
        story_count=len(stories.by_story),
        completed_tasks=completed,
        missing=missing,
        unknown=frozenset(unknown),
    )


def iter_test_files(root: Path) -> Iterable[Path]:
    yield from root.glob("packages/**/tests/**/*.py")
    yield from root.glob("frontend/src/**/*.test.*")
    e2e = root / "e2e"
    if e2e.exists():
        yield from (path for path in e2e.rglob("*") if path.suffix in {".ts", ".tsx", ".js"})


def check_repository(root: Path) -> CoverageReport:
    stories_text = (root / "docs/02-user-stories.md").read_text(encoding="utf-8")
    roadmap_text = (root / "docs/07-roadmap.md").read_text(encoding="utf-8")
    test_texts = (path.read_text(encoding="utf-8") for path in iter_test_files(root))
    return evaluate_coverage(stories_text, roadmap_text, test_texts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        report = check_repository(args.root)
    except (OSError, ValueError) as error:
        print(f"Coverage matrix error: {error}", file=sys.stderr)
        return 1
    if report.unknown:
        print(f"Unknown US/AC references: {', '.join(sorted(report.unknown))}", file=sys.stderr)
    for task_id, references in report.missing.items():
        print(f"{task_id} lacks tests for: {', '.join(sorted(references))}", file=sys.stderr)
    if report.unknown or report.missing:
        return 1
    print(
        f"Coverage matrix: {report.story_count} stories; "
        f"{len(report.completed_tasks)} completed tasks; all references valid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
