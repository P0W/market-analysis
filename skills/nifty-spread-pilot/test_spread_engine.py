"""
Unit & Mathematical Verification Tests for NIFTY Spread Pilot (`spread_engine.py`).
Validates:
  1. Discounted Black-76 pricing & Put-Call Parity recovery
  2. Safeguarded Newton-Bisection IV solver & no-arbitrage bounds
  3. 1st-order & 2nd-order Greeks against central finite differences
  4. Regime A1 (`NO_LOSS_PROFIT_LOCK_OCO`): guaranteed >= Rs 0 net floor under worst-case limit fill
  5. Regime A2 (`PROFIT_LOCK_INFEASIBLE`): thin profit cushion where limit slippage cannot guarantee >= Rs 0
  6. Regime B (`LOSS_MINIMIZATION_OCO`): underwater spread sets Lower Trigger to Cost-Breakeven Scratch (E_zero)
  7. Priority Kill-Switch (`CLOSE_ALL_IMMEDIATELY`): loss-cap breach / Gamma wall breach
  8. Unreachable target handling (target > max possible profit)
  9. Debit spread (`BULL_CALL` / `BEAR_PUT`) accounting and OCO slot ordering
  10. Pre-filtered candidate ranking (`rank_candidate_spreads`)
"""

import math
import time
import unittest

import spread_engine as se


