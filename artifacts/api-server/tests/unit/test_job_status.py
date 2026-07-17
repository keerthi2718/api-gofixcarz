"""Unit tests for job status transition rules."""
import pytest

from app.models.job import JobStatus
from app.services.job_service import _TERMINAL, _VALID_TRANSITIONS


def test_terminal_statuses():
    assert JobStatus.COMPLETED in _TERMINAL
    assert JobStatus.CANCELLED in _TERMINAL
    assert JobStatus.OPEN not in _TERMINAL


def test_terminal_statuses_have_no_transitions():
    for terminal in _TERMINAL:
        assert _VALID_TRANSITIONS[terminal] == set(), \
            f"Terminal status {terminal} should have no valid transitions"


def test_open_can_start_or_cancel():
    allowed = _VALID_TRANSITIONS[JobStatus.OPEN]
    assert JobStatus.IN_PROGRESS in allowed
    assert JobStatus.CANCELLED in allowed
    assert JobStatus.COMPLETED not in allowed


def test_in_progress_can_wait_or_complete():
    allowed = _VALID_TRANSITIONS[JobStatus.IN_PROGRESS]
    assert JobStatus.WAITING_FOR_PARTS in allowed
    assert JobStatus.QUALITY_CHECK in allowed
    assert JobStatus.COMPLETED in allowed
    assert JobStatus.CANCELLED in allowed


def test_waiting_can_resume_or_cancel():
    allowed = _VALID_TRANSITIONS[JobStatus.WAITING_FOR_PARTS]
    assert JobStatus.IN_PROGRESS in allowed
    assert JobStatus.CANCELLED in allowed
    assert JobStatus.COMPLETED not in allowed


def test_quality_check_can_go_back_or_complete():
    allowed = _VALID_TRANSITIONS[JobStatus.QUALITY_CHECK]
    assert JobStatus.IN_PROGRESS in allowed
    assert JobStatus.COMPLETED in allowed
    assert JobStatus.CANCELLED in allowed


def test_no_transition_back_to_open_from_in_progress():
    allowed = _VALID_TRANSITIONS[JobStatus.IN_PROGRESS]
    assert JobStatus.OPEN not in allowed


def test_all_statuses_have_transition_map():
    for status in JobStatus:
        assert status in _VALID_TRANSITIONS, f"Missing transition map for {status}"
