# gentlr

`gentlr` is a real-ML Activity Monitor triage agent for macOS. It scores local processes with a shared lightweight supervisor, so you can watch up to 30 app policies without launching 30 RAM-eating ML runtimes.

- real `StandardScaler`
- real `PCA`
- real `KMeans`
- real `SVM`
- real `RandomForest`
- real `GradientBoosting`
- real `XGBoost`

It defaults to dry-run. It will not close protected apps such as Codex, Devin, Windsurf, Terminal, Finder, frontmost apps, system processes, shells, or core Apple services.

## Bootstrap

```sh
./bootstrap.sh
```

## Run

```sh
./.venv/bin/python ./gentlr.py
```

## Floating Organism UI

```sh
./gentlr-ui
```

The widget stays on top, shows memory pressure, pulses like a small organism, and exposes menu/button controls for training, dry refresh, watching, and one-at-a-time safe apply.

## Train Real ML

```sh
./.venv/bin/python ./gentlr.py --train
```

## Initialize 30 App Policies

```sh
./.venv/bin/python ./gentlr.py --init-policies
```

## Shared Supervisor

```sh
./.venv/bin/python ./gentlr.py --supervise
```

## Close Safe Candidates

```sh
./.venv/bin/python ./gentlr.py --apply --threshold 0.90 --max-kill 2
```

## Identity

```sh
./.venv/bin/python ./gentlr.py --identity
```

This prints the name as `base2 -> base64 -> lambda`.

## Recommended Use

Run dry for a few passes first. If the same harmless helpers keep ranking high, use `--apply` with a high threshold. The defaults are intentionally gentle.
