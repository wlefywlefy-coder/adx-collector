# FORWARD_PROTOCOL — frozen on 2026-11-03 (before the first logged signal)

Paper test only. No money, no orders. Long-only. Universe: the 10 ADX Sharia names
(ADNOCGAS, ADNOCDRILL, ADIB, ALPHADHABI, BOROUGE, ALDAR, ADNOCLS, ADNOCDIST, FERTIGLB, PRESIGHT).
Do not change anything below until at least 30 closed signals per rule AND 8 weeks have passed.
Any change is a new protocol with a new start date, and the old results stay as they are.

## Inputs
Snapshots written by collect.py every 15 minutes (data/YYYY-MM-DD/HHMM.json, UTC).
Entry window 06:30-09:30 UTC (10:30-13:30 Dubai), session must be Trading.

## Activity ratio
act = value traded so far today / median of the value traded at the same time on each of the previous 5 days (at least 3 prior days needed; before that no signals are produced).

## Rules (first trigger per symbol, per rule, per day)
- R1 breakout: last > previous day's high AND act >= 1.5 AND last >= today's open AND change from previous close <= +4%.
- R2 strong momentum: change from previous close >= +1.5% AND last in the top 20% of today's range AND act >= 1.5 AND change <= +4%.

## Paper trade
Entry at the snapshot's last price. Target +1.0%, stop -0.8% from entry, otherwise exit at the final snapshot at/after 10:45 UTC (14:45 Dubai).
Target/stop detection uses the running day high/low between snapshots; if both could be hit in one interval the stop counts first (conservative).
Costs: 0.315% round trip commission plus the per-stock spread table in forward.py.

## Judgement (nothing is judged before 30 closed signals per rule)
Mean net return per trade, win rate, profit factor, and excess over an equal-weight basket of the same 10 names held over the same window.
Acceptance follows the ADX-Lab limits: mean net >= +0.20%, profit factor >= 1.2, positive excess, p<=0.05 vs random is checked in the weekly review.
Failing means the system stays a monitoring and avoidance tool only.
