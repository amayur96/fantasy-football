from ffdraft.value import ValueWeights, adp_round, build_rankings, pick_curve, replacement_levels, starter_counts, value_round


def test_starter_counts_allocates_flex(settings, players):
    counts = starter_counts(settings, players)
    assert counts["QB"] == 10 and counts["TE"] == 10 and counts["K"] == 10
    # 10 flex slots go to RB/WR/TE beyond their dedicated starters (20 RB, 20 WR)
    assert counts["RB"] + counts["WR"] + counts["TE"] == 20 + 20 + 10 + 10


def test_replacement_baseline_is_mean_of_window(settings, players):
    counts = starter_counts(settings, players)
    base = replacement_levels(players, counts, ValueWeights())
    projs = sorted((p.proj_points for p in players if p.position == "QB"), reverse=True)
    expected = sum(projs[10:13]) / 3
    assert abs(base["QB"] - expected) < 1e-9


def test_vorp_monotonic_within_position(rankings):
    for pos, lst in rankings.by_pos.items():
        vorps = [p.vorp for p in lst]
        assert vorps == sorted(vorps, reverse=True), pos


def test_missing_adp_uses_projection_vorp(settings, players):
    for p in players:
        p.adp = None
    r = build_rankings(players, settings)
    assert all(abs(p.adp_vorp - p.vorp) < 1e-9 for p in r.overall)


def test_tiers_are_contiguous_and_capped(rankings):
    for pos, lst in rankings.by_pos.items():
        tiers = [p.tier for p in lst]
        assert tiers == sorted(tiers), pos
        assert tiers[0] == 1
        for t in set(tiers):
            assert tiers.count(t) <= ValueWeights().tier_max_size + 1


def test_round_helpers():
    assert adp_round(23, 10) == 3
    assert adp_round(None, 10) is None
    assert value_round(10, 10) == 1
    assert value_round(11, 10) == 2


def test_pick_curve_descends(rankings):
    curve = pick_curve(rankings, 180)
    assert len(curve) == 180
    assert curve[0] >= curve[50] >= curve[-1]


def test_expert_rank_blends_and_renormalises(settings, players):
    from ffdraft.value import ValueWeights

    for p in players:
        p.adp = None
    rb1 = next(p for p in players if p.name == "RB Player 1")
    rb2 = next(p for p in players if p.name == "RB Player 2")
    rb2.fp_rank = 1  # experts love RB2
    r = build_rankings(players, settings, ValueWeights(w_proj=0.5, w_adp=0.25, w_fp=0.25))
    a, b = r.by_id[rb1.player_id], r.by_id[rb2.player_id]
    assert abs(a.value - a.vorp) < 1e-9  # no adp, no fp -> pure projection
    assert b.value > b.vorp and b.consensus_gap is not None and b.consensus_gap < 0
    assert abs(b.value - (0.5 * b.vorp + 0.25 * b.fp_vorp) / 0.75) < 1e-9


def test_boris_chen_tiers_override_gap_tiers(settings, players):
    for i, p in enumerate(q for q in players if q.position == "WR"):
        p.bc_tier = 1 + i // 6
    r = build_rankings(players, settings)
    wrs = r.by_pos["WR"]
    assert wrs[0].tier == 1 and all(p.tier == p.bc_tier for p in wrs if p.bc_tier)


def test_tiers_continue_past_boris_chen_for_the_whole_pool(settings, players):
    """Boris Chen only ranks the top of each position; the rest still need real tiers for late rounds."""
    from ffdraft.value import ValueWeights, build_rankings

    wrs = [p for p in players if p.position == "WR"]
    for i, p in enumerate(wrs[:12]):
        p.bc_tier = 1 + i // 4  # tiers 1-3 cover only the first 12
    r = build_rankings(players, settings, ValueWeights())
    ranked = r.by_pos["WR"]
    assert all(p.tier == p.bc_tier for p in ranked if p.bc_tier)
    tail = [p for p in ranked if not p.bc_tier]
    assert tail, "fixture should have unranked WRs"
    assert min(p.tier for p in tail) > 3  # continues past Boris Chen's last tier
    assert len({p.tier for p in tail}) > 1, "the tail must not collapse into one bucket"
    tiers = [p.tier for p in ranked]
    assert tiers == sorted(tiers)  # still monotonic down the list
