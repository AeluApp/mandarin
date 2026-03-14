import json, os

def append_passages(fname, passages):
    """Append passages to a JSON array file."""
    if os.path.exists(fname) and os.path.getsize(fname) > 2:
        with open(fname) as f:
            existing = json.load(f)
    else:
        existing = []
    existing.extend(passages)
    with open(fname, 'w') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return len(existing)

def write_dialogue(dirname, filename, dialogue):
    """Write a single dialogue file."""
    os.makedirs(dirname, exist_ok=True)
    fpath = os.path.join(dirname, filename)
    with open(fpath, 'w') as f:
        json.dump(dialogue, f, ensure_ascii=False, indent=4)
    return fpath
