#!/usr/bin/env python3
import json
import os
import time

# Read the spinner.rs file
with open('spinner.rs', 'r') as f:
    spinner_data = json.load(f)

# Read the existing spinners.json to get the structure
with open('spinners.json', 'r') as f:
    spinners_json = json.load(f)

# Clear existing spinner entries (keep loadingMessages)
spinners_json['spinners'] = []

# Create text files for each spinner
for i, spinner in enumerate(spinner_data):
    # Generate a unique filename using timestamp and index
    filename = f"{int(time.time() * 1000)}_{i}.txt"
    
    # Write frames to text file
    with open(filename, 'w') as f:
        for frame in spinner['frames']:
            f.write(frame + '\n')
    
    # Add entry to spinners.json
    spinners_json['spinners'].append({
        'filename': filename,
        'interval': spinner['interval']
    })
    
    # Small delay to ensure unique timestamps
    time.sleep(0.001)

# Write updated spinners.json
with open('spinners.json', 'w') as f:
    json.dump(spinners_json, f, indent=4)

print(f"Converted {len(spinner_data)} spinners")
print("Updated spinners.json with new entries")