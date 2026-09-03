from ffdraft.keeper import compute_keeper_cost, keeper_options, keeper_slot_round, my_pick_overall, owned_rounds
from ffdraft.models import PickTrade, SetupOverrides
from ffdraft.value import pick_curve

NAMES = {i: f"Team {i}" for i in range(1, 11)}


def cost(pid, drafts, override=None):
    return compute_keeper_cost(pid, drafts, 2026, 18, 3, NAMES, override)


def test_drafted_costs_same_round(drafts):
    c, src, years, hist, warn = cost(101, drafts)
    assert (c, src, years) == (6, "drafted", 0) and not warn


def test_kept_costs_two_earlier(drafts):
    c, src, years, hist, _ = cost(103, drafts)
    assert (c, src, years) == (4, "kept", 1)


def test_keeper_chain(drafts):
    c, src, years, hist, _ = cost(102, drafts)
    assert (c, src, years) == (13, "kept", 2)
    assert [h.round for h in hist] == [15, 17, 17]


def test_undrafted_costs_last_round(drafts):
    c, src, years, hist, _ = cost(120, drafts)
    assert (c, src) == (18, "undrafted") and hist == []


def test_override_wins(drafts):
    c, src, *_ = cost(101, drafts, override=2)
    assert (c, src) == (2, "override")


def test_other_team_warning(drafts):
    c, src, _, _, warn = cost(115, drafts)
    assert (c, src) == (5, "drafted")
    assert warn and "Team 5" in warn[0] and "R3" in warn[0]


def test_clamp_at_round_one():
    drafts = {2025: [__import__("ffdraft.models", fromlist=["DraftHistoryPick"]).DraftHistoryPick(season=2025, team_id=3, player_id=9, round_num=1, round_pick=1, keeper_status=True)]}
    c, src, _, _, warn = cost(9, drafts)
    assert c == 1 and any("round 1" in w for w in warn)


def test_my_pick_overall():
    assert my_pick_overall(1, 3, 10) == 3
    assert my_pick_overall(2, 3, 10) == 18
    assert my_pick_overall(3, 3, 10) == 23


def test_owned_rounds_and_slot_fallback():
    trades = [PickTrade(season=2026, round=4, original_team_id=3, owner_team_id=8), PickTrade(season=2026, round=9, original_team_id=1, owner_team_id=3)]
    owned = owned_rounds(3, trades, 2026, 18)
    assert owned[4] == 0 and owned[9] == 2 and owned[5] == 1
    r, warn = keeper_slot_round(3, 4, trades, 2026, 18)
    assert r == 5 and warn and "R4" in warn
    assert keeper_slot_round(3, 6, trades, 2026, 18) == (6, None)


def test_keeper_options_ranking(roster, rankings, drafts, settings, setup):
    opts = keeper_options(roster, rankings, drafts, settings, setup, pick_curve(rankings, 180))
    by_id = {o.roster_entry.player_id: o for o in opts}
    assert by_id[116].cost_round == 1 and abs(by_id[116].surplus_points or 0) < 60  # R1 pick on the R1 guy: ~no surplus
    assert by_id[120].cost_round == 18 and by_id[120].surplus_points is not None and by_id[120].surplus_points > 0  # RB6 at R18 is a steal
    assert by_id[102].cost_pick_overall == my_pick_overall(13, 3, 10)
    assert opts[0].surplus_points == max(o.surplus_points for o in opts if o.surplus_points is not None)
    assert "R18" in by_id[120].reason and "undrafted" in by_id[120].reason


def test_keeper_options_with_override(roster, rankings, drafts, settings):
    setup = SetupOverrides(my_slot=3, keeper_cost_overrides={101: 12})
    opts = keeper_options(roster, rankings, drafts, settings, setup, [])
    o = next(o for o in opts if o.roster_entry.player_id == 101)
    assert o.cost_round == 12 and o.cost_source == "override"


def test_kickers_and_defenses_are_never_recommended(rankings, drafts, settings, setup):
    from ffdraft.models import RosterEntry

    dst = next(p for p in rankings.overall if p.position == "D/ST")
    roster = [RosterEntry(season=2025, team_id=3, player_id=dst.player_id, name=dst.name, position="D/ST"),
              RosterEntry(season=2025, team_id=3, player_id=120, name="P120", position="RB")]
    opts = keeper_options(roster, rankings, drafts, settings, setup, pick_curve(rankings, 180))
    assert opts[0].roster_entry.player_id == 120
    assert opts[-1].surplus_points is None and "never worth" in opts[-1].reason


def test_reason_cites_experts_and_uses_fp_round(roster, players, drafts, settings, setup):
    from ffdraft.value import build_rankings

    rb6 = next(p for p in players if p.player_id == 120)
    rb6.fp_rank, rb6.fp_pos_rank, rb6.fp_best, rb6.fp_worst, rb6.bc_tier = 5, "RB3", 2, 9, 1
    r = build_rankings(players, settings)
    opts = keeper_options(roster, r, drafts, settings, setup, pick_curve(r, 180))
    o = next(o for o in opts if o.roster_entry.player_id == 120)
    assert "RB3 / #5 overall" in o.reason and "Boris Chen tier 1" in o.reason
    assert o.surplus_rounds == 18 - o.adp_round  # rounds surplus stays on the visible ADP round


def test_unknown_slot_uses_round_average_and_reports_range(roster, rankings, drafts, settings):
    setup = SetupOverrides()  # ESPN order exists on the fixture but is not confirmed
    opts = keeper_options(roster, rankings, drafts, settings, setup, pick_curve(rankings, 180))
    o = next(o for o in opts if o.roster_entry.player_id == 120)
    assert o.slot_known is False and o.cost_pick_overall is None
    assert o.surplus_by_slot is not None and len(o.surplus_by_slot) == 10
    assert min(o.surplus_by_slot.values()) <= (o.surplus_points or 0) <= max(o.surplus_by_slot.values()) + 1e-9
    setup.order_confirmed = True
    o2 = next(o for o in keeper_options(roster, rankings, drafts, settings, setup, pick_curve(rankings, 180)) if o.roster_entry.player_id == 120)
    assert o2.slot_known and o2.cost_pick_overall == my_pick_overall(18, 3, 10) and o2.surplus_by_slot is None


def test_reason_compares_neighbours(roster, rankings, drafts, settings, setup):
    opts = [o for o in keeper_options(roster, rankings, drafts, settings, setup, pick_curve(rankings, 180)) if o.surplus_points is not None]
    assert "ranks ahead of" in opts[0].reason and "ranks behind" not in opts[0].reason
    assert "ranks behind" in opts[1].reason and "ranks ahead of" in opts[1].reason
    assert opts[1].roster_entry.name in opts[0].reason
