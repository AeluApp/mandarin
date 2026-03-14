#!/usr/bin/env python3
"""Merge all batch files into passage files and report status."""
import json, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def smart_merge_all():
    import glob
    for level in range(1, 10):
        target = f'passages_hsk{level}.json'
        # Find all batch files for this level (multiple naming patterns)
        batch_files = sorted(set(
            glob.glob(f'hsk{level}_batch*.json') +
            glob.glob(f'hsk{level}_b*.json')
        ))
        for fname in batch_files:
            if '_part' in fname and not fname.endswith('.json'): continue
            try:
                with open(fname) as f:
                    data = json.load(f)
                if os.path.exists(target) and os.path.getsize(target) > 2:
                    with open(target) as f:
                        existing = json.load(f)
                    existing_ids = {p['id'] for p in existing}
                    new_data = [p for p in data if p['id'] not in existing_ids]
                    if new_data:
                        existing.extend(new_data)
                        with open(target, 'w') as f:
                            json.dump(existing, f, ensure_ascii=False, indent=2)
                        print(f'  {fname}: +{len(new_data)} → HSK{level}: {len(existing)}')
                else:
                    with open(target, 'w') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f'  {fname}: +{len(data)} → HSK{level}: {len(data)}')
            except Exception as e:
                print(f'  {fname} ERROR: {e}')

print("=== MERGING ===")
smart_merge_all()

print("\n=== PASSAGE TOTALS ===")
targets = {1:125, 2:125, 3:120, 4:120, 5:139, 6:120, 7:120, 8:120, 9:120}
grand = 0
for level in range(1, 10):
    target = f'passages_hsk{level}.json'
    count = 0
    if os.path.exists(target) and os.path.getsize(target) > 2:
        with open(target) as f:
            count = len(json.load(f))
    grand += count
    status = "DONE" if count >= targets[level] else f"{count}/{targets[level]}"
    print(f'  HSK {level}: {status}')
print(f'  Total: {grand}/1009')

print("\n=== DIALOGUE TOTALS ===")
dlg_dir = 'dialogues'
targets_dlg = {1:34, 2:44, 3:55, 4:51, 5:47, 6:33, 7:10, 8:10, 9:10}
dlg_total = 0
if os.path.exists(dlg_dir):
    files = [f for f in os.listdir(dlg_dir) if f.endswith('.json')]
    by_level = {}
    for f in files:
        level = int(f.split('_')[0][1:])
        by_level[level] = by_level.get(level, 0) + 1
    for k in sorted(targets_dlg.keys()):
        count = by_level.get(k, 0)
        dlg_total += count
        status = "DONE" if count >= targets_dlg[k] else f"{count}/{targets_dlg[k]}"
        print(f'  HSK {k}: {status}')
print(f'  Total: {dlg_total}/294')
