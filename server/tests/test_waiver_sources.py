from ffdraft.models import UsageWeek, WaiverPlayer
from ffdraft.waiver_sources import (
    apply_fp_ros, apply_fp_waiver, apply_rotowire, apply_sleeper, apply_snaps, clean_note, fp_ros_slug, fp_waiver_slugs, parse_rotowire_moves,
    parse_snap_csv,
)
from ffdraft.weekly import _usage


def wx(pid, name, pos, team="FA", usage=()):
    return WaiverPlayer(player_id=pid, name=name, position=pos, pro_team=team, usage=[UsageWeek(week=w) for w in usage])


def test_fp_slugs():
    assert fp_waiver_slugs("HALF") == ["waiver-wire-half-point-ppr-overall", "waiver-wire-overall"]
    assert fp_waiver_slugs("STD") == ["waiver-wire-overall"]
    assert fp_ros_slug("PPR") == "ros-ppr-overall" and fp_ros_slug("STD") == "ros-overall"


def test_apply_fp_waiver_and_ros():
    ps = [wx(1, "Jahmyr Gibbs", "RB", "DET"), wx(2, "Tank Dell", "WR", "HOU"), wx(3, "Vikings D/ST", "D/ST", "MIN"), wx(4, "A.J. Brown", "WR", "PHI")]
    ww = {"players": [
        {"player_name": "Jahmyr Gibbs", "player_position_id": "RB", "rank_ecr": 1, "tag": "$40", "note": "<p>Feature <b>back</b>&nbsp;now.</p>", "player_owned_avg": 58.9},
        {"player_name": "Minnesota Vikings", "player_position_id": "DST", "player_team_id": "MIN", "rank_ecr": 7, "tag": "", "note": None},
        {"player_name": "Nobody Here", "player_position_id": "WR", "rank_ecr": 9},
    ]}
    assert apply_fp_waiver(ps, ww) == 2
    assert ps[0].fp_waiver_rank == 1 and ps[0].fp_faab == "$40" and ps[0].fp_note == "Feature back now." and ps[0].fp_waiver_owned == 58.9
    assert ps[2].fp_waiver_rank == 7 and ps[2].fp_faab is None
    ros = {"players": [
        {"player_name": "AJ Brown", "player_position_id": "WR", "rank_ecr": 3, "rank_min": 1, "rank_max": 9},
        {"player_name": "Jahmyr Gibbs", "player_position_id": "RB", "rank_ecr": 5},
        {"player_name": "Tank Dell", "player_position_id": "WR", "rank_ecr": 40, "pos_rank": "WR17"},
        {"player_name": "Minnesota Vikings", "player_position_id": "DST", "player_team_id": "MIN", "rank_ecr": 150},
    ]}
    assert apply_fp_ros(ps, ros) == 4
    assert ps[3].ros_rank == 3 and ps[3].ros_pos_rank == "WR1" and ps[3].ros_best == 1 and ps[3].ros_worst == 9
    assert ps[0].ros_pos_rank == "RB1" and ps[1].ros_pos_rank == "WR17" and ps[2].ros_pos_rank == "DST1"


def test_clean_note():
    assert clean_note("  <p>Hi&amp;bye</p>\n<br/>there ") == "Hi&bye there"
    assert clean_note(None) is None and clean_note("<p></p>") is None


def test_apply_sleeper_including_dst():
    ps = [wx(10, "Some Back", "RB", "SEA"), wx(11, "Vikings D/ST", "D/ST", "MIN"), wx(12, "Other Guy", "WR", "NYJ")]
    sleeper = {"500": {"espn_id": 10, "injury_status": "Questionable", "injury_body_part": "Knee", "practice_participation": "DNP", "depth_chart_order": "1"}}
    by_espn = {10: sleeper["500"]}
    adds = [{"player_id": "500", "count": 700000}, {"player_id": "MIN", "count": 5000}, {"player_id": "999", "count": 1}]
    drops = [{"player_id": "500", "count": 100}]
    assert apply_sleeper(ps, by_espn, adds, drops, sleeper) == 1
    assert ps[0].sleeper_injury == "QUESTIONABLE" and ps[0].sleeper_body_part == "Knee" and ps[0].sleeper_practice == "DNP" and ps[0].depth_chart_order == 1
    assert ps[0].sleeper_adds == 700000 and ps[0].sleeper_drops == 100
    assert ps[1].sleeper_adds == 5000 and ps[2].sleeper_adds is None


