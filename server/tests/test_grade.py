"""Draft grades: every pick scored against what its slot was worth."""
import pytest

from ffdraft.draft import DraftBoard, build_state
from ffdraft.grade import grade_board, letter
from ffdraft.models import SetupOverrides


@pytest.fixture
def board(settings):
    return DraftBoard(build_state(settings, SetupOverrides(my_slot=3)), None)


def _fill(board, rankings, order):
    """Give every pick a player, taking from `order` so the outcome is controlled."""
    pool = list(order)
    for p in board.picks:
        if p.player_id is None and not p.unknown and pool:
            p.player_id = pool.pop(0).player_id
            p.source = "manual"


def test_nothing_drafted_grades_nothing(board, settings, rankings):
    g = grade_board(board, settings, SetupOverrides(), rankings)
    assert g.teams == [] and "nothing to grade" in g.note.lower()
    assert g.graded_picks == 0


def test_every_team_is_graded_once_and_ranked(board, settings, rankings):
    _fill(board, rankings, rankings.overall)
    g = grade_board(board, settings, SetupOverrides(), rankings)
    assert len(g.teams) == settings.team_count
    assert [t.rank for t in g.teams] == list(range(1, settings.team_count + 1))
    assert all(0 <= t.score <= 100 for t in g.teams)
    assert all(t.reasons for t in g.teams)
    scores = [t.score for t in g.teams]
    assert scores == sorted(scores, reverse=True)  # ranked best first


def test_the_team_that_beat_the_curve_most_ranks_first(board, settings, rankings):
    _fill(board, rankings, rankings.overall)
    g = grade_board(board, settings, SetupOverrides(), rankings)
    best_edge = max(g.teams, key=lambda t: t.edge_per_pick)
    assert g.teams[0].team_id == best_edge.team_id


def test_grades_explain_themselves(board, settings, rankings):
    _fill(board, rankings, rankings.overall)
    g = grade_board(board, settings, SetupOverrides(), rankings)
    t = g.teams[0]
    assert any("pick slots usually return" in r for r in t.reasons)
    assert t.best is not None and t.worst is not None
    assert t.best.edge >= t.worst.edge
    assert t.picks_made == sum(1 for p in board.picks if p.owner_team_id == t.team_id and p.player_id)


def test_partial_draft_is_flagged_as_provisional(board, settings, rankings):
    pool = list(rankings.overall)
    for p in board.picks[:20]:
        p.player_id = pool.pop(0).player_id
        p.source = "manual"
    g = grade_board(board, settings, SetupOverrides(), rankings)
    assert not g.complete and "picks are in" in g.note
    assert g.graded_picks == 20


def test_score_scale_never_reads_as_a_failure_for_an_ordinary_draft(board, settings, rankings):
    """Someone finishes last in every league; the scale should not call that an F."""
    _fill(board, rankings, rankings.overall)
    g = grade_board(board, settings, SetupOverrides(), rankings)
    assert min(t.score for t in g.teams) >= 50
    assert max(t.score for t in g.teams) <= 100


def test_letters_track_the_score():
    assert letter(98) == "A+" and letter(93) == "A" and letter(84) == "B"
    assert letter(78) == "C+" and letter(75) == "C" and letter(64) == "D" and letter(40) == "F"


def test_open_starting_slots_are_reported(board, settings, rankings):
    qbs = [p for p in rankings.overall if p.position == "QB"]
    for p in board.picks[:10]:
        p.player_id = qbs.pop(0).player_id
        p.source = "manual"
    g = grade_board(board, settings, SetupOverrides(), rankings)
    drafted = [t for t in g.teams if t.picks_made]
    assert all(t.open_starters for t in drafted)  # a roster of quarterbacks fills nothing else
    assert any("still missing" in r for t in drafted for r in t.reasons)
