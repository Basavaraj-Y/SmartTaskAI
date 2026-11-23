import json
from functools import lru_cache

import torch
from django.conf import settings

from core.ml_models import (
    MAX_TOKENS,
    CompletionMLP,
    DelayFeedForward,
    PriorityBiLSTM,
    encode_text,
    encode_task_type,
)


def _checkpoint(name):
    path = settings.MODEL_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"Model artifact {path.name} is missing. Run "
            "`python deep_learning/train_models.py` from the repository root."
        )
    return torch.load(path, map_location="cpu", weights_only=True)


@lru_cache(maxsize=1)
def priority_model():
    vocab_path = settings.MODEL_DIR / "priority_vocab.json"
    if not vocab_path.is_file():
        raise FileNotFoundError("Priority model vocabulary is missing; train the models first.")
    vocabulary = json.loads(vocab_path.read_text(encoding="utf-8"))
    checkpoint = _checkpoint("priority_bilstm.pt")
    model = PriorityBiLSTM(len(vocabulary))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model, vocabulary, checkpoint.get("training_data", "unknown")


@lru_cache(maxsize=1)
def completion_model():
    checkpoint = _checkpoint("completion_mlp.pt")
    model = CompletionMLP()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


@lru_cache(maxsize=1)
def delay_model():
    checkpoint = _checkpoint("delay_ffn.pt")
    model = DelayFeedForward()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


def predict_priority(description, task_type):
    model, vocabulary, training_data = priority_model()
    tokens, length = encode_text(description, vocabulary)
    features = torch.tensor([encode_task_type(task_type)], dtype=torch.float32)
    with torch.inference_mode():
        probabilities = model(torch.tensor([tokens]), features).softmax(dim=1)[0]
    index = int(probabilities.argmax())
    return {
        "priority": ["low", "medium", "high", "critical"][index],
        "score": round(float(probabilities[index]), 4),
        "token_count": length,
        "model": "BiLSTM",
        "training_data": training_data,
    }


def predict_completion(complexity, effort_points, team_size, dependencies):
    model = completion_model()
    features = torch.tensor([[
        complexity / 5, min(effort_points, 20) / 20,
        min(team_size, 10) / 10, min(dependencies, 10) / 10,
    ]], dtype=torch.float32)
    with torch.inference_mode():
        days = float(model(features)[0]) * 30
    return {
        "estimated_days": round(max(0.5, min(days, 120)), 1),
        "model": "MLP regression",
        "training_data": "synthetic",
    }


def predict_delay(progress, completed, pending, days_until_deadline, overdue, complexity):
    model = delay_model()
    features = torch.tensor([[
        progress / 100, min(completed, 100) / 100, min(pending, 100) / 100,
        max(-1, min(days_until_deadline, 90) / 90),
        min(overdue, 50) / 50, complexity / 5,
    ]], dtype=torch.float32)
    with torch.inference_mode():
        probabilities = model(features).softmax(dim=1)[0]
    index = int(probabilities.argmax())
    return {
        "forecast": ["on_time", "at_risk", "likely_delayed"][index],
        "score": round(float(probabilities[index]), 4),
        "model": "Deep feedforward network",
        "training_data": "synthetic",
    }
