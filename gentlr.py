#!/usr/bin/env python3
"""
gentlr: real-ML macOS process triage and per-app watcher supervisor.

It uses real sklearn/XGBoost models:
- StandardScaler
- PCA
- KMeans
- SVM
- RandomForest
- GradientBoosting
- XGBoost

The default mode is dry-run. `--apply` is required before anything is closed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import time
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "gentlr-model.joblib"
EVENTS_PATH = ROOT / "gentlr-events.ndjson"
POLICY_PATH = ROOT / "gentlr-policies.json"
POLICY_TEMPLATE_NAMES = [
    "Code Helper (Plugin)",
    "Code Helper (GPU)",
    "Google Chrome Helper (GPU)",
    "Google Chrome Helper (Plugin)",
    "Microsoft Edge Helper (GPU)",
    "Microsoft Edge Helper (Plugin)",
    "Slack Helper (GPU)",
    "Slack Helper (Plugin)",
    "Discord Helper (GPU)",
    "Discord Helper (Plugin)",
    "Notion Helper (GPU)",
    "Notion Helper (Plugin)",
    "Figma Helper (GPU)",
    "Figma Helper (Plugin)",
    "Dropbox Helper",
    "Google Drive Helper",
    "OneDrive Finder Integration",
    "Crashpad",
    "Updater",
    "Telemetry",
    "Language Server",
    "node server",
    "python server",
    "Electron Helper",
    "Renderer Helper",
    "GPU Helper",
    "Plugin Helper",
    "background helper",
    "sync helper",
    "index helper",
]

PROTECTED_NAMES = {
    "Activity Monitor",
    "Codex",
    "Devin",
    "Finder",
    "Terminal",
    "iTerm2",
    "loginwindow",
    "launchd",
    "WindowServer",
    "kernel_task",
    "zsh",
    "bash",
    "ssh",
    "tmux",
    "screen",
    "python",
    "python3",
    "Python",
    "Python3",
    "node",
    "Node",
    "git",
    "rg",
    "swift",
    "swiftc",
    "swift-frontend",
    "clang",
    "clang++",
    "ld",
    "make",
    "cmake",
    "Code",
    "Visual Studio Code",
    "Microsoft Edge",
    "Google Chrome",
    "Safari",
    "Arc",
    "Slack",
    "Notion",
    "Discord",
}

PROTECTED_SUBSTRINGS = (
    "/System/",
    "/usr/libexec/",
    "com.apple.",
    "Activity Monitor",
    "Codex",
    "Devin",
    "Windsurf",
    "Terminal",
    "iTerm",
    "Chrome Helper (Renderer)",
    "Codex (Renderer)",
    "Codex (Service)",
    "Devin Helper",
    "Microsoft Edge Helper (Renderer)",
)

POLICY_DENY_NAMES = {
    "Code",
    "Visual Studio Code",
    "Microsoft Edge",
    "Google Chrome",
    "Safari",
    "Arc",
    "Codex",
    "codex",
    "Codex (Renderer)",
    "Codex (Service)",
    "Devin",
    "Devin Helper",
    "Devin Helper (Renderer)",
    "Devin Helper (Plugin)",
    "Devin Helper (GPU)",
    "Python",
    "Terminal",
    "iTerm2",
    "Finder",
}

SYSTEM_POLICY_DENY_SUBSTRINGS = (
    "com.apple.",
    "CoreServices",
    "CoreLocation",
    "ControlCenter",
    "Spotlight",
    "corespotlight",
    "sharingd",
    "homed",
    "duet",
    "siri",
    "knowledge-agent",
    "heard",
)

APP_HELPER_HINTS = (
    "Helper",
    "Renderer",
    "GPU",
    "Plugin",
    "Crashpad",
    "Telemetry",
    "Updater",
    "Language Server",
    "Code Helper",
    "Electron",
)


def ensure_vendor_path() -> None:
    """Keep /Users/alep/Downloads/math.py from shadowing stdlib math."""
    script_dir = str(ROOT)
    downloads = str(ROOT.parent)
    sys.path[:] = [p for p in sys.path if p not in {"", script_dir, downloads}]


ensure_vendor_path()

try:
    import joblib
    import numpy as np
    import psutil
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.metrics import silhouette_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    from xgboost import XGBClassifier
except Exception as exc:  # pragma: no cover - this is an operator-facing failure path
    print("gentlr requires the local real-ML venv:", exc, file=sys.stderr)
    print("Run: /Users/alep/Downloads/gentlr/bootstrap.sh", file=sys.stderr)
    raise


@dataclass
class ProcSample:
    pid: int
    ppid: int
    name: str
    username: str
    rss_mb: float
    cpu_pct: float
    age_min: float
    threads: int
    fds: int
    status: str
    cmdline: str

    def vector(self) -> list[float]:
        text = f"{self.name} {self.cmdline}".lower()
        return [
            self.rss_mb,
            self.cpu_pct,
            self.age_min,
            float(self.threads),
            float(self.fds),
            1.0 if self.status in {"sleeping", "idle"} else 0.0,
            1.0 if any(h.lower() in text for h in APP_HELPER_HINTS) else 0.0,
            1.0 if "server" in text or "language" in text else 0.0,
            1.0 if "crash" in text or "telemetry" in text or "updater" in text else 0.0,
            float(len(self.cmdline)),
        ]


def encoded_name(name: str = "gentlr") -> str:
    bits = "".join(format(byte, "08b") for byte in name.encode())
    return "lambda:" + base64.b64encode(bits.encode()).decode()


def frontmost_app() -> str:
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        return subprocess.check_output(["osascript", "-e", script], text=True, timeout=1).strip()
    except Exception:
        return ""


def process_samples() -> list[ProcSample]:
    now = time.time()
    rows: list[ProcSample] = []
    attrs = ["pid", "ppid", "name", "username", "memory_info", "cpu_percent", "create_time", "num_threads", "status", "cmdline"]
    try:
        iterator = psutil.process_iter(attrs)
    except Exception:
        return rows
    for proc in iterator:
        try:
            info = proc.info
            mem = info.get("memory_info")
            cmd = " ".join(info.get("cmdline") or [])
            rows.append(
                ProcSample(
                    pid=int(info["pid"]),
                    ppid=int(info.get("ppid") or 0),
                    name=str(info.get("name") or ""),
                    username=str(info.get("username") or ""),
                    rss_mb=float((mem.rss if mem else 0) / (1024 * 1024)),
                    cpu_pct=float(info.get("cpu_percent") or 0.0),
                    age_min=max(0.0, (now - float(info.get("create_time") or now)) / 60.0),
                    threads=int(info.get("num_threads") or 0),
                    fds=int(proc.num_fds()) if hasattr(proc, "num_fds") else 0,
                    status=str(info.get("status") or ""),
                    cmdline=cmd,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, PermissionError):
            continue
    return rows


def protected_reason(sample: ProcSample, frontmost: str) -> str | None:
    haystack = f"{sample.name} {sample.cmdline}"
    if sample.pid in {0, 1, os.getpid(), os.getppid()}:
        return "core/self"
    if sample.username and sample.username != psutil.Process().username():
        return "other-user"
    if sample.name in PROTECTED_NAMES:
        return "protected-name"
    if frontmost and sample.name == frontmost:
        return "frontmost"
    for needle in PROTECTED_SUBSTRINGS:
        if needle in haystack:
            return f"protected:{needle}"
    return None


def pseudo_label(sample: ProcSample) -> int:
    text = f"{sample.name} {sample.cmdline}".lower()
    helper = any(h.lower() in text for h in APP_HELPER_HINTS)
    waste = ("telemetry" in text) or ("crashpad" in text) or ("updater" in text)
    idle = sample.status in {"sleeping", "idle"} and sample.cpu_pct < 1.5
    large = sample.rss_mb >= 350
    medium_helper = sample.rss_mb >= 150 and helper and idle
    old_helper = sample.age_min >= 30 and helper and idle
    if waste and idle:
        return 1
    if large and helper and idle:
        return 1
    if medium_helper and old_helper:
        return 1
    return 0


def feature_matrix(samples: list[ProcSample]) -> np.ndarray:
    return np.asarray([sample.vector() for sample in samples], dtype=np.float64)


def train_model(samples: list[ProcSample]) -> dict[str, Any]:
    frontmost = frontmost_app()
    trainable = [s for s in samples if protected_reason(s, frontmost) is None]
    if len(trainable) < 8:
        raise RuntimeError("not enough visible process samples to train")
    x = feature_matrix(trainable)
    y = np.asarray([pseudo_label(s) for s in trainable], dtype=np.int64)
    if len(set(y.tolist())) < 2:
        # Force a conservative negative class and a small positive class from top RSS helpers.
        order = np.argsort(x[:, 0])
        y[:] = 0
        for idx in order[-max(1, min(3, len(order) // 8)):]:
            if trainable[int(idx)].rss_mb >= 100:
                y[int(idx)] = 1
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    n_components = max(1, min(3, x_scaled.shape[0], x_scaled.shape[1]))
    pca = PCA(n_components=n_components, random_state=42)
    x_pca = pca.fit_transform(x_scaled)
    k = max(2, min(4, len(trainable) // 5))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(x_pca)
    x_aug = np.hstack([x_scaled, x_pca, clusters.reshape(-1, 1)])
    models: dict[str, Any] = {
        "svm": SVC(C=1.0, kernel="rbf", probability=True, class_weight="balanced", random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=80, max_depth=5, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=1),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=80, learning_rate=0.05, max_depth=2, random_state=42),
        "xgboost": XGBClassifier(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            n_jobs=1,
            random_state=42,
        ),
    }
    fitted = {}
    for name, model in models.items():
        model.fit(x_aug, y)
        fitted[name] = model
    try:
        silhouette = float(silhouette_score(x_pca, clusters)) if len(set(clusters.tolist())) > 1 else 0.0
    except Exception:
        silhouette = 0.0
    bundle = {
        "created_at": time.time(),
        "feature_names": ["rss_mb", "cpu_pct", "age_min", "threads", "fds", "idle", "helper_hint", "server_hint", "waste_hint", "cmdline_len"],
        "scaler": scaler,
        "pca": pca,
        "kmeans": kmeans,
        "models": fitted,
        "train_rows": len(trainable),
        "positive_rows": int(y.sum()),
        "pca_explained_variance": [float(v) for v in pca.explained_variance_ratio_],
        "silhouette": silhouette,
    }
    joblib.dump(bundle, MODEL_PATH)
    return bundle


def load_or_train(samples: list[ProcSample], force: bool = False) -> dict[str, Any]:
    if MODEL_PATH.exists() and not force:
        try:
            return joblib.load(MODEL_PATH)
        except Exception:
            pass
    return train_model(samples)


def predict(bundle: dict[str, Any], samples: list[ProcSample]) -> list[dict[str, Any]]:
    if not samples:
        return []
    x = feature_matrix(samples)
    x_scaled = bundle["scaler"].transform(x)
    x_pca = bundle["pca"].transform(x_scaled)
    clusters = bundle["kmeans"].predict(x_pca).reshape(-1, 1)
    x_aug = np.hstack([x_scaled, x_pca, clusters])
    scores = []
    for sample, pca_row, cluster, row in zip(samples, x_pca, clusters.flatten(), x_aug):
        probs = []
        model_scores = {}
        for name, model in bundle["models"].items():
            if hasattr(model, "predict_proba"):
                prob = float(model.predict_proba(row.reshape(1, -1))[0][1])
            else:
                prob = float(model.predict(row.reshape(1, -1))[0])
            probs.append(prob)
            model_scores[name] = prob
        score = float(np.mean(probs))
        scores.append(
            {
                "score": score,
                "pid": sample.pid,
                "name": sample.name,
                "rss_mb": sample.rss_mb,
                "cpu_pct": sample.cpu_pct,
                "age_min": sample.age_min,
                "cluster": int(cluster),
                "pca": [float(v) for v in pca_row],
                "models": model_scores,
                "sample": sample,
            }
        )
    return sorted(scores, key=lambda item: item["score"], reverse=True)


def terminate(sample: ProcSample, gentle_seconds: float = 4.0) -> str:
    try:
        proc = psutil.Process(sample.pid)
        proc.terminate()
        try:
            proc.wait(timeout=gentle_seconds)
            return "terminated"
        except psutil.TimeoutExpired:
            os.kill(sample.pid, signal.SIGKILL)
            return "killed-after-timeout"
    except (psutil.NoSuchProcess, ProcessLookupError):
        return "already-gone"
    except psutil.AccessDenied:
        return "access-denied"


def default_policies(samples: list[ProcSample], limit: int = 30) -> dict[str, Any]:
    apps = []
    frontmost = frontmost_app()
    for sample in sorted(samples, key=lambda s: s.rss_mb, reverse=True):
        haystack = f"{sample.name} {sample.cmdline}"
        helper_like = any(h.lower() in haystack.lower() for h in APP_HELPER_HINTS)
        denied = sample.name in POLICY_DENY_NAMES or any(s.lower() in haystack.lower() for s in SYSTEM_POLICY_DENY_SUBSTRINGS)
        if (
            all(app["name"] != sample.name for app in apps)
            and protected_reason(sample, frontmost) is None
            and helper_like
            and not denied
            and sample.rss_mb >= 60
        ):
            apps.append(
                {
                    "name": sample.name,
                    "enabled": True,
                    "threshold": 0.94,
                    "max_kill_per_cycle": 1,
                    "min_rss_mb": 120,
                }
            )
        if len(apps) >= limit:
            break
    for name in POLICY_TEMPLATE_NAMES:
        if len(apps) >= limit:
            break
        if all(app["name"] != name for app in apps):
            apps.append(
                {
                    "name": name,
                    "enabled": False,
                    "threshold": 0.95,
                    "max_kill_per_cycle": 1,
                    "min_rss_mb": 150,
                }
            )
    policies = {
        "version": 1,
        "apps": apps,
    }
    POLICY_PATH.write_text(json.dumps(policies, indent=2) + "\n")
    return policies


def load_policies(samples: list[ProcSample]) -> dict[str, Any]:
    if POLICY_PATH.exists():
        return json.loads(POLICY_PATH.read_text())
    return default_policies(samples)


def append_event(event: dict[str, Any]) -> None:
    with EVENTS_PATH.open("a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def print_ranked(items: list[dict[str, Any]], limit: int) -> None:
    print("score  rssMB   cpu  pid    cluster  name")
    print("-----  ------  ---  -----  -------  ----")
    for item in items[:limit]:
        print(f"{item['score']:.2f}  {item['rss_mb']:6.1f}  {item['cpu_pct']:3.0f}  {item['pid']:5d}  {item['cluster']:7d}  {item['name'][:42]}")


def snapshot(limit: int = 5, train: bool = False, min_rss_mb: float = 80.0) -> dict[str, Any]:
    samples = process_samples()
    if not samples:
        return {"ok": False, "error": "no process samples", "items": []}
    bundle = load_or_train(samples, force=train)
    frontmost = frontmost_app()
    candidates = [s for s in samples if protected_reason(s, frontmost) is None and s.rss_mb >= min_rss_mb]
    ranked = predict(bundle, candidates)
    vm = psutil.virtual_memory()
    return {
        "ok": True,
        "identity": encoded_name(),
        "total_rss_mb": sum(s.rss_mb for s in samples),
        "available_mb": vm.available / (1024 * 1024),
        "used_pct": vm.percent,
        "samples": len(samples),
        "candidates": len(candidates),
        "model": {
            "train_rows": bundle["train_rows"],
            "positive_rows": bundle["positive_rows"],
            "pca_explained_variance": bundle["pca_explained_variance"],
            "silhouette": bundle["silhouette"],
        },
        "items": [{k: v for k, v in item.items() if k != "sample"} for item in ranked[:limit]],
    }


def run_ui(args: argparse.Namespace) -> int:
    widget = ROOT / "GentlrWidget"
    if not widget.exists():
        subprocess.check_call([str(ROOT / "build-ui.sh")])
    os.execv(str(widget), [str(widget)])


def run_once(args: argparse.Namespace) -> int:
    samples = process_samples()
    if not samples:
        print("No process samples available. Grant process-list visibility or run from Terminal.")
        return 2
    frontmost = frontmost_app()
    bundle = load_or_train(samples, force=args.train)
    candidates = [s for s in samples if protected_reason(s, frontmost) is None and s.rss_mb >= args.min_rss_mb]
    ranked = predict(bundle, candidates)
    print(f"gentlr identity={encoded_name()} mode={'apply' if args.apply else 'dry-run'} samples={len(samples)} candidates={len(candidates)}")
    print(f"model rows={bundle['train_rows']} positives={bundle['positive_rows']} pca_var={bundle['pca_explained_variance']} silhouette={bundle['silhouette']:.3f}")
    print_ranked(ranked, args.limit)
    if not args.apply:
        print("\ndry-run only; add --apply to close high-confidence candidates.")
        return 0
    closed = 0
    for item in ranked:
        if closed >= args.max_kill or item["score"] < args.threshold:
            break
        sample = item["sample"]
        if protected_reason(sample, frontmost_app()) is not None:
            continue
        result = terminate(sample, args.gentle_seconds)
        event = {k: v for k, v in item.items() if k != "sample"}
        event.update({"ts": time.time(), "action": result})
        append_event(event)
        print(f"{result}: pid={sample.pid} name={sample.name} score={item['score']:.2f}")
        closed += 1
    print(f"closed={closed}")
    return 0


def run_json(args: argparse.Namespace) -> int:
    data = snapshot(limit=args.limit, train=args.train, min_rss_mb=args.min_rss_mb)
    print(json.dumps(data, indent=2))
    return 0 if data.get("ok") else 2


def supervise(args: argparse.Namespace) -> int:
    samples = process_samples()
    if not samples:
        print("No process samples available. Grant process-list visibility or run from Terminal.")
        return 2
    policies = load_policies(samples)
    print(f"gentlr supervisor policies={len(policies.get('apps', []))} interval={args.interval}s mode={'apply' if args.apply else 'dry-run'}")
    while True:
        cycle_args = argparse.Namespace(**vars(args))
        cycle_args.limit = args.limit
        cycle_args.max_kill = 0
        samples = process_samples()
        bundle = load_or_train(samples, force=False)
        frontmost = frontmost_app()
        total_closed = 0
        for policy in policies.get("apps", [])[:30]:
            if not policy.get("enabled", True):
                continue
            name = str(policy.get("name", ""))
            app_samples = [
                s for s in samples
                if name.lower() in f"{s.name} {s.cmdline}".lower()
                and s.rss_mb >= float(policy.get("min_rss_mb", args.min_rss_mb))
                and protected_reason(s, frontmost) is None
            ]
            ranked = predict(bundle, app_samples)
            for item in ranked:
                if total_closed >= args.max_kill_per_cycle:
                    break
                if item["score"] < float(policy.get("threshold", args.threshold)):
                    break
                if not args.apply:
                    print(f"would-close app={name} pid={item['pid']} score={item['score']:.2f} rss={item['rss_mb']:.1f}")
                    continue
                result = terminate(item["sample"], args.gentle_seconds)
                event = {k: v for k, v in item.items() if k != "sample"}
                event.update({"ts": time.time(), "app_policy": name, "action": result})
                append_event(event)
                print(f"{result} app={name} pid={item['pid']} score={item['score']:.2f}")
                total_closed += 1
        if args.once:
            break
        time.sleep(args.interval)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-ML gentle process optimizer.")
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--train", action="store_true", help="Retrain the real ML bundle from current process samples.")
    parser.add_argument("--apply", action="store_true", help="Actually terminate high-confidence candidates.")
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--min-rss-mb", type=float, default=100.0)
    parser.add_argument("--max-kill", type=int, default=2)
    parser.add_argument("--max-kill-per-cycle", type=int, default=3)
    parser.add_argument("--gentle-seconds", type=float, default=4.0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--supervise", action="store_true", help="Run one shared per-app watcher supervisor.")
    parser.add_argument("--ui", action="store_true", help="Open floating microorganism widget UI.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable real-ML snapshot.")
    parser.add_argument("--once", action="store_true", help="In supervisor mode, run one cycle and exit.")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--init-policies", action="store_true", help="Create up to 30 app policies from current processes.")
    args = parser.parse_args()
    if args.identity:
        print(encoded_name())
        return 0
    samples = process_samples()
    if args.init_policies:
        policies = default_policies(samples)
        print(POLICY_PATH)
        print(json.dumps(policies, indent=2))
        return 0
    if args.ui:
        return run_ui(args)
    if args.json:
        return run_json(args)
    if args.supervise:
        return supervise(args)
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
