# SPC Automation Script Specification — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Related:** `control-charts.md` (chart specs), `process-capability.md` (Cp/Cpk)

---

## 1. Purpose

Automated generation of SPC control charts from Aelu's SQLite database, with rule violation detection and alerting. Runs as a scheduled job (daily or on-demand via `./run spc`).

---

## 2. Architecture

```
SQLite (mandarin.db)
    ↓ queries
spc_monitor.py
    ↓ computes control limits, checks rules
    ├── generates PNG charts (matplotlib)
    ├── logs violations to improvement_log table
    └── writes summary to data/spc_report.json
```

---

## 3. Python Implementation

### 3.1 Core SPC Engine

```python
#!/usr/bin/env python3
"""spc_monitor.py — Automated SPC monitoring for Aelu Mandarin."""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "mandarin.db"
CHART_DIR = Path(__file__).parent.parent / "data" / "spc_charts"
REPORT_PATH = Path(__file__).parent.parent / "data" / "spc_report.json"


@dataclass
class ControlLimits:
    """Control limits for a single chart."""
    cl: float          # Center line
    ucl: float         # Upper control limit (CL + 3σ)
    lcl: float         # Lower control limit (CL - 3σ)
    sigma_1: float     # 1σ distance from center
    sigma_2: float     # 2σ distance from center


@dataclass
class Violation:
    """A detected out-of-control condition."""
    rule: int          # Western Electric rule number (1-8)
    rule_name: str
    chart_name: str
    point_index: int   # Which data point triggered the rule
    point_value: float
    severity: str      # 'critical', 'warning', 'info'
    detail: str


def compute_control_limits(values: list[float]) -> ControlLimits:
    """Compute 3-sigma control limits from a list of values."""
    if len(values) < 2:
        raise ValueError("Need at least 2 data points for control limits")

    mean = np.mean(values)
    std = np.std(values, ddof=1)  # Sample standard deviation

    # Prevent zero-width limits
    if std < 1e-10:
        std = 1e-10

    return ControlLimits(
        cl=float(mean),
        ucl=float(mean + 3 * std),
        lcl=float(mean - 3 * std),
        sigma_1=float(std),
        sigma_2=float(2 * std),
    )


def compute_xbar_r_limits(
    subgroup_means: list[float],
    subgroup_ranges: list[float],
    n: int,
) -> tuple[ControlLimits, ControlLimits]:
    """Compute X-bar and R chart limits using standard constants."""
    # A2, D3, D4 constants for subgroup sizes 2-25
    A2_TABLE = {
        2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
        7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308, 15: 0.223,
        20: 0.180, 25: 0.153,
    }
    D3_TABLE = {
        2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0.076, 8: 0.136,
        9: 0.184, 10: 0.223, 15: 0.348, 20: 0.414, 25: 0.459,
    }
    D4_TABLE = {
        2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 1.924,
        7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777, 15: 1.652,
        20: 1.586, 25: 1.541,
    }

    # Use closest available n
    available_n = sorted(A2_TABLE.keys())
    closest_n = min(available_n, key=lambda x: abs(x - n))

    A2 = A2_TABLE[closest_n]
    D3 = D3_TABLE[closest_n]
    D4 = D4_TABLE[closest_n]

    x_double_bar = np.mean(subgroup_means)
    r_bar = np.mean(subgroup_ranges)

    xbar_limits = ControlLimits(
        cl=float(x_double_bar),
        ucl=float(x_double_bar + A2 * r_bar),
        lcl=float(x_double_bar - A2 * r_bar),
        sigma_1=float(A2 * r_bar / 3),
        sigma_2=float(A2 * r_bar * 2 / 3),
    )

    r_limits = ControlLimits(
        cl=float(r_bar),
        ucl=float(D4 * r_bar),
        lcl=float(D3 * r_bar),
        sigma_1=float((D4 - D3) * r_bar / 6),
        sigma_2=float((D4 - D3) * r_bar / 3),
    )

    return xbar_limits, r_limits
```

### 3.2 Western Electric Rule Detection

