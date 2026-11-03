import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "coverage_matrix.py"
coverage = runpy.run_path(str(SCRIPT))


def test_real_documents_have_valid_story_and_task_references() -> None:
    """T0.1: the coverage gate parses the real story and roadmap documents."""
    root = SCRIPT.parents[1]
    report = coverage["check_repository"](root)
    assert report.story_count >= 80
    assert not report.unknown


def test_unknown_acceptance_criteria_are_rejected() -> None:
    """T0.1: an invalid AC reference fails even when its task is unfinished."""
    stories = "### US-DES-01 Example [P0] [unit]\n\n- AC-1 Given a valid case.\n"
    roadmap = "- [ ] **T0.1 Example**\n【验收】US-DES-01/AC-2\n"
    report = coverage["evaluate_coverage"](stories, roadmap, [])
    assert report.unknown == frozenset({"US-DES-01/AC-2"})


def test_only_completed_tasks_require_automated_coverage() -> None:
    """T0.1: unchecked work does not create false missing-test failures."""
    stories = "### US-DES-01 Example [P0] [unit]\n\n- AC-1 Given a valid case.\n"
    roadmap = "- [ ] **T0.1 Pending**\n【验收】US-DES-01/AC-1\n"
    assert not coverage["evaluate_coverage"](stories, roadmap, []).missing
    completed = roadmap.replace("- [ ]", "- [x]")
    report = coverage["evaluate_coverage"](stories, completed, [])
    assert report.missing["T0.1"] == frozenset({"US-DES-01/AC-1"})


def test_roadmap_ranges_expand_to_all_acceptance_criteria() -> None:
    """T0.1: AC ranges in roadmap cards expand before coverage is evaluated."""
    stories = """### US-DES-01 Example [P0] [unit]

- AC-1 First case.
- AC-2 Second case.
- AC-3 Third case.
"""
    roadmap = "- [x] **T0.1 Example**\n【验收】US-DES-01/AC-1..3\n"
    report = coverage["evaluate_coverage"](stories, roadmap, [])
    assert report.missing["T0.1"] == frozenset(
        {"US-DES-01/AC-1", "US-DES-01/AC-2", "US-DES-01/AC-3"}
    )


def test_malformed_task_checkbox_is_an_error() -> None:
    """T0.1: task state cannot be hidden by a malformed checkbox."""
    with pytest.raises(ValueError, match="Malformed roadmap task checkbox"):
        coverage["parse_roadmap"]("- [] **T0.1 Example**", coverage["parse_user_stories"](""))


def test_test_tags_expand_comma_separated_acceptance_criteria() -> None:
    """T0.1: comma-separated AC tags in tests satisfy every referenced criterion."""
    stories = """### US-DES-01 Example [P0] [unit]

- AC-1 First case.
- AC-2 Second case.
"""
    roadmap = "- [x] **T0.1 Example**\n【验收】US-DES-01/AC-1,2\n"
    tests = ['def test_example():\n    """US-DES-01/AC-1,2: both cases."""\n']
    report = coverage["evaluate_coverage"](stories, roadmap, tests)
    assert not report.missing
    assert not report.unknown


def test_p0_story_range_excludes_p1_acceptance_criteria() -> None:
    """T0.1: a roadmap card explicitly limited to P0 does not pull in later P1 work."""
    stories = """### US-TBL-05 Example [P0/P1] [unit]

- AC-1 P0 case.
- AC-2 [P1] Later case.
"""
    roadmap = "- [x] **T2.5 Example**\n【验收】US-TBL-03..05 的全部 P0 AC\n"
    report = coverage["evaluate_coverage"](stories, roadmap, [])
    assert report.missing["T2.5"] == frozenset({"US-TBL-05/AC-1"})
    assert "US-TBL-05/AC-2" not in report.missing["T2.5"]
