#!/usr/bin/env python3
import argparse, json, random

""""usage
python3 split.py --in training_set.json --out-train split_train.json --out-val split_val.json --val-frac 0.1 --seed 42
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out-train", required=True)
    ap.add_argument("--out-val", required=True)
    ap.add_argument("--out-test", default=None)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--test-frac", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rnd = random.Random(args.seed)
    rnd.shuffle(data)

    n = len(data)
    n_test = int(n * args.test_frac)
    n_val = int(n * args.val_frac)

    test = data[:n_test] if n_test else []
    val = data[n_test:n_test + n_val]
    train = data[n_test + n_val:]

    with open(args.out_train, "w", encoding="utf-8") as f:
        json.dump(train, f, ensure_ascii=False)
    with open(args.out_val, "w", encoding="utf-8") as f:
        json.dump(val, f, ensure_ascii=False)
    if args.out_test:
        with open(args.out_test, "w", encoding="utf-8") as f:
            json.dump(test, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