```python
def check_western_electric_rules(
    values: list[float],
    limits: ControlLimits,
    chart_name: str,
) -> list[Violation]:
    """Check all 8 Western Electric rules against a data series."""
    violations = []
    n = len(values)
    cl, ucl, lcl = limits.cl, limits.ucl, limits.lcl
    s1 = limits.sigma_1
    s2 = limits.sigma_2

    for i, v in enumerate(values):

        # Rule 1: Point beyond 3σ
        if v > ucl or v < lcl:
            violations.append(Violation(
                rule=1, rule_name="Beyond 3σ", chart_name=chart_name,
                point_index=i, point_value=v, severity="critical",
                detail=f"Value {v:.2f} exceeds limits [{lcl:.2f}, {ucl:.2f}]",
            ))

        # Rule 2: 9 consecutive points same side of center
        if i >= 8:
            window = values[i-8:i+1]
            if all(x > cl for x in window) or all(x < cl for x in window):
                violations.append(Violation(
                    rule=2, rule_name="9-point shift", chart_name=chart_name,
                    point_index=i, point_value=v, severity="warning",
                    detail=f"9 consecutive points on same side of CL ({cl:.2f})",
                ))

        # Rule 3: 6 consecutive points trending (all increasing or all decreasing)
        if i >= 5:
            window = values[i-5:i+1]
            diffs = [window[j+1] - window[j] for j in range(5)]
            if all(d > 0 for d in diffs):
                violations.append(Violation(
                    rule=3, rule_name="6-point trend up", chart_name=chart_name,
                    point_index=i, point_value=v, severity="warning",
                    detail="6 consecutive increasing points",
                ))
            elif all(d < 0 for d in diffs):
                violations.append(Violation(
                    rule=3, rule_name="6-point trend down", chart_name=chart_name,
                    point_index=i, point_value=v, severity="warning",
                    detail="6 consecutive decreasing points",
                ))

        # Rule 4: 14 consecutive alternating points
        if i >= 13:
            window = values[i-13:i+1]
            diffs = [window[j+1] - window[j] for j in range(13)]
            alternating = all(
                diffs[j] * diffs[j+1] < 0 for j in range(12)
            )
            if alternating:
                violations.append(Violation(
                    rule=4, rule_name="14-point alternation", chart_name=chart_name,
                    point_index=i, point_value=v, severity="info",
                    detail="14 consecutive alternating points",
                ))

        # Rule 5: 2 of 3 consecutive points beyond 2σ (same side)
        if i >= 2:
            window = values[i-2:i+1]
            above_2s = sum(1 for x in window if x > cl + s2)
            below_2s = sum(1 for x in window if x < cl - s2)
            if above_2s >= 2 or below_2s >= 2:
                violations.append(Violation(
                    rule=5, rule_name="2-of-3 beyond 2σ", chart_name=chart_name,
                    point_index=i, point_value=v, severity="warning",
                    detail=f"2 of 3 points beyond 2σ from center",
                ))

        # Rule 6: 4 of 5 consecutive points beyond 1σ (same side)
        if i >= 4:
            window = values[i-4:i+1]
            above_1s = sum(1 for x in window if x > cl + s1)
            below_1s = sum(1 for x in window if x < cl - s1)
            if above_1s >= 4 or below_1s >= 4:
                violations.append(Violation(
                    rule=6, rule_name="4-of-5 beyond 1σ", chart_name=chart_name,
                    point_index=i, point_value=v, severity="info",
                    detail=f"4 of 5 points beyond 1σ from center",
                ))

        # Rule 7: 15 consecutive points within 1σ (stratification)
        if i >= 14:
            window = values[i-14:i+1]
            if all(abs(x - cl) < s1 for x in window):
                violations.append(Violation(
                    rule=7, rule_name="15-point stratification",
                    chart_name=chart_name,
                    point_index=i, point_value=v, severity="info",
                    detail="15 points within 1σ — possible data grouping",
                ))

        # Rule 8: 8 consecutive points beyond 1σ (either side, mixture)
        if i >= 7:
            window = values[i-7:i+1]
            if all(abs(x - cl) > s1 for x in window):
                violations.append(Violation(
                    rule=8, rule_name="8-point mixture", chart_name=chart_name,
                    point_index=i, point_value=v, severity="info",
                    detail="8 points beyond 1σ on either side — possible mixture",
                ))

    return violations
```

