# -*- coding: utf-8 -*-
import json
import re
import sys

filepath = sys.argv[1]

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace smart/curly double quotes with Chinese corner brackets
# But only inside JSON string values, not the JSON structural quotes
# Strategy: replace \u201c and \u201d with corner brackets
content = content.replace('\u201c', '\u300c').replace('\u201d', '\u300d')

# Also need to handle the case where regular ASCII " is used as Chinese quotation
# inside strings. We need to escape those.
# Actually, the problem is that inside JSON strings, bare " chars break parsing.
# Let's try a different approach: read line by line and fix

# Better approach: find all lines and escape inner quotes
lines = content.split('\n')
fixed_lines = []
for line in lines:
    fixed_lines.append(line)

content = '\n'.join(fixed_lines)

# Try parsing
try:
    data = json.loads(content)
    print(f"Valid JSON after smart quote fix: {len(data)} passages")
    # Re-dump cleanly
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("File rewritten successfully")
except json.JSONDecodeError as e:
    print(f"Still invalid: {e}")
    # Need more aggressive fixing
    # Find the problematic areas - look for unescaped quotes inside strings
    print("Attempting aggressive fix...")

    # The issue is ASCII " used as Chinese quotation marks inside JSON string values
    # We need to find these and replace with corner brackets
    # Pattern: within a JSON string value, any " that's not at the boundary

    # Simple approach: replace sequences like 比作"xxx" with 比作「xxx」
    # This is a Chinese text pattern where " " are used as quotation marks

    # Find all Chinese text followed by "..." pattern
    # Replace ASCII double quotes that appear between Chinese characters
    import re

    # Match: Chinese char + " + non-quote-chars + " + Chinese char
    # This catches Chinese quotation usage of ASCII quotes
    def fix_chinese_quotes(text):
        # Pattern: after a Chinese character or punctuation, " followed by content and closing "
        result = []
        i = 0
        in_json_string = False
        json_string_start = -1

        while i < len(text):
            c = text[i]
            if c == '"' and (i == 0 or text[i-1] != '\\'):
                if not in_json_string:
                    in_json_string = True
                    json_string_start = i
                    result.append(c)
                else:
                    # This could be end of JSON string or an inner quote
                    # Check what follows: if it's : , ] } or whitespace before those, it's JSON structural
                    rest = text[i+1:].lstrip()
                    if rest and rest[0] in ':,]}':
                        # End of JSON string
                        in_json_string = False
                        result.append(c)
                    else:
                        # Inner quote - replace with corner bracket
                        # But we need to figure out if it's opening or closing
                        # Look at what's before: if Chinese char, it might be opening
                        if result and ord(result[-1]) > 127:
                            result.append('\u300c')  # opening corner bracket
                        else:
                            result.append('\u300d')  # closing corner bracket

            else:
                result.append(c)
            i += 1
        return ''.join(result)

    fixed = fix_chinese_quotes(content)
    try:
        data = json.loads(fixed)
        print(f"Fixed! Valid JSON: {len(data)} passages")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("File rewritten successfully")
    except json.JSONDecodeError as e2:
        print(f"Still broken: {e2}")
        print("Manual fix needed")
