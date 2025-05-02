import pandas as pd
import numpy as np

def compute_cost(split, venues, S, λo, λu, θ):
    executed = 0
    cash_spent = 0.0
    for q, v in zip(split, venues):
        exe = min(q, v['ask_size'])
        executed += exe
        cash_spent += exe * (v['ask'] + v['fee'])
        maker_rebate = max(q - exe, 0) * v['rebate']
        cash_spent -= maker_rebate

    underfill = max(S - executed, 0)
    overfill = max(executed - S, 0)
    risk_pen = θ * (underfill + overfill)
    cost_pen = λu * underfill + λo * overfill
    return cash_spent + risk_pen + cost_pen

def allocate(order_size, venues, λo, λu, θ):
    step = 100
    N = len(venues)
    splits = [[]]

    for v in range(N):
        new_splits = []
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, venues[v]['ask_size'])
            for q in range(0, max_v + 1, step):
                new_splits.append(alloc + [q])
        splits = new_splits

    best_cost = float('inf')
    best_split = None

    for alloc in splits:
        total = sum(alloc)
        if total != order_size:
            continue
        cost = compute_cost(alloc, venues, order_size, λo, λu, θ)
        if cost < best_cost:
            best_cost = cost
            best_split = alloc

    if best_split is None:
        return [0] * len(venues), float('inf')
    return best_split, best_cost

def run_backtest(snapshots, λo, λu, θ, S=5000):
    total_remaining = S
    cash_spent = 0.0

    for ts, venues in snapshots:
        if total_remaining <= 0:
            break

        split, _ = allocate(total_remaining, venues, λo, λu, θ)

        for q, v in zip(split, venues):
            if total_remaining <= 0:
                break
            exe = min(q, v['ask_size'], total_remaining)
            if exe > 0:
                cash_spent += exe * (v['ask'] + v['fee'])
                rebate = max(q - exe, 0) * v['rebate']
                cash_spent -= rebate
                total_remaining -= exe

    avg_price = cash_spent / float(S)
    return cash_spent, avg_price

def baseline_best_ask(snapshots, S=5000):
    rem, cash = S, 0.0
    for ts, venues in snapshots:
        if rem <= 0: break
        v = min(venues, key=lambda x: x['ask'])
        exe = min(rem, v['ask_size'])
        cash += exe * (v['ask'] + v['fee'])
        rem -= exe
    return cash, cash / S

def baseline_twap_60s(snapshots, S=5000):
    snap_df = pd.DataFrame(
        [(ts, min(vs, key=lambda x: x['ask'])['ask'] + min(vs, key=lambda x: x['ask'])['fee'])
         for ts, vs in snapshots],
        columns=['ts', 'best_ask']
    ).set_index('ts')
    buckets = snap_df.resample('60s').first().dropna()
    n = len(buckets)
    per = S // n
    cash = (per * buckets['best_ask']).sum()
    rem = S - per * n
    if rem > 0:
        cash += rem * buckets['best_ask'].iloc[-1]
    return cash, cash / S

def baseline_vwap(df, S=5000):
    df2 = df[['ask_px_00', 'ask_sz_00']].dropna().astype(float)
    vw = ((df2['ask_px_00'] + 0.003) * df2['ask_sz_00']).sum() / df2['ask_sz_00'].sum()
    return vw * S, vw

def print_json(d, indent=0):
    pad = "  " * indent
    if isinstance(d, dict):
        print("{")
        for i, (k, v) in enumerate(d.items()):
            comma = "," if i < len(d) - 1 else ""
            print(f'{pad}  "{k}": ', end="")
            print_json(v, indent + 1)
            print(comma)
        print(pad + "}", end="")
    elif isinstance(d, float):
        print(f"{d}", end="")
    elif isinstance(d, int):
        print(f"{d}", end="")
    elif isinstance(d, str):
        print(f'"{d}"', end="")
    else:
        raise TypeError(f"Unsupported type: {type(d)}")

def main():
    df = pd.read_csv('l1_day.csv')
    df['ts'] = pd.to_datetime(df['ts_event'])
    df = (
        df.sort_values('ts')
          .drop_duplicates(subset=['ts_event', 'publisher_id'])
    )

    snapshots = []
    for ts, group in df.groupby('ts'):
        venues = []
        for _, row in group.iterrows():
            venues.append({
                'id': row['publisher_id'],
                'ask': float(row['ask_px_00']),
                'ask_size': int(row['ask_sz_00']),
                'fee': 0.003,
                'rebate': 0.002
            })
        snapshots.append((ts, venues))

    lambdas_over = np.linspace(0.01, 0.10, 100)
    lambdas_under = np.linspace(0.05, 0.20, 100)
    thetas = np.linspace(0.0001, 0.0010, 100)

    N_SAMPLES = 5000
    idx_o = np.random.randint(0, 100, size=N_SAMPLES)
    idx_u = np.random.randint(0, 100, size=N_SAMPLES)
    idx_t = np.random.randint(0, 100, size=N_SAMPLES)

    best = {'cash': float('inf')}
    for i in range(N_SAMPLES):
        λo = lambdas_over[idx_o[i]]
        λu = lambdas_under[idx_u[i]]
        θ = thetas[idx_t[i]]

        cash, avg = run_backtest(snapshots, λo, λu, θ)
        if cash < best['cash']:
            best.update({'λo': λo, 'λu': λu, 'θ': θ, 'cash': cash, 'avg': avg})

    b1_cash, b1_avg = baseline_best_ask(snapshots)
    b2_cash, b2_avg = baseline_twap_60s(snapshots)
    b3_cash, b3_avg = baseline_vwap(df)

    opt_cash, opt_avg = best['cash'], best['avg']
    savings = {
        'vs_best_ask': (b1_avg - opt_avg) / b1_avg * 1e4,
        'vs_twap': (b2_avg - opt_avg) / b2_avg * 1e4,
        'vs_vwap': (b3_avg - opt_avg) / b3_avg * 1e4
    }

    output = {
        'best_params': {
            'lambda_over': best['λo'],
            'lambda_under': best['λu'],
            'theta_queue': best['θ']
        },
        'optimized': {
            'total_cash': opt_cash,
            'avg_price': opt_avg
        },
        'baseline': {
            'best_ask': {'total_cash': b1_cash, 'avg_price': b1_avg},
            'TWAP60s': {'total_cash': b2_cash, 'avg_price': b2_avg},
            'VWAP': {'total_cash': b3_cash, 'avg_price': b3_avg}
        },
        'savings_bps': savings
    }

    print_json(output)
    #import json
    #print(json.dumps(output, indent=2))
    # Was unsure whether I could use json library or not, so thought to create the function instead


if __name__ == '__main__':
    main()