### 3.3 Chart Generation

```python
def plot_control_chart(
    dates: list[str],
    values: list[float],
    limits: ControlLimits,
    chart_name: str,
    ylabel: str,
    violations: list[Violation],
    usl: Optional[float] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a control chart PNG with zones and violation markers."""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = CHART_DIR / f"{chart_name}_{datetime.now():%Y%m%d}.png"

    fig, ax = plt.subplots(figsize=(14, 6))

    x = range(len(values))

    # Zone shading (A/B/C zones)
    cl, s1, s2 = limits.cl, limits.sigma_1, limits.sigma_2
    ax.axhspan(cl - s1, cl + s1, alpha=0.1, color='green', label='Zone C (±1σ)')
    ax.axhspan(cl + s1, cl + s2, alpha=0.1, color='yellow')
    ax.axhspan(cl - s2, cl - s1, alpha=0.1, color='yellow', label='Zone B (±2σ)')
    ax.axhspan(cl + s2, limits.ucl, alpha=0.1, color='red')
    ax.axhspan(limits.lcl, cl - s2, alpha=0.1, color='red', label='Zone A (±3σ)')

    # Control lines
    ax.axhline(y=limits.cl, color='green', linewidth=1.5, linestyle='-', label=f'CL = {cl:.1f}')
    ax.axhline(y=limits.ucl, color='red', linewidth=1, linestyle='--', label=f'UCL = {limits.ucl:.1f}')
    ax.axhline(y=limits.lcl, color='red', linewidth=1, linestyle='--', label=f'LCL = {limits.lcl:.1f}')

    # USL (specification limit, distinct from control limit)
    if usl is not None:
        ax.axhline(y=usl, color='darkred', linewidth=2, linestyle=':', label=f'USL = {usl}')

    # Data points
    ax.plot(x, values, 'b-o', markersize=4, linewidth=1, label='Data')

    # Mark violations
    violation_indices = {v.point_index for v in violations if v.severity == 'critical'}
    warning_indices = {v.point_index for v in violations if v.severity == 'warning'}

    for idx in violation_indices:
        if 0 <= idx < len(values):
            ax.plot(idx, values[idx], 'rv', markersize=12)  # Red triangle
    for idx in warning_indices:
        if 0 <= idx < len(values):
            ax.plot(idx, values[idx], 'y^', markersize=10)  # Yellow triangle

    # Labels
    ax.set_title(f'Control Chart: {chart_name}', fontsize=14, fontweight='bold')
    ax.set_ylabel(ylabel)
    ax.set_xlabel('Subgroup')

    # X-axis labels (dates, if available)
    if dates and len(dates) == len(values):
        step = max(1, len(dates) // 15)  # Show ~15 labels max
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                          rotation=45, ha='right', fontsize=8)

    ax.legend(loc='upper right', fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    logger.info(f"Chart saved: {output_path}")
    return output_path
```

### 3.4 Data Queries and Chart Orchestration

