"""
Generating Function for the Bi-Periodic François Sequence
Algorithm Analysis and Performance Modeling.

This script evaluates the single generating function formulation and measures
runtime, throughput, peak memory usage, and optional CPU package energy using
Intel Power Gadget / RAPL logs when available.
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import subprocess
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt


PARAMETER_SETS: List[Tuple[str, float, float]] = [
    ("a=2,b=1", 2.0, 1.0),
    ("a=1,b=2", 1.0, 2.0),
    ("a=3,b=-2", 3.0, -2.0),
    ("a=1,b=1", 1.0, 1.0),
    ("a=1,b=0.25", 1.0, 0.25),
]


def xi(n: int) -> int:
    """Return the parity indicator used in the bi-periodic formulation."""
    return n - 2 * (n // 2)


def alpha_value(n: int, a: float, b: float) -> float:
    """Return the alternating coefficient alpha_n."""
    return (a * (1 - xi(n))) + (b * xi(n))


def theorem6_value(n: int, x: float, a: float, b: float) -> float:
    """Evaluate the closed-form generating function expression."""
    alpha = alpha_value(n, a, b)
    denom_core = 1.0 - alpha * x - x * x
    denom_full = (1.0 - x) * denom_core

    if abs(denom_core) < 1e-12 or abs(1.0 - x) < 1e-12 or abs(denom_full) < 1e-12:
        raise ZeroDivisionError(
            f"Denominator is very close to zero: n={n}, x={x}, a={a}, b={b}, alpha={alpha}"
        )

    part1 = (3 * a * b + 3 * a - 3 - (3 * a - 1) * alpha * x) / denom_core
    part2 = (alpha * x * x) / denom_full
    return part1 + part2


def theorem6_workload(iterations: int, a: float, b: float, x_values: List[float]) -> float:
    """Run the N-iteration workload."""
    total = 0.0
    x_len = len(x_values)
    for n in range(iterations):
        total += theorem6_value(n, x_values[n % x_len], a, b)
    return total


def find_powerlog_exe() -> Optional[Path]:
    """Locate Intel Power Gadget PowerLog executable on Windows."""
    candidates: List[Path] = []
    ipg_dir = os.environ.get("IPG_Dir")
    if ipg_dir:
        candidates.append(Path(ipg_dir) / "PowerLog3.0.exe")

    candidates.extend([
        Path(r"C:\Program Files\Intel\Power Gadget 3.6\PowerLog3.0.exe"),
        Path(r"C:\Program Files\Intel\Power Gadget\PowerLog3.0.exe"),
        Path(r"C:\Program Files\Intel\Intel Power Gadget 3.6\PowerLog3.0.exe"),
    ])

    for exe in candidates:
        if exe.exists():
            return exe
    return None


def start_powerlog(output_csv: Path, sample_ms: int, duration_s: int) -> Optional[subprocess.Popen]:
    """Start Intel Power Gadget logging if available."""
    exe = find_powerlog_exe()
    if exe is None:
        return None

    cmd = [str(exe), "-resolution", str(sample_ms), "-duration", str(duration_s), "-file", str(output_csv)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)


def parse_powerlog_csv(csv_path: Path) -> Dict[str, float]:
    """Parse Intel Power Gadget CSV output."""
    if not csv_path.exists():
        return {}

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        rows = list(csv.reader(f))

    header_idx = None
    for i, row in enumerate(rows):
        joined = ",".join(row).lower()
        if "time" in joined and ("power" in joined or "energy" in joined):
            header_idx = i
            break
    if header_idx is None:
        return {}

    header = [h.strip() for h in rows[header_idx]]
    data_rows = rows[header_idx + 1 :]

    def find_col(groups: List[List[str]]) -> Optional[int]:
        for idx, col in enumerate(header):
            lc = col.lower()
            for group in groups:
                if all(token in lc for token in group):
                    return idx
        return None

    idx_pkg_power = find_col([["package", "power"], ["pkg", "power"]])
    idx_pkg_energy = find_col([["package", "energy"], ["pkg", "energy"]])

    def to_float(value: str) -> Optional[float]:
        try:
            return float(value.strip().replace(",", "."))
        except Exception:
            return None

    pkg_powers: List[float] = []
    pkg_energies: List[float] = []
    for row in data_rows:
        if len(row) != len(header):
            continue
        if idx_pkg_power is not None:
            value = to_float(row[idx_pkg_power])
            if value is not None:
                pkg_powers.append(value)
        if idx_pkg_energy is not None:
            value = to_float(row[idx_pkg_energy])
            if value is not None:
                pkg_energies.append(value)

    result: Dict[str, float] = {}
    if pkg_powers:
        result["pkg_power_mean_w"] = statistics.mean(pkg_powers)
        result["pkg_power_min_w"] = min(pkg_powers)
        result["pkg_power_max_w"] = max(pkg_powers)
    if len(pkg_energies) >= 2:
        result["real_pkg_energy_j"] = pkg_energies[-1] - pkg_energies[0]
    return result


def safe_label(label: str) -> str:
    """Create a filesystem-safe label."""
    return label.replace("=", "").replace(",", "_").replace("-", "neg").replace(" ", "_").replace(".", "p")


def estimate_powerlog_duration(iterations: int) -> int:
    """Estimate PowerLog measurement duration according to workload size."""
    if iterations <= 10_000:
        return 30
    if iterations <= 100_000:
        return 45
    return 90


def run_single_test(
    iterations: int,
    config_name: str,
    a: float,
    b: float,
    run_id: int,
    output_dir: Path,
    x_values: List[float],
    use_ipg: bool,
    sample_ms: int,
) -> Dict[str, Any]:
    """Run one benchmark repetition."""
    run_dir = output_dir / f"iter_{iterations}" / safe_label(config_name) / f"run_{run_id:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    powerlog_csv = run_dir / "powerlog.csv"
    ipg_duration_s = estimate_powerlog_duration(iterations)

    proc = None
    if use_ipg:
        proc = start_powerlog(powerlog_csv, sample_ms=sample_ms, duration_s=ipg_duration_s)
        if proc is not None:
            time.sleep(1.0)

    tracemalloc.start()
    t0 = time.perf_counter()
    checksum = theorem6_workload(iterations=iterations, a=a, b=b, x_values=x_values)
    t1 = time.perf_counter()
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    runtime_s = t1 - t0
    if proc is not None:
        try:
            proc.wait(timeout=ipg_duration_s + 15)
        except subprocess.TimeoutExpired:
            proc.kill()

    result: Dict[str, Any] = {
        "iterations": iterations,
        "config_name": config_name,
        "a": a,
        "b": b,
        "run_id": run_id,
        "runtime_s": runtime_s,
        "time_per_iteration_us": (runtime_s / iterations) * 1_000_000.0,
        "throughput_iter_per_s": iterations / runtime_s if runtime_s > 0 else 0.0,
        "peak_memory_kb": peak_mem / 1024.0,
        "checksum": checksum,
        "powerlog_csv": str(powerlog_csv) if proc is not None else "",
        "big_o_time": "O(N)",
        "big_o_space": "O(1)",
    }

    if proc is not None:
        result.update(parse_powerlog_csv(powerlog_csv))
    if "pkg_power_mean_w" in result:
        result["computed_energy_j"] = float(result["pkg_power_mean_w"]) * runtime_s
    return result


def summarize_results(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate raw rows by parameter set and workload size."""
    grouped: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for row in raw_rows:
        key = (int(row["iterations"]), str(row["config_name"]))
        grouped.setdefault(key, []).append(row)

    numeric_keys = [
        "runtime_s",
        "time_per_iteration_us",
        "throughput_iter_per_s",
        "peak_memory_kb",
        "pkg_power_mean_w",
        "computed_energy_j",
        "real_pkg_energy_j",
    ]

    summaries: List[Dict[str, Any]] = []
    for (iterations, config_name), rows in grouped.items():
        base: Dict[str, Any] = {
            "iterations": iterations,
            "config_name": config_name,
            "a": rows[0]["a"],
            "b": rows[0]["b"],
            "runs": len(rows),
            "big_o_time": "O(N)",
            "big_o_space": "O(1)",
        }
        for key in numeric_keys:
            values = [float(r[key]) for r in rows if key in r and isinstance(r[key], (int, float))]
            if values:
                base[f"{key}_mean"] = statistics.mean(values)
                base[f"{key}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
                base[f"{key}_min"] = min(values)
                base[f"{key}_max"] = max(values)
        summaries.append(base)

    summaries.sort(key=lambda r: (r["iterations"], r["config_name"]))
    return summaries


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    """Write rows to CSV."""
    if not rows:
        return
    fieldnames: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(summary_rows: List[Dict[str, Any]], path: Path) -> None:
    """Write the plain-text performance report."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("Generating Function Algorithm Analysis and Performance Modeling Report\n")
        f.write("=" * 82 + "\n\n")
        f.write("Big-O Analysis\n")
        f.write("- Single Generating Function Calculation: O(1)\n")
        f.write("- Workload of N iterations: O(N)\n")
        f.write("- Memory complexity: O(1)\n\n")
        f.write("Energy estimate: computed_energy_j = pkg_power_mean_w * runtime_s\n\n")
        for row in summary_rows:
            f.write(
                f"iterations={row['iterations']}, config={row['config_name']}, "
                f"runtime_mean={row.get('runtime_s_mean')}, "
                f"throughput_mean={row.get('throughput_iter_per_s_mean')}, "
                f"energy_mean={row.get('computed_energy_j_mean')}, "
                f"memory_mean={row.get('peak_memory_kb_mean')}\n"
            )


def plot_metric_with_errorbars(
    summary_rows: List[Dict[str, Any]],
    mean_key: str,
    std_key: str,
    ylabel: str,
    title: str,
    out_path: Path,
    log_x: bool = True,
) -> None:
    """Generate an error-bar line plot."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in summary_rows:
        if mean_key in row:
            grouped.setdefault(row["config_name"], []).append(row)
    if not grouped:
        return

    plt.figure(figsize=(10, 6))
    for config_name, rows in grouped.items():
        rows = sorted(rows, key=lambda r: r["iterations"])
        x = [r["iterations"] for r in rows]
        y = [r[mean_key] for r in rows]
        yerr = [r.get(std_key, 0.0) for r in rows]
        plt.errorbar(x, y, yerr=yerr, marker="o", capsize=4, label=config_name)

    if log_x:
        plt.xscale("log")
    plt.xlabel("Iterations")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_boxplot_raw(raw_rows: List[Dict[str, Any]], metric_key: str, ylabel: str, title: str, out_path: Path) -> None:
    """Generate a boxplot for raw values."""
    grouped: Dict[str, List[float]] = {}
    for row in raw_rows:
        if metric_key in row and isinstance(row[metric_key], (int, float)):
            label = f"{row['iterations']}\n{row['config_name']}"
            grouped.setdefault(label, []).append(float(row[metric_key]))
    if not grouped:
        return

    labels = list(grouped.keys())
    values = [grouped[label] for label in labels]

    plt.figure(figsize=(15, 7))
    plt.boxplot(values, tick_labels=labels, showmeans=True)
    plt.xlabel("Iterations and parameter set")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_energy_efficiency(summary_rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Generate an iterations-per-joule plot."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in summary_rows:
        if "computed_energy_j_mean" in row and row["computed_energy_j_mean"] > 0:
            grouped.setdefault(row["config_name"], []).append(row)
    if not grouped:
        return

    plt.figure(figsize=(10, 6))
    for config_name, rows in grouped.items():
        rows = sorted(rows, key=lambda r: r["iterations"])
        x = [r["iterations"] for r in rows]
        y = [r["iterations"] / r["computed_energy_j_mean"] for r in rows]
        plt.plot(x, y, marker="o", label=config_name)

    plt.xscale("log")
    plt.xlabel("Iterations")
    plt.ylabel("Iterations per Joule")
    plt.title("Energy Efficiency of the Generating Function")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def generate_figures(raw_rows: List[Dict[str, Any]], summary_rows: List[Dict[str, Any]], figures_dir: Path) -> None:
    """Generate all benchmark figures."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    plot_metric_with_errorbars(summary_rows, "runtime_s_mean", "runtime_s_std", "Runtime (s)", "Runtime Scaling", figures_dir / "runtime_scaling_errorbar.png")
    plot_metric_with_errorbars(summary_rows, "time_per_iteration_us_mean", "time_per_iteration_us_std", "Time per iteration (µs)", "Average Time per Iteration", figures_dir / "time_per_iteration_errorbar.png")
    plot_metric_with_errorbars(summary_rows, "throughput_iter_per_s_mean", "throughput_iter_per_s_std", "Iterations per second", "Throughput Scaling", figures_dir / "throughput_scaling_errorbar.png")
    plot_metric_with_errorbars(summary_rows, "computed_energy_j_mean", "computed_energy_j_std", "Computed energy (J)", "Energy Consumption Scaling", figures_dir / "energy_scaling_errorbar.png")
    plot_metric_with_errorbars(summary_rows, "peak_memory_kb_mean", "peak_memory_kb_std", "Peak memory (KB)", "Peak Memory Usage", figures_dir / "memory_usage_errorbar.png")
    plot_energy_efficiency(summary_rows, figures_dir / "energy_efficiency_iterations_per_joule.png")
    plot_boxplot_raw(raw_rows, "runtime_s", "Runtime (s)", "Runtime Distribution", figures_dir / "boxplot_runtime.png")
    plot_boxplot_raw(raw_rows, "computed_energy_j", "Computed energy (J)", "Energy Distribution", figures_dir / "boxplot_energy.png")


def run_experiment(iterations_list: List[int], runs: int, output_dir: str, use_ipg: bool, sample_ms: int) -> Dict[str, str]:
    """Run the complete experimental workflow."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    x_values = [0.05, 0.10, 0.15, 0.20]
    raw_rows: List[Dict[str, Any]] = []
    for iterations in iterations_list:
        for config_name, a, b in PARAMETER_SETS:
            for run_id in range(1, runs + 1):
                raw_rows.append(
                    run_single_test(iterations, config_name, a, b, run_id, output_root, x_values, use_ipg, sample_ms)
                )

    summary_rows = summarize_results(raw_rows)
    raw_csv = output_root / "raw_results.csv"
    summary_csv = output_root / "summary_results.csv"
    report_txt = output_root / "performance_report.txt"
    figures_dir = output_root / "figures"

    write_csv(raw_rows, raw_csv)
    write_csv(summary_rows, summary_csv)
    write_report(summary_rows, report_txt)
    generate_figures(raw_rows, summary_rows, figures_dir)

    return {
        "output_dir": str(output_root),
        "raw_csv": str(raw_csv),
        "summary_csv": str(summary_csv),
        "report_txt": str(report_txt),
        "figures_dir": str(figures_dir),
        "big_o_time": "O(N)",
        "big_o_space": "O(1)",
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generating function algorithm analysis and performance modeling")
    parser.add_argument("--iterations", type=int, nargs="+", default=[10_000, 100_000, 1_000_000])
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output_dir", type=str, default="generating_function_algorithm_performance_results")
    parser.add_argument("--no-ipg", action="store_true", help="Disable Intel Power Gadget measurement.")
    parser.add_argument("--sample_ms", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    artifacts = run_experiment(
        iterations_list=args.iterations,
        runs=args.runs,
        output_dir=args.output_dir,
        use_ipg=not args.no_ipg,
        sample_ms=args.sample_ms,
    )
    print("Generating Function algorithm analysis and performance modeling completed.")
    for key, value in artifacts.items():
        print(f"{key}: {value}")
