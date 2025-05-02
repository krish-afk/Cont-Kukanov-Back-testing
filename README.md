# Cont & Kukanov Smart Order Router Backtest

This repository contains a back-testing implementation of the static cost model from Cont & Kukanov’s "Optimal Order Placement in Limit Order Markets". The router splits a 5,000-share buy order across multiple venues, tunes three risk parameters, and benchmarks against three baselines.

---

## Files

* **backtest.py**
  Standalone Python 3.8+ script (uses only `numpy`, `pandas`, stdlib). Reads `l1_day.csv`, runs the allocator, benchmarks, and prints a single JSON to stdout.

* **l1\_day.csv**
  \~60 000 level-1 snapshots from 13:36:32–13:45:14 UTC on 1 Aug 2024.

---

## Usage

```bash
python backtest.py
```

The script runs in <2 minutes on a modern laptop and outputs a JSON object with:

1. **`best_params`**: tuned `lambda_over`, `lambda_under`, `theta_queue`
2. **`optimized`**: total cash & average fill price for those params
3. **`baseline`**: same metrics for Best-Ask, 60 s TWAP, and VWAP
4. **`savings_bps`**: basis-point improvements versus each baseline

---

## Code Structure

1. **`compute_cost(split, venues, S, λo, λu, θ)`**
   Implements the Cont–Kukanov cost function (fees, rebates, under/overfill penalties, queue risk).
2. **`allocate(order_size, venues, λo, λu, θ)`**
   Brute-force search in 100-share increments across venues, picks the split minimizing `compute_cost`.
3. **Data loading & snapshots**
    * Reads l1_day.csv and parses per-venue snapshots by timestamp

    * Deduplicates (ts_event, publisher_id) pairs

    * Converts prices/sizes into dictionaries used for routing decisions

4. **`run_backtest(λo, λu, θ)`**

   * Iterates through all snapshots while filling a 5,000-share order
   * At each step, uses `allocate()` to determine optimal venue split
   * Accumulates cash cost and fill volume, rolls forward remainder
   
5. **Parameter search**

   * Define 100 evenly spaced values for each of the three risk parameters
   * Randomly sample 5 000 unique `(λo, λu, θ)` triples
   * Keep the combination with lowest total cost
6. **Baselines**

   * **Best-Ask**: hit the lowest ask each snapshot
   * **TWAP60s**: split shares equally into 60 s buckets
   * **VWAP**: static VWAP price weighted by displayed size
7. **Output**
   Prints the final JSON object with all metrics.

---

## Parameter Search Details

* **`lambda_over`**: 100 values in \[0.01, 0.10]
* **`lambda_under`**: 100 values in \[0.05, 0.20]
* **`theta_queue`**: 100 values in \[0.0001, 0.0010]
* **Sampling**: 5 000 random triples to cover combinations without full 1 000 000-grid evaluation

---

## Suggested Improvement for Realism

**Incorporate dynamic slippage & queue position:**

* Model a simple slippage function that increases the effective ask price as cumulative execution in a snapshot grows.
* Track each limit order’s queue position and simulate partial fills from the front of the queue before marketable orders drain deeper levels.

This would more accurately capture adverse selection and depth dynamics beyond top-of-book static sizes.