```python
def fetch_api_latency_data(db_path: Path, days: int = 30) -> tuple[list[str], list[float]]:
    """Fetch hourly API latency subgroup means."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            strftime('%Y-%m-%d %H:00', created_at) AS hour_bucket,
            AVG(CAST(detail AS REAL)) AS x_bar
        FROM client_event
        WHERE category = 'performance'
          AND event = 'api_response_time'
          AND created_at >= datetime('now', ?)
        GROUP BY hour_bucket
        HAVING COUNT(*) >= 3
        ORDER BY hour_bucket
    """, (f'-{days} days',)).fetchall()
    conn.close()

    dates = [r['hour_bucket'] for r in rows]
    values = [r['x_bar'] for r in rows]
    return dates, values


def fetch_session_accuracy_data(db_path: Path, days: int = 30) -> tuple[list[str], list[float]]:
    """Fetch per-session drill accuracy proportions."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            DATE(started_at) AS day,
            ROUND(CAST(items_correct AS REAL) / NULLIF(items_completed, 0), 3) AS accuracy
        FROM session_log
        WHERE items_completed > 0
          AND session_outcome != 'started'
          AND started_at >= datetime('now', ?)
        ORDER BY started_at
    """, (f'-{days} days',)).fetchall()
    conn.close()

    dates = [r['day'] for r in rows]
    values = [r['accuracy'] for r in rows if r['accuracy'] is not None]
    return dates[:len(values)], values


def fetch_daily_sessions(db_path: Path, days: int = 60) -> tuple[list[str], list[float]]:
    """Fetch daily completed session counts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            DATE(started_at) AS day,
            COUNT(*) AS sessions
        FROM session_log
        WHERE session_outcome != 'started'
          AND started_at >= datetime('now', ?)
        GROUP BY day
        ORDER BY day
    """, (f'-{days} days',)).fetchall()
    conn.close()

    dates = [r['day'] for r in rows]
    values = [float(r['sessions']) for r in rows]
    return dates, values
```

### 3.5 Alert and Logging

```python
def log_violations(db_path: Path, violations: list[Violation]) -> int:
    """Log violations to improvement_log table. Returns count logged."""
    if not violations:
        return 0

    conn = sqlite3.connect(str(db_path))
    logged = 0
    for v in violations:
        if v.severity in ('critical', 'warning'):
            conn.execute("""
                INSERT INTO improvement_log
                    (trigger_reason, observation, proposed_change, status)
                VALUES (?, ?, ?, 'proposed')
            """, (
                f"SPC Rule {v.rule} violation on {v.chart_name}",
                f"{v.rule_name}: {v.detail} (value={v.point_value:.2f}, "
                f"index={v.point_index}, severity={v.severity})",
                f"Investigate {v.chart_name} — see control-charts.md reaction plan "
                f"for Rule {v.rule}",
            ))
            logged += 1
            logger.warning(
                f"SPC VIOLATION: Rule {v.rule} ({v.rule_name}) on "
                f"{v.chart_name}: {v.detail}"
            )
    conn.commit()
    conn.close()
    return logged
```

### 3.6 Main Runner

```python
def run_spc_monitoring(db_path: Optional[Path] = None, days: int = 30) -> dict:
    """Run full SPC monitoring suite. Returns summary report."""
    if db_path is None:
        db_path = DB_PATH

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "charts": [],
        "violations": [],
        "total_violations": 0,
    }

    # Chart 1: API Latency
    dates, values = fetch_api_latency_data(db_path, days)
    if len(values) >= 10:
        limits = compute_control_limits(values)
        violations = check_western_electric_rules(values, limits, "api_latency")
        chart_path = plot_control_chart(
            dates, values, limits, "api_latency",
            "Response Time (ms)", violations, usl=500,
        )
        log_violations(db_path, violations)
        report["charts"].append({
            "name": "api_latency",
            "data_points": len(values),
            "cl": limits.cl,
            "ucl": limits.ucl,
            "violations": len(violations),
            "chart_file": str(chart_path),
        })
        report["violations"].extend([
            {"rule": v.rule, "chart": v.chart_name, "detail": v.detail}
            for v in violations
        ])

    # Chart 2: Session Accuracy
    dates, values = fetch_session_accuracy_data(db_path, days)
    if len(values) >= 10:
        limits = compute_control_limits(values)
        violations = check_western_electric_rules(values, limits, "session_accuracy")
        chart_path = plot_control_chart(
            dates, values, limits, "session_accuracy",
            "Accuracy (proportion correct)", violations,
        )
        log_violations(db_path, violations)
        report["charts"].append({
            "name": "session_accuracy",
            "data_points": len(values),
            "cl": limits.cl,
            "ucl": limits.ucl,
            "violations": len(violations),
            "chart_file": str(chart_path),
        })
        report["violations"].extend([
            {"rule": v.rule, "chart": v.chart_name, "detail": v.detail}
            for v in violations
        ])

    # Chart 3: Daily Sessions
    dates, values = fetch_daily_sessions(db_path, days=60)
    if len(values) >= 10:
        limits = compute_control_limits(values)
        violations = check_western_electric_rules(values, limits, "daily_sessions")
        chart_path = plot_control_chart(
            dates, values, limits, "daily_sessions",
            "Completed Sessions", violations,
        )
        log_violations(db_path, violations)
        report["charts"].append({
            "name": "daily_sessions",
            "data_points": len(values),
            "cl": limits.cl,
            "ucl": limits.ucl,
            "violations": len(violations),
            "chart_file": str(chart_path),
        })
        report["violations"].extend([
            {"rule": v.rule, "chart": v.chart_name, "detail": v.detail}
            for v in violations
        ])

    report["total_violations"] = sum(c.get("violations", 0) for c in report["charts"])

    # Write report
    with open(REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(
        f"SPC monitoring complete: {len(report['charts'])} charts, "
        f"{report['total_violations']} violations"
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_spc_monitoring()
    print(json.dumps(report, indent=2))
```