def test_rotowire_parse_and_apply():
    rows = [{"rank": 1, "player": "Emanuel Wilson", "playerID": "17593", "team": "SEA", "pos": "RB", "change": "38.1"},
            {"rank": 2, "player": "Denzel Boston", "playerID": "18000", "team": "JAC", "pos": "WR", "change": "+20.5"}]
    parsed = parse_rotowire_moves(rows)
    assert parsed[0] == {"rotowire_id": 17593, "name": "Emanuel Wilson", "team": "SEA", "pos": "RB", "change": 38.1}
    assert parsed[1]["team"] == "JAX" and parsed[1]["change"] == 20.5
    ps = [wx(1, "Emanuel Wilson", "RB", "SEA"), wx(2, "Denzel Boston", "WR", "JAX"), wx(3, "Jaguars D/ST", "D/ST", "JAX")]
    injuries = [{"rotowire_id": None, "name": "Denzel Boston", "team": "JAX", "pos": "WR", "injury": "Hamstring", "status": "Questionable"}]
    dropped = [{"rotowire_id": None, "name": "Jaguars", "team": "JAX", "pos": "DST", "change": 9.0}]
    a, d, i = apply_rotowire(ps, {"added": parsed, "dropped": dropped}, injuries, {17593: 1})
    assert (a, d, i) == (2, 1, 1)
    assert ps[0].rw_add_pct == 38.1 and ps[1].rw_add_pct == 20.5 and ps[1].rw_injury == "Hamstring" and ps[1].rw_status == "Questionable"
    assert ps[2].rw_drop_pct == 9.0


SNAPS = """game_id,pfr_game_id,season,game_type,week,player,pfr_player_id,position,team,opponent,offense_snaps,offense_pct,defense_snaps,defense_pct,st_snaps,st_pct
2026_01_LA_DET,x,2026,REG,1,Kyren Williams,WillKy00,RB,LA,DET,50,0.78,0,0,0,0
2026_02_LA_ARI,x,2026,REG,2,Kyren Williams,WillKy00,RB,LA,ARI,44,0.66,0,0,0,0
2026_03_LA_SF,x,2026,REG,3,Kyren Williams,WillKy00,RB,LA,SF,60,0.9,0,0,0,0
2026_01_LA_DET,x,2026,REG,1,Some Lineman,LineSo00,OL,LA,DET,60,1.0,0,0,0,0
"""


def test_snaps_parse_and_apply():
    snaps = parse_snap_csv(SNAPS)
    assert list(snaps) == ["kyren williams|LAR"] and snaps["kyren williams|LAR"] == [[1, 50.0, 0.78], [2, 44.0, 0.66], [3, 60.0, 0.9]]
    p = wx(1, "Kyren Williams", "RB", "LAR", usage=(1, 2))
    assert apply_snaps([p], snaps, 3) == 1
    assert p.snap_pct == 0.66 and [u.snap_pct for u in p.usage] == [0.78, 0.66]  # week 3 is the week being planned, so it is excluded


def test_usage_from_espn_stats():
    class Fake:
        stats = {1: {"breakdown": {"receivingTargets": 7.0, "rushingAttempts": 12, "receivingReceptions": 5}, "points": 9.1}, 2: {"breakdown": {}, "points": 0}, 3: {"breakdown": {"passingAttempts": 30}, "points": 4}}

    u = _usage(Fake(), 4)
    assert [(x.week, x.targets, x.carries, x.receptions, x.pass_att, x.points) for x in u] == [(1, 7, 12, 5, None, 9.1), (3, None, None, None, 30, 4)]
    assert _usage(Fake(), 1) == []
