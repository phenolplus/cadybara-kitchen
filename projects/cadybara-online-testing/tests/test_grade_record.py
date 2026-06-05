from __future__ import annotations

import pytest
from pydantic import ValidationError

from cadybara_online_testing.grading import CodeRubric, GradeRecord


def test_grade_record_round_trips_json() -> None:
    grade = GradeRecord(
        grade_id="grade-1",
        experiment_id="exp",
        model_name="model",
        prompt_id="prompt",
        repetition=0,
        run_id="run-1",
        rubric=CodeRubric(
            code_validity=1,
            intent_attempt=2,
            feature_accuracy=1,
            notes="reasonable body",
        ),
        graded_at_utc="2026-05-23T00:00:00Z",
        grader="aaroh",
    )
    parsed = GradeRecord.model_validate_json(grade.model_dump_json())
    assert parsed == grade
    assert parsed.rubric.intent_attempt == 2


def test_code_rubric_validates_score_ranges() -> None:
    with pytest.raises(ValidationError):
        CodeRubric(code_validity=2, intent_attempt=0, feature_accuracy=0)
    with pytest.raises(ValidationError):
        CodeRubric(code_validity=1, intent_attempt=4, feature_accuracy=0)
    with pytest.raises(ValidationError):
        CodeRubric(code_validity=1, intent_attempt=0, feature_accuracy=-1)