---

## 4. CLI Integration

Add to `./run` launcher:

```python
# In cli.py or run script
@app.command()
def spc():
    """Run SPC monitoring and generate control charts."""
    from mandarin.spc_monitor import run_spc_monitoring
    report = run_spc_monitoring()
    print(f"Charts generated: {len(report['charts'])}")
    print(f"Violations detected: {report['total_violations']}")
    for v in report['violations']:
        print(f"  Rule {v['rule']} on {v['chart']}: {v['detail']}")
```

---

## 5. Scheduled Execution

Run daily via cron (or Fly.io scheduled machine):

```
# crontab entry
0 6 * * * cd /app && python -m mandarin.spc_monitor 2>> /app/data/spc.log
```

---

## 6. Alert Escalation

| Violation Severity | Action |
|-------------------|--------|
| `critical` (Rule 1) | Log to `improvement_log` + print to console + write to `data/spc_alerts.log` |
| `warning` (Rules 2, 3, 5, 6) | Log to `improvement_log` + write to `data/spc_alerts.log` |
| `info` (Rules 4, 7, 8) | Write to `data/spc_alerts.log` only (no improvement_log entry) |

Future enhancement: email notification via Resend for critical violations when in production with active users.

---

## 7. Testing

```python
# test_spc_monitor.py
def test_rule_1_detection():
    """Points beyond 3σ should trigger Rule 1."""
    values = [10, 11, 9, 10, 11, 10, 9, 10, 50]  # Last point is outlier
    limits = compute_control_limits(values[:8])  # Limits from stable data
    violations = check_western_electric_rules(values, limits, "test")
    assert any(v.rule == 1 for v in violations)

def test_rule_2_detection():
    """9 consecutive points above center should trigger Rule 2."""
    values = [10, 11, 12, 11, 10, 11, 12, 11, 12, 11]  # All above mean of ~5
    # Construct data where last 9 points are all above center
    base = [5, 4, 5, 6, 5, 4, 5, 6, 5]
    shifted = [12, 11, 12, 13, 12, 11, 12, 13, 12]
    all_values = base + shifted
    limits = compute_control_limits(all_values)
    violations = check_western_electric_rules(all_values, limits, "test")
    assert any(v.rule == 2 for v in violations)

def test_rule_3_detection():
    """6 consecutive increasing points should trigger Rule 3."""
    values = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15, 16]
    limits = compute_control_limits(values)
    violations = check_western_electric_rules(values, limits, "test")
    assert any(v.rule == 3 for v in violations)

def test_no_violations_stable_process():
    """A stable process should have no violations."""
    np.random.seed(42)
    values = list(np.random.normal(100, 5, 50))
    limits = compute_control_limits(values)
    violations = check_western_electric_rules(values, limits, "test")
    critical = [v for v in violations if v.severity == 'critical']
    # May have occasional Rule 1 due to randomness, but should be rare
    assert len(critical) <= 1
```
