from ffdraft.external import fp_page_slug, is_superflex, match_external, parse_borischen, parse_fantasypros, scoring_format
from ffdraft.models import Player, ScoringRule

BC_TEXT = """Tier 1: Jahmyr Gibbs, Bijan Robinson
Tier 2: Christian McCaffrey, RB Player 2

Tier 3: RB Player 3, Nobody Else
"""
FP_HTML = """<html><script>
var ecrData = {"sport":"NFL","total_experts":114,"last_updated":"9/03","position_id":"OP","players":[
{"player_id":1,"player_name":"QB Player 1","player_team_id":"BUF","player_position_id":"QB","player_bye_week":"7","rank_ecr":1,"rank_min":"1","rank_max":"2","rank_ave":"1.01","rank_std":"0.09","pos_rank":"QB1","tier":1},
{"player_id":2,"player_name":"RB Player 2","player_team_id":"ATL","player_position_id":"RB","player_bye_week":"5","rank_ecr":9,"rank_min":"5","rank_max":"14","rank_ave":"9.67","rank_std":"1.70","pos_rank":"RB2","tier":2},
{"player_id":3,"player_name":"Buffalo Bills","player_team_id":"BUF","player_position_id":"DST","player_bye_week":"7","rank_ecr":150,"rank_min":"140","rank_max":"160","rank_ave":"150","rank_std":"3","pos_rank":"DST1","tier":1},
{"player_id":4,"player_name":"Nobody Here","player_team_id":"SEA","player_position_id":"WR","player_bye_week":"8","rank_ecr":400,"rank_min":"1","rank_max":"2","rank_ave":"1","rank_std":"1","pos_rank":"WR99","tier":9}
]};
</script></html>"""


def test_parse_borischen():
    rows = parse_borischen(BC_TEXT)
    assert rows[0] == ("Jahmyr Gibbs", 1) and rows[3] == ("RB Player 2", 2) and rows[-1] == ("Nobody Else", 3)


def test_parse_fantasypros():
    d = parse_fantasypros(FP_HTML)
    assert d["total_experts"] == 114 and len(d["players"]) == 4


def test_match_external(players):
    players = list(players) + [Player(player_id=999, name="Bills D/ST", position="D/ST", pro_team="BUF", proj_points=100)]
    fp = parse_fantasypros(FP_HTML)
    bc = {"RB": parse_borischen(BC_TEXT)}
    ranks, unmatched, matched = match_external(players, bc, fp)
    qb1 = next(p for p in players if p.name == "QB Player 1")
    rb2 = next(p for p in players if p.name == "RB Player 2")
    assert ranks[qb1.player_id].fp_rank == 1 and ranks[qb1.player_id].fp_pos_rank == "QB1"
    assert ranks[rb2.player_id].fp_rank == 9 and ranks[rb2.player_id].bc_tier == 2
    assert ranks[999].fp_rank == 150  # DST matched by team abbreviation
    assert "Nobody Here (WR)" in unmatched["fantasypros"]
    assert matched["fantasypros"] == 3 and matched["borischen"] == 2  # RB2 and RB3; the others aren't in the pool
    assert "Nobody Else (RB)" in unmatched["borischen"]


def test_dotted_initials_normalise_like_espn():
    from ffdraft.espn.parse import normalize_name

    assert normalize_name("D.J. Moore") == normalize_name("DJ Moore")
    assert normalize_name("Travis Etienne Jr.") == normalize_name("Travis Etienne")


def test_scoring_and_superflex(settings):
    assert scoring_format(settings) == "STD"
    settings.scoring = [ScoringRule(stat_id=53, abbr="REC", label="Each reception", points=0.5)]
    assert scoring_format(settings) == "HALF"
    assert is_superflex(settings) is False
    settings.roster_slots = {**settings.roster_slots, "QB": 2}
    assert is_superflex(settings) is True
    assert fp_page_slug("HALF", True) == "half-point-ppr-superflex"
