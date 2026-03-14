# -*- coding: utf-8 -*-
"""Add passages to batch files. Run with: python3 add_passages.py"""
import json
import sys

def load_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_file(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Verify
    with open(path, 'r', encoding='utf-8') as f:
        verified = json.load(f)
    print(f"Saved {path}: {len(verified)} passages, all valid")
    for p in verified:
        print(f"  {p['id']}: {len(p['questions'])} questions")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 add_passages.py <command>")
        sys.exit(1)
    cmd = sys.argv[1]
    print(f"Running command: {cmd}")
