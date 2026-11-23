import re

import torch
from torch import nn

PRIORITY_LABELS = ["low", "medium", "high", "critical"]
DELAY_LABELS = ["on_time", "at_risk", "likely_delayed"]
TASK_TYPES = ["bug", "improvement", "new_feature", "other"]
MAX_TOKENS = 32


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())[:MAX_TOKENS]


def encode_text(text, vocabulary):
    tokens = tokenize(text)
    indices = [vocabulary.get(token, 1) for token in tokens] or [1]
    indices = indices[:MAX_TOKENS]
    length = len(indices)
    return indices + [0] * (MAX_TOKENS - length), length


def encode_task_type(task_type):
    features = [0.0] * len(TASK_TYPES)
    features[TASK_TYPES.index(task_type)] = 1.0
    return features


class PriorityBiLSTM(nn.Module):
    def __init__(self, vocabulary_size, embedding_dim=48, hidden_dim=32, feature_count=4):
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2 + feature_count, 48),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(48, len(PRIORITY_LABELS)),
        )

    def forward(self, tokens, features):
        embedded = self.embedding(tokens)
        _, (hidden, _) = self.lstm(embedded)
        text = torch.cat((hidden[-2], hidden[-1]), dim=1)
        return self.classifier(torch.cat((text, features), dim=1))


class CompletionMLP(nn.Module):
    def __init__(self, feature_count=4):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(feature_count, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, features):
        return self.network(features).squeeze(1)


class DelayFeedForward(nn.Module):
    def __init__(self, feature_count=6):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(feature_count, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, len(DELAY_LABELS)),
        )

    def forward(self, features):
        return self.network(features)
