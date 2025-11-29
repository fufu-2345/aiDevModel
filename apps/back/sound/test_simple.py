import torch
import json
import numpy as np
import soundfile as sf

# Load config and model
model_dir = "khanomtan/"

with open(model_dir + "config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

print(f"Config loaded. Sample rate: {config['audio']['sample_rate']}")
print(f"Model args: {config['model_args']['num_speakers']} speakers")

# Check available model files
import os
print(f"\nAvailable model files in {model_dir}:")
for f in os.listdir(model_dir):
    if f.endswith('.pth'):
        file_size = os.path.getsize(os.path.join(model_dir, f)) / (1024**2)  # Convert to MB
        print(f"  - {f} ({file_size:.2f} MB)")
