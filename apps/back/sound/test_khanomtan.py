import torch
import json
import numpy as np
import soundfile as sf
import os

print("=" * 60)
print("KhanomTan TTS - Test Script")
print("=" * 60)

# Model directory
model_dir = "khanomtan/"

# Load config
with open(model_dir + "config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

print("\n✓ Config loaded")
print(f"  - Sample rate: {config['audio']['sample_rate']}")
print(f"  - FFT size: {config['audio']['fft_size']}")
print(f"  - Number of speakers: {config['model_args']['num_speakers']}")

# Load language IDs
with open(model_dir + "language_ids.json", "r", encoding="utf-8") as f:
    language_ids = json.load(f)

print(f"\n✓ Language IDs loaded: {list(language_ids.keys())}")

# Load speakers
speakers_file = torch.load(model_dir + "speakers.pth")
print(f"✓ Speakers loaded: {len(speakers_file)} speakers")

# Try to load the model
try:
    print(f"\nLoading model from: {model_dir}best_model.pth")
    state_dict = torch.load(model_dir + "best_model.pth", map_location="cpu")
    
    if isinstance(state_dict, dict):
        print(f"✓ Model loaded successfully!")
        print(f"  - Model state dict keys: {list(state_dict.keys())[:5]}...")
        print(f"  - Total parameters: {sum(p.numel() for p in state_dict.values() if isinstance(p, torch.Tensor)):,}")
    else:
        print(f"✓ Model loaded (object type: {type(state_dict).__name__})")
        
except Exception as e:
    print(f"✗ Error loading model: {e}")

print("\n" + "=" * 60)
print("Note: Full inference requires TTS library which is")
print("not compatible with Python 3.12+. Please use Python 3.10/3.11")
print("or adapt the code to use the model directly with PyTorch.")
print("=" * 60)