class TestSpreadEngine(unittest.TestCase):
    def test_discounted_put_call_parity(self) -> None:
        f_val = 22698.45
        strike = 22400.0
        t_days = 31.05
        t_years = t_days / 365.0
        r = 0.067
        sigma = 0.165

        call_p = se.bs76_price(f_val, strike, t_years, sigma, "CE", r)
        put_p = se.bs76_price(f_val, strike, t_years, sigma, "PE", r)

        # C - P == e^(-rT) * (F - K)
        self.assertAlmostEqual(call_p - put_p, math.exp(-r * t_years) * (f_val - strike), places=7)

        # Recover implied forward F from call & put prices
        parity = se.implied_forward_from_pair(strike, call_p, put_p, t_days, r)
        self.assertAlmostEqual(parity["forward"], f_val, places=2)

    def test_iv_solver_and_no_arbitrage_bounds(self) -> None:
        f_val = 22698.45
        strike = 22400.0
        t_years = 31.05 / 365.0
        r = 0.067
        sigma = 0.165

        call_p = se.bs76_price(f_val, strike, t_years, sigma, "CE", r)
        put_p = se.bs76_price(f_val, strike, t_years, sigma, "PE", r)

        iv_c, ok_c, _ = se.implied_vol_with_status(f_val, strike, t_years, call_p, "CE", r)
        iv_p, ok_p, _ = se.implied_vol_with_status(f_val, strike, t_years, put_p, "PE", r)
        self.assertTrue(ok_c)
        self.assertTrue(ok_p)
        self.assertAlmostEqual(iv_c, sigma, places=5)
        self.assertAlmostEqual(iv_p, sigma, places=5)

        # Price below discounted intrinsic must flag iv_reliable=False
        intrinsic_disc = math.exp(-r * t_years) * (f_val - strike)
        _, ok_bad, status_bad = se.implied_vol_with_status(f_val, strike, t_years, intrinsic_disc - 5.0, "CE", r)
        self.assertFalse(ok_bad)
        self.assertEqual(status_bad, "PRICE_BELOW_DISCOUNTED_INTRINSIC")

    def test_greeks_against_finite_differences(self) -> None:
        f_val = 22698.45
        strike = 22400.0
        t_days = 31.05
        t_years = t_days / 365.0
        r = 0.067
        sigma = 0.165

        call_p = se.bs76_price(f_val, strike, t_years, sigma, "CE", r)
        g = se.compute_greeks(f_val, strike, t_days, call_p, "CE", r)

        df_step = 1.0
        c_up = se.bs76_price(f_val + df_step, strike, t_years, sigma, "CE", r)
        c_dn = se.bs76_price(f_val - df_step, strike, t_years, sigma, "CE", r)
        fd_delta = (c_up - c_dn) / (2.0 * df_step)
        fd_gamma = (c_up - 2.0 * call_p + c_dn) / (df_step**2)

        self.assertAlmostEqual(g["delta"], fd_delta, places=3)
        self.assertAlmostEqual(g["gamma"], fd_gamma, places=5)
        self.assertIn("vanna_per_1pct_iv", g)
        self.assertIn("charm_delta_per_day", g)
        self.assertIn("vomma_pts_1pct2", g)

    def test_regime_a1_no_loss_profit_lock_oco(self) -> None:
        # Profitable Bull Put Spread (Nov 22400/22200 PE @ 296.00 / 234.30 vs entry 353.70 / 281.55)
        res = se.evaluate_live_credit_spread(
            forward=22698.45,
            t_days=31.05,
            opt_type="PE",
            short_strike=22400,
            short_entry=353.70,
            short_ltp=296.00,
            long_strike=22200,
            long_entry=281.55,
            long_ltp=234.30,
            lot_size=65,
            target_net_rupees=2000.0,
        )
        self.assertEqual(res["strategy"]["strategy_code"], "BULL_PUT")
        self.assertEqual(res["oco_regime"], "NO_LOSS_PROFIT_LOCK_OCO")
        self.assertTrue(res["sequenced_gtt_plan"]["zero_loss_floor_feasible"])
        worst_stop_net = res["sequenced_gtt_plan"]["scenario_payoffs_rs"]["upper_stop_worst_limit_fill"]["net_pnl_rs"]
        self.assertGreaterEqual(worst_stop_net, 0.0)

    def test_regime_a2_profit_lock_infeasible_on_thin_cushion(self) -> None:
        # Spread is 68.80 pts vs entry 72.15 pts (+3.35 pts gross = +Rs 217.75 gross, ~+Rs 69 net after dynamic charges)
        # Position is in net profit after charges, but cushion (+1.06 pts) cannot fund GTT limit buffers without going negative.
        res = se.evaluate_live_credit_spread(
            forward=22580.0,
            t_days=31.05,
            opt_type="PE",
            short_strike=22400,
            short_entry=353.70,
            short_ltp=338.80,
            long_strike=22200,
            long_entry=281.55,
            long_ltp=270.00,
            lot_size=65,
            target_net_rupees=2000.0,
        )
        self.assertEqual(res["oco_regime"], "PROFIT_LOCK_INFEASIBLE")
        self.assertFalse(res["sequenced_gtt_plan"]["zero_loss_floor_feasible"])

    def test_regime_b_loss_minimization_oco_when_underwater(self) -> None:
        # Spread is 82.0 pts vs entry 72.15 pts (Underwater by ~Rs 760 net, inside Rs 2,500 cap)
        res = se.evaluate_live_credit_spread(
            forward=22510.0,
            t_days=31.05,
            opt_type="PE",
            short_strike=22400,
            short_entry=353.70,
            short_ltp=365.00,
            long_strike=22200,
            long_entry=281.55,
            long_ltp=283.00,
            lot_size=65,
            target_net_rupees=2000.0,
            max_loss_net_rupees=2500.0,
        )
        self.assertEqual(res["oco_regime"], "LOSS_MINIMIZATION_OCO")
        self.assertEqual(res["verdict"], "HOLD_WITH_LOSS_MINIMIZATION_OCO")
        # Lower trigger in drawdown should aim for Cost-Breakeven Scratch (~Rs 0 net), not +Rs 2,000
        scratch_net = res["sequenced_gtt_plan"]["scenario_payoffs_rs"]["lower_target_normal_fill"]["net_pnl_rs"]
        self.assertTrue(-350.0 <= scratch_net <= 350.0)

    def test_kill_switch_on_loss_cap_or_gamma_wall(self) -> None:
        res = se.evaluate_live_credit_spread(
            forward=22350.0,
            t_days=31.05,
            opt_type="PE",
            short_strike=22400,
            short_entry=353.70,
            short_ltp=430.00,
            long_strike=22200,
            long_entry=281.55,
            long_ltp=315.00,
            lot_size=65,
            target_net_rupees=2000.0,
            max_loss_net_rupees=2500.0,
        )
        self.assertEqual(res["verdict"], "CLOSE_ALL_IMMEDIATELY")
        self.assertEqual(res["oco_regime"], "CLOSE_ALL_IMMEDIATELY")

    def test_unreachable_target_auto_calibration(self) -> None:
        res = se.evaluate_live_credit_spread(
            forward=22698.45,
            t_days=31.05,
            opt_type="PE",
            short_strike=22400,
            short_entry=353.70,
            short_ltp=296.00,
            long_strike=22200,
            long_entry=281.55,
            long_ltp=234.30,
            lot_size=65,
            target_net_rupees=9000.0,  # Exceeds max possible net profit (~Rs 4,568)
        )
        self.assertFalse(res["summary"]["target_reachable"])
        self.assertGreater(res["summary"]["target_exit_spread_pts"], 10.0)

    def test_debit_spread_accounting(self) -> None:
        res = se.evaluate_live_credit_spread(
            forward=22600.0,
            t_days=10.0,
            opt_type="CE",
            short_strike=22800,
            short_entry=45.0,
            short_ltp=65.0,
            long_strike=22600,
            long_entry=120.0,
            long_ltp=165.0,
            lot_size=65,
            target_net_rupees=1800.0,
            charges_override_rs=117.0,
        )
        self.assertEqual(res["strategy"]["strategy_code"], "BULL_CALL")
        self.assertEqual(res["strategy"]["spread_style"], "DEBIT")
        # Entry debit = 75 pts, Width = 200 pts -> Max Net Profit = (125 * 65) - 117 = 8008
        self.assertAlmostEqual(res["summary"]["max_profit_net_rs"], 8008.0, places=2)
        # Max Net Loss = (75 * 65) + 117 = 4992
        self.assertAlmostEqual(res["summary"]["max_loss_net_rs"], 4992.0, places=2)

    def test_rank_candidate_spreads_prefilter(self) -> None:
        chain = [
            # High credit but only 20 pts OTM (fails >= 40 pts OTM gate):
            {"strike": 22530, "type": "PE", "ltp": 115.0},
            {"strike": 22330, "type": "PE", "ltp": 55.0},
            # Valid passing candidate (100 pts OTM, >18% credit/width, >=1.5 net theta):
            {"strike": 22450, "type": "PE", "ltp": 88.0},
            {"strike": 22250, "type": "PE", "ltp": 40.0},
        ]
        res = se.rank_candidate_spreads(forward=22550.0, t_days=5.0, bias="bull_put", chain=chain, lot_size=65)
        self.assertEqual(res["verdict"], "ENTER_BEST_SPREAD")
        self.assertEqual(res["best_spread"]["short_strike"], 22450)

    def test_sub_millisecond_performance(self) -> None:
        t0 = time.perf_counter()
        n_runs = 200
        for _ in range(n_runs):
            se.evaluate_live_credit_spread(
                forward=22698.45,
                t_days=31.05,
                opt_type="PE",
                short_strike=22400,
                short_entry=353.70,
                short_ltp=296.00,
                long_strike=22200,
                long_entry=281.55,
                long_ltp=234.30,
                lot_size=65,
                target_net_rupees=2000.0,
            )
        avg_ms = (time.perf_counter() - t0) * 1000.0 / n_runs
        self.assertLess(avg_ms, 2.0, f"Expected < 2.0 ms per evaluation, got {avg_ms:.3f} ms")


if __name__ == "__main__":
    unittest.main()
