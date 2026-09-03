from ffdraft.injury import build_report, missed_time, parse_news
from ffdraft.models import Player, SeasonPoints

NEWS = {"news": {"feed": [
    {"published": "2026-09-02T10:00Z", "type": "Rotowire", "headline": "Chase (knee) was limited at Wednesday's practice",
     "story": "He hyperextended the knee last week."},
    {"published": "2026-08-28T10:00Z", "type": "Story", "headline": "Fantasy cheat sheet: value picks", "story": "<p>Sleepers to target</p>"},
    {"published": "2026-08-25T10:00Z", "type": "Rotowire", "headline": "Chase downplayed his knee injury Tuesday", "story": "A little hyperextension."},
]}}


def _p(status=None):
    return Player(player_id=1, name="Test Guy", position="WR", pro_team="CIN", injury_status=status)


def test_parse_news_keeps_only_injury_items():
    notes, part = parse_news(NEWS)
    assert len(notes) == 2 and part == "knee"
    assert notes[0].date == "2026-09-02" and notes[0].source == "Rotowire"
    assert all("cheat sheet" not in n.headline for n in notes)


def test_missed_time_from_history():
    hist = [SeasonPoints(season=2025, points=200, avg=14, games=14), SeasonPoints(season=2024, points=250, avg=15, games=17)]
    m = missed_time(hist)
    assert len(m) == 1 and m[0].season == 2025 and m[0].missed == 3


def test_report_levels():
    healthy = build_report(_p(), [SeasonPoints(season=2025, points=250, avg=15, games=17)], {})
    assert healthy.level == "none" and "No injury designation" in healthy.concern

    watch = build_report(_p("QUESTIONABLE"), [], NEWS)
    assert watch.level == "watch" and watch.body_part == "knee" and watch.status == "Questionable"
    assert "not disqualifying" in watch.concern

    out = build_report(_p("OUT"), [SeasonPoints(season=2025, points=90, avg=9, games=9)], NEWS)
    assert out.level == "concern" and "plan for a backup" in out.concern
    assert out.missed[0].missed == 8

    fragile = build_report(_p(), [SeasonPoints(season=2025, points=90, avg=10, games=9)], {})
    assert fragile.level == "concern" and "missed games before" in fragile.concern


def test_football_is_not_a_foot_injury():
    """ESPN's feed mixes in general fantasy articles; word boundaries keep them out."""
    noise = {"news": {"feed": [
        {"published": "2026-09-02", "type": "Rotowire", "headline": "Gibbs had a strong day at practice", "story": "He looked explosive."},
        {"published": "2026-09-02", "type": "Story", "headline": "Fantasy football buzz: expect Gibbs to be busier", "story": "Football analysis."},
    ]}}
    notes, part = parse_news(noise)
    assert notes == [] and part is None
    assert build_report(_p(), [], noise).level == "none"


def test_real_body_part_still_detected():
    hurt = {"news": {"feed": [{"published": "2026-08-30", "type": "Rotowire",
                               "headline": "Nacua (groin) is practicing Sunday", "story": "He returned to drills."}]}}
    notes, part = parse_news(hurt)
    assert part == "groin" and len(notes) == 1
