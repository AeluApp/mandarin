# Cumulative Flow Diagram (CFD)

> Last updated: 2026-03-10

## What Is a CFD?

A stacked area chart showing the cumulative count of items in each workflow state over time. The horizontal distance between bands represents lead time. The vertical distance represents WIP.

**X-axis:** Time (weeks)
**Y-axis:** Cumulative item count
**Stacked areas (bottom to top):** Done, Review, In Progress, Ready, Backlog

---

## How to Read a CFD

The shape of the bands tells you everything about flow health:

### 1. Healthy Flow (Target State)
```
        ╱‾‾‾‾‾‾‾  Backlog
       ╱ ‾‾‾‾‾‾   Ready
      ╱  ‾‾‾‾‾    In Progress
     ╱   ‾‾‾‾     Review
    ╱    ‾‾‾       Done
───╱─────────────── time →
```
**Pattern:** All bands roughly parallel, with consistent vertical thickness. The Done band grows steadily.
**Meaning:** Items flow through the system at a predictable rate. WIP is stable. Lead time is constant.
**What to do:** Nothing. This is the goal.

### 2. Bottleneck at Review
```
        ╱‾‾‾‾‾‾‾  Backlog
       ╱ ‾‾‾‾‾‾   Ready
      ╱  ‾‾‾‾‾    In Progress
     ╱ ══════════  Review (widening)
    ╱    ‾‾‾       Done (flattening)
───╱─────────────── time →
```
**Pattern:** Review band widens while Done band flattens or grows slowly.
**Meaning:** Items finish development but aren't getting deployed. For a solo founder, this usually means: testing/deploy friction, procrastinating on final verification, or unclear "done" criteria.
**What to do:** Stop starting new work. Clear the Review queue. Automate deploy if friction is the cause.

### 3. Starvation (Ready Queue Empty)
```
        ╱‾‾‾‾‾‾‾  Backlog
       ╱           Ready (narrowing to zero)
      ╱            In Progress (narrowing)
     ╱   ‾‾‾‾     Review
    ╱    ‾‾‾       Done
───╱─────────────── time →
```
**Pattern:** Ready band narrows and disappears. In Progress follows.
**Meaning:** Nothing is being pulled from Backlog into Ready. The pipeline is drying up. Either: backlog grooming isn't happening, or there genuinely isn't more work to do (unlikely for a pre-PMF product).
**What to do:** Hold a replenishment session. Review the backlog. If the backlog is empty, do strategy review — is the product direction clear?

### 4. Scope Creep
```
        ╱‾‾‾‾‾‾‾‾‾‾‾‾  Backlog (accelerating growth)
       ╱ ‾‾‾‾‾‾‾‾‾      Ready (growing)
      ╱  ‾‾‾‾‾           In Progress
     ╱   ‾‾‾‾            Review
    ╱    ‾‾‾              Done (growing, but slower than Backlog)
───╱─────────────────────── time →
```
**Pattern:** Top bands (Backlog, Ready) grow faster than bottom bands (Done). The gap between total items and completed items widens.
**Meaning:** You are adding work faster than you are finishing it. WIP will eventually grow. Lead time will increase.
**What to do:** Stop adding to Backlog. Focus on finishing what's in flight. At next strategy review, decide whether to prune the backlog aggressively.

---

## CFD Generation Script

Save as `scripts/generate_cfd.py` and run from project root.

```python
#!/usr/bin/env python3
"""
Generate a Cumulative Flow Diagram from flow metrics data.

Usage:
    python scripts/generate_cfd.py [--output cfd.png]

Input: reads from docs/kanban/flow-data.csv
Format: date,backlog,ready,in_progress,review,done
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime
except ImportError:
    print("Requires matplotlib: pip install matplotlib")
    sys.exit(1)


def load_data(csv_path: str) -> dict:
    """Load flow data from CSV."""
    dates = []
    columns = {"backlog": [], "ready": [], "in_progress": [], "review": [], "done": []}

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.append(datetime.strptime(row["date"], "%Y-%m-%d"))
            for col in columns:
                columns[col].append(int(row[col]))

    return {"dates": dates, **columns}


def generate_cfd(data: dict, output_path: str):
    """Generate stacked area chart."""
    fig, ax = plt.subplots(figsize=(12, 6))

    # Stack order: Done (bottom) → Review → In Progress → Ready → Backlog (top)
    # This way the Done area grows from the bottom, which is intuitive.
    labels = ["Done", "Review", "In Progress", "Ready", "Backlog"]
    colors = ["#4a9e8e", "#d4a373", "#e07a5f", "#81b29a", "#b8c4bb"]
    values = [data["done"], data["review"], data["in_progress"],
              data["ready"], data["backlog"]]

    ax.stackplot(data["dates"], *values, labels=labels, colors=colors, alpha=0.85)

    # Formatting
    ax.set_title("Aelu — Cumulative Flow Diagram", fontsize=14, fontweight="bold")
    ax.set_xlabel("Week", fontsize=11)
    ax.set_ylabel("Cumulative Items", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    plt.xticks(rotation=45)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    plt.savefig(output_path, dpi=150)
    print(f"CFD saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Cumulative Flow Diagram")
    parser.add_argument("--output", default="reports/cfd.png", help="Output image path")
    parser.add_argument("--data", default="docs/kanban/flow-data.csv", help="Input CSV")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"No data file at {data_path}. Create it with this format:")
        print("date,backlog,ready,in_progress,review,done")
        print("2026-02-24,8,3,3,1,0")
        print("2026-03-03,6,3,3,1,5")
        print("2026-03-10,5,3,3,1,6")
        sys.exit(1)

    data = load_data(str(data_path))
    generate_cfd(data, args.output)


if __name__ == "__main__":
    main()
```

---

## Sample Data File

Create `docs/kanban/flow-data.csv`:

```csv
date,backlog,ready,in_progress,review,done
2026-02-17,12,2,3,0,0
2026-02-24,8,3,3,1,2
2026-03-03,6,3,3,1,5
2026-03-10,5,3,3,1,6
```

---

## Weekly Update Process

Every Monday during replenishment:

1. Count items in each column.
2. Add a row to `flow-data.csv`.
3. Run `python scripts/generate_cfd.py`.
4. Review the chart:
   - Are bands parallel? Good.
   - Is any band widening? Investigate.
   - Is Done growing steadily? Good.
   - Is Backlog growing faster than Done? Stop adding work.

---

## Key Measurements from the CFD

| Measurement | How to Read It |
|-------------|---------------|
| **Lead Time** | Horizontal distance between when an item enters (top of chart moves up) and when it exits (Done band moves up). |
| **WIP** | Vertical distance between the Done band and the top of the chart at any point in time. |
| **Throughput** | Slope of the Done band. Steeper = faster delivery. |
| **Demand Rate** | Slope of the top line (total items). If steeper than Done slope, you're adding work faster than finishing it. |
