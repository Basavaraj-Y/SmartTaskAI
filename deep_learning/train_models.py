"""Train three independent PyTorch models with explicit dataset provenance.

Priority uses public Jira issues when available, with a labelled synthetic
fallback. Completion and delay use synthetic examples; none are SmartTask AI
history or evidence of real-world predictive performance.
"""

import json
import random
import re
import sys
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.ml_models import (  # noqa: E402
    DELAY_LABELS,
    MAX_TOKENS,
    PRIORITY_LABELS,
    TASK_TYPES,
    CompletionMLP,
    DelayFeedForward,
    PriorityBiLSTM,
    encode_text,
    encode_task_type,
)

SEED = 41
EPOCHS = 24
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
MODEL_DIR = ROOT / "deep_learning" / "saved_models"
PROCESSED_DIR = ROOT / "deep_learning" / "datasets" / "processed"
EXPERIMENT_DIR = ROOT / "deep_learning" / "experiments"
PRIORITY_DATASET_PATH = ROOT / "deep_learning" / "datasets" / "raw" / "100k-jira-issues-apache.csv"
PRIORITY_DATASET_URL = "https://github.com/javichur/jira-issue-dataset"
MAX_PUBLIC_PRIORITY_ROWS = 20000


def set_seeds(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def split_indices(size, labels=None, groups=None):
    indices = np.arange(size)
    if groups is not None:
        train, remainder = next(
            GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=SEED).split(
                indices, labels, groups
            )
        )
        validation_relative, test_relative = next(
            GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=SEED + 1).split(
                remainder, labels[remainder], groups[remainder]
            )
        )
        return train, remainder[validation_relative], remainder[test_relative]
    stratify = labels if labels is not None and min(np.bincount(labels)) >= 3 else None
    train, rest = train_test_split(
        indices, test_size=0.30, random_state=SEED, stratify=stratify
    )
    rest_labels = labels[rest] if labels is not None and stratify is not None else None
    validation, test = train_test_split(
        rest, test_size=0.50, random_state=SEED, stratify=rest_labels
    )
    return train, validation, test


def priority_data(size=1800):
    contexts = [
        "Prepare the {area} for the upcoming release",
        "Review and improve the {area} requested by the product team",
        "Resolve a {area} issue affecting the customer workflow",
        "Document the {area} and verify the latest changes",
        "Complete the {area} before the integration milestone",
        "Investigate the {area} dependency and report findings",
    ]
    areas = [
        "payment service", "mobile navigation", "accessibility audit",
        "database migration", "analytics dashboard", "security review",
        "email notifications", "onboarding flow", "search index",
        "billing export", "deployment pipeline", "support workflow",
    ]
    priority_terms = {
        "low": ["routine", "optional", "backlog", "minor"],
        "medium": ["planned", "standard", "scheduled", "normal"],
        "high": ["important", "blocking", "time-sensitive", "customer-facing"],
        "critical": ["urgent", "outage", "security incident", "release blocker"],
    }
    rows = []
    for _ in range(size):
        urgency = random.random()
        complexity = random.randint(1, 5)
        due = random.randint(0, 60)
        effort = random.randint(1, 20)
        score = (
            0.30 * urgency
            + 0.16 * (complexity - 1) / 4
            + 0.21 * (1 - min(due, 30) / 30)
            + 0.13 * min(effort, 10) / 10
        )
        index = 0 if score < 0.21 else 1 if score < 0.37 else 2 if score < 0.55 else 3
        label = PRIORITY_LABELS[index]
        description = (
            random.choice(priority_terms[label])
            + " "
            + random.choice(contexts).format(area=random.choice(areas))
        )
        task_type = random.choice(TASK_TYPES)
        rows.append({
            "description": description,
            "task_type": task_type,
            "label": index,
        })
    return pd.DataFrame(rows)


def normalized_task_type(value):
    normalized = value.strip().lower()
    if normalized == "bug":
        return "bug"
    if normalized == "improvement":
        return "improvement"
    if normalized in {"new feature", "new-feature"}:
        return "new_feature"
    return "other"


def load_priority_data():
    if not PRIORITY_DATASET_PATH.is_file():
        return priority_data(), {
            "source": "synthetic_fallback",
            "note": "The public Jira file was not present; generated synthetic examples were used.",
            "license": "Not applicable; generated data.",
            "records_used": 1800,
        }

    priority_map = {
        "trivial": 0, "low": 0,
        "minor": 1, "normal": 1,
        "major": 2, "high": 2,
        "critical": 3, "blocker": 3, "urgent": 3,
    }
    rows = []
    malformed_rows = 0
    missing_rows = 0
    unknown_priority_rows = 0
    raw_rows = 0
    with PRIORITY_DATASET_PATH.open(encoding="utf-8", newline="") as source:
        for fields in csv.reader(source, delimiter=";"):
            raw_rows += 1
            if len(fields) < 6:
                malformed_rows += 1
                continue
            issue_type = fields[0].strip()
            description = ";".join(fields[3:-2]).strip()
            priority = fields[-2].strip().lower()
            if not issue_type or not description or not priority:
                missing_rows += 1
                continue
            if priority not in priority_map:
                unknown_priority_rows += 1
                continue
            rows.append({
                "description": description,
                "task_type": normalized_task_type(issue_type),
                "project_group": fields[1].partition("-")[0],
                "label": priority_map[priority],
            })

    if not rows:
        raise ValueError(
            f"No usable priority examples found in {PRIORITY_DATASET_PATH.name}."
        )
    frame = pd.DataFrame(rows)
    if len(frame) > MAX_PUBLIC_PRIORITY_ROWS:
        frame = frame.sample(n=MAX_PUBLIC_PRIORITY_ROWS, random_state=SEED)
    metadata = {
        "source": PRIORITY_DATASET_URL,
        "license": "Apache-2.0 (repository LICENSE file)",
        "source_columns": [
            "Issue Type", "Issue Key", "Resolution", "Summary", "Priority", "Status"
        ],
        "used_columns": ["Issue Type", "Summary", "Priority"],
        "excluded_columns": ["Issue Key (used only to group project splits)", "Resolution", "Status"],
        "split_strategy": "GroupShuffleSplit by project key; the project key is not a model input.",
        "project_groups": frame["project_group"].nunique(),
        "priority_mapping": {
            "Trivial/Low": "low",
            "Minor/Normal": "medium",
            "Major/High": "high",
            "Critical/Blocker/Urgent": "critical",
        },
        "raw_rows": raw_rows,
        "malformed_rows_dropped": malformed_rows,
        "rows_with_missing_required_values_dropped": missing_rows,
        "rows_with_unmapped_priority_dropped": unknown_priority_rows,
        "usable_rows": len(rows),
        "records_used": len(frame),
        "sampling": (
            f"Uniform random sample with seed {SEED}; maximum {MAX_PUBLIC_PRIORITY_ROWS} records."
        ),
        "limitations": (
            "Apache Jira issue summaries and priorities may not represent this application's users; "
            "mapped labels are cross-project approximations and require local validation."
        ),
    }
    return frame.reset_index(drop=True), metadata


def completion_data(size=1800):
    rows = []
    for _ in range(size):
        complexity = random.randint(1, 5)
        effort = random.randint(1, 20)
        team_size = random.randint(1, 8)
        dependencies = random.randint(0, 8)
        days = (
            0.5 + 0.75 * effort + 0.9 * complexity + 1.5 * dependencies
            - 0.55 * (team_size - 1) + random.gauss(0, 2.2)
        )
        rows.append({
            "complexity": complexity,
            "effort_points": effort,
            "team_size": team_size,
            "dependencies": dependencies,
            "duration_days": round(max(0.5, min(days, 60)), 2),
        })
    return pd.DataFrame(rows)


def delay_data(size=2400):
    rows = []
    for _ in range(size):
        total = random.randint(4, 50)
        completed = random.randint(0, total)
        pending = total - completed
        progress = max(0, min(100, 100 * completed / total + random.gauss(0, 5)))
        days = random.randint(-14, 90)
        complexity = random.randint(1, 5)
        overdue = random.randint(0, min(pending, 12)) if days < 14 else random.randint(0, 3)
        risk = (
            pending * complexity / (max(days, 0) + 10) / 4
            + 0.075 * overdue
            - 0.006 * progress
        )
        label = 0 if risk < 0.12 else 1 if risk < 0.55 else 2
        rows.append({
            "progress": progress,
            "completed": completed,
            "pending": pending,
            "days_until_deadline": days,
            "overdue": overdue,
            "complexity": complexity,
            "label": label,
        })
    return pd.DataFrame(rows)


def tensors(values):
    return torch.as_tensor(values, dtype=torch.float32)


def train_model(model, train_dataset, validation_dataset, criterion, epochs=EPOCHS):
    model.to(DEVICE)
    training = DataLoader(train_dataset, batch_size=64, shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002, weight_decay=1e-4)
    best_loss = float("inf")
    best_weights = None
    patience = 5
    stale_epochs = 0
    for _ in range(epochs):
        model.train()
        for batch in training:
            batch = tuple(value.to(DEVICE) for value in batch)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(*batch[:-1]), batch[-1])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            validation_loss = 0.0
            count = 0
            for batch in DataLoader(validation_dataset, batch_size=128):
                batch = tuple(value.to(DEVICE) for value in batch)
                validation_loss += criterion(model(*batch[:-1]), batch[-1]).item() * len(batch[-1])
                count += len(batch[-1])
        validation_loss /= max(count, 1)
        if validation_loss < best_loss - 1e-5:
            best_loss = validation_loss
            best_weights = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break
    if best_weights is not None:
        model.load_state_dict(best_weights)
    return model.cpu()


def per_class_metrics(actual, predictions, label_names):
    precision, recall, f1, support = precision_recall_fscore_support(
        actual,
        predictions,
        labels=np.arange(len(label_names)),
        zero_division=0,
    )
    return {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(label_names)
    }


def classifier_metrics(model, inputs, labels, label_names, baseline, chart_path):
    model.eval()
    with torch.inference_mode():
        predictions = model(*inputs).argmax(dim=1).cpu().numpy()
    actual = labels.cpu().numpy()
    baseline_predictions = np.full_like(actual, baseline)
    result = {
        "test_accuracy": float(accuracy_score(actual, predictions)),
        "test_macro_f1": float(f1_score(actual, predictions, average="macro", zero_division=0)),
        "majority_baseline_accuracy": float(accuracy_score(actual, baseline_predictions)),
        "majority_baseline_macro_f1": float(
            f1_score(actual, baseline_predictions, average="macro", zero_division=0)
        ),
        "test_examples": int(len(actual)),
        "per_class": per_class_metrics(actual, predictions, label_names),
    }
    matrix = confusion_matrix(actual, predictions, labels=np.arange(len(label_names)))
    fig, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set(
        xticks=np.arange(len(label_names)), yticks=np.arange(len(label_names)),
        xticklabels=label_names, yticklabels=label_names,
        xlabel="Predicted label", ylabel="True label",
        title="Held-out confusion matrix",
    )
    plt.setp(axis.get_xticklabels(), rotation=25, ha="right")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(column, row, str(matrix[row, column]), ha="center", va="center")
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=140)
    plt.close(fig)
    result["confusion_matrix"] = matrix.tolist()
    row_totals = matrix.sum(axis=1, keepdims=True)
    normalized_matrix = np.divide(
        matrix,
        row_totals,
        out=np.zeros_like(matrix, dtype=float),
        where=row_totals != 0,
    )
    fig, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(normalized_matrix, cmap="Blues", vmin=0, vmax=1)
    axis.set(
        xticks=np.arange(len(label_names)), yticks=np.arange(len(label_names)),
        xticklabels=label_names, yticklabels=label_names,
        xlabel="Predicted label", ylabel="True label",
        title="Row-normalized held-out confusion matrix",
    )
    plt.setp(axis.get_xticklabels(), rotation=25, ha="right")
    for row in range(normalized_matrix.shape[0]):
        for column in range(normalized_matrix.shape[1]):
            axis.text(
                column,
                row,
                f"{normalized_matrix[row, column]:.2f}",
                ha="center",
                va="center",
            )
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    normalized_path = chart_path.with_name(
        f"{chart_path.stem}_normalized{chart_path.suffix}"
    )
    fig.savefig(normalized_path, dpi=140)
    plt.close(fig)
    result["normalized_confusion_matrix"] = normalized_matrix.tolist()
    return result


def train_priority():
    frame, provenance = load_priority_data()
    frame.to_csv(PROCESSED_DIR / "priority_training.csv", index=False)
    labels = frame["label"].to_numpy()
    groups = frame["project_group"].to_numpy() if "project_group" in frame else None
    train, validation, test = split_indices(len(frame), labels, groups=groups)
    provenance["split_examples"] = {
        "train": int(len(train)),
        "validation": int(len(validation)),
        "test": int(len(test)),
    }
    if groups is not None:
        provenance["projects_per_split"] = {
            "train": int(pd.Series(groups[train]).nunique()),
            "validation": int(pd.Series(groups[validation]).nunique()),
            "test": int(pd.Series(groups[test]).nunique()),
        }
    provenance["class_counts_by_split"] = {
        split_name: {
            label: int(np.count_nonzero(labels[indices] == label_index))
            for label_index, label in enumerate(PRIORITY_LABELS)
        }
        for split_name, indices in (
            ("train", train),
            ("validation", validation),
            ("test", test),
        )
    }
    vocabulary = {"<pad>": 0, "<unk>": 1}
    for text in frame.iloc[train]["description"]:
        for token in re.findall(r"[a-z0-9]+", text.lower())[:MAX_TOKENS]:
            vocabulary.setdefault(token, len(vocabulary))
    encoded = [encode_text(text, vocabulary)[0] for text in frame["description"]]
    numeric = np.asarray([
        encode_task_type(task_type) for task_type in frame["task_type"]
    ], dtype=np.float32)
    tokens = torch.tensor(encoded, dtype=torch.long)
    features = tensors(numeric)
    target = torch.tensor(labels, dtype=torch.long)
    class_weights = len(train) / (
        len(PRIORITY_LABELS) * np.bincount(labels[train], minlength=len(PRIORITY_LABELS))
    )
    model = train_model(
        PriorityBiLSTM(len(vocabulary)),
        TensorDataset(tokens[train], features[train], target[train]),
        TensorDataset(tokens[validation], features[validation], target[validation]),
        nn.CrossEntropyLoss(weight=tensors(class_weights).to(DEVICE)),
    )
    counts = np.bincount(labels[train], minlength=len(PRIORITY_LABELS))
    baseline = int(np.argmax(counts))
    metrics = classifier_metrics(
        model, (tokens[test], features[test]), target[test],
        PRIORITY_LABELS, baseline,
        EXPERIMENT_DIR / "priority_confusion_matrix.png",
    )
    text_baseline = make_pipeline(
        ColumnTransformer(
            [
                (
                    "summary",
                    TfidfVectorizer(
                        max_features=40000,
                        ngram_range=(1, 2),
                        min_df=2,
                        sublinear_tf=True,
                    ),
                    "description",
                ),
                (
                    "task_type",
                    OneHotEncoder(handle_unknown="ignore"),
                    ["task_type"],
                ),
            ]
        ),
        LogisticRegression(max_iter=500, random_state=SEED),
    )
    features_frame = frame[["description", "task_type"]]
    text_baseline.fit(features_frame.iloc[train], labels[train])
    baseline_predictions = text_baseline.predict(features_frame.iloc[test])
    metrics["tfidf_logistic_regression_baseline"] = {
        "test_accuracy": float(accuracy_score(labels[test], baseline_predictions)),
        "test_macro_f1": float(
            f1_score(labels[test], baseline_predictions, average="macro", zero_division=0)
        ),
        "test_examples": int(len(test)),
        "per_class": per_class_metrics(
            labels[test], baseline_predictions, PRIORITY_LABELS
        ),
        "confusion_matrix": confusion_matrix(
            labels[test], baseline_predictions, labels=np.arange(len(PRIORITY_LABELS))
        ).tolist(),
    }
    metrics["dataset_source"] = provenance["source"]
    metrics["dataset_records"] = provenance["records_used"]
    torch.save(
        {"state_dict": model.state_dict(), "training_data": provenance["source"]},
        MODEL_DIR / "priority_bilstm.pt",
    )
    (MODEL_DIR / "priority_vocab.json").write_text(json.dumps(vocabulary), encoding="utf-8")
    return metrics, provenance


def train_completion():
    frame = completion_data()
    frame.to_csv(PROCESSED_DIR / "completion_synthetic.csv", index=False)
    inputs = np.column_stack((
        frame["complexity"].to_numpy() / 5,
        np.minimum(frame["effort_points"].to_numpy(), 20) / 20,
        np.minimum(frame["team_size"].to_numpy(), 10) / 10,
        np.minimum(frame["dependencies"].to_numpy(), 10) / 10,
    )).astype(np.float32)
    target = (frame["duration_days"].to_numpy(dtype=np.float32) / 30)
    train, validation, test = split_indices(len(frame))
    x, y = tensors(inputs), tensors(target)
    model = train_model(
        CompletionMLP(),
        TensorDataset(x[train], y[train]),
        TensorDataset(x[validation], y[validation]),
        nn.SmoothL1Loss(),
    )
    model.eval()
    with torch.inference_mode():
        predicted = model(x[test]).cpu().numpy() * 30
    actual = target[test] * 30
    median_baseline = float(np.median(target[train]) * 30)
    metrics = {
        "test_mae_days": float(mean_absolute_error(actual, predicted)),
        "test_rmse_days": float(np.sqrt(mean_squared_error(actual, predicted))),
        "median_baseline_mae_days": float(
            mean_absolute_error(actual, np.full_like(actual, median_baseline))
        ),
        "test_examples": int(len(test)),
        "split_examples": {
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
        },
    }
    fig, axis = plt.subplots(figsize=(6, 5))
    axis.scatter(actual, predicted, alpha=0.45, s=12)
    axis.plot([0, 60], [0, 60], "r--", linewidth=1)
    axis.set(xlabel="Synthetic actual duration (days)", ylabel="Predicted duration (days)",
             title="Completion MLP — held-out examples")
    fig.tight_layout()
    fig.savefig(EXPERIMENT_DIR / "completion_actual_vs_predicted.png", dpi=140)
    plt.close(fig)
    torch.save({"state_dict": model.state_dict()}, MODEL_DIR / "completion_mlp.pt")
    return metrics


def train_delay():
    frame = delay_data()
    frame.to_csv(PROCESSED_DIR / "delay_synthetic.csv", index=False)
    labels = frame["label"].to_numpy()
    inputs = np.column_stack((
        frame["progress"].to_numpy() / 100,
        np.minimum(frame["completed"].to_numpy(), 100) / 100,
        np.minimum(frame["pending"].to_numpy(), 100) / 100,
        np.clip(frame["days_until_deadline"].to_numpy(), -90, 90) / 90,
        np.minimum(frame["overdue"].to_numpy(), 50) / 50,
        frame["complexity"].to_numpy() / 5,
    )).astype(np.float32)
    train, validation, test = split_indices(len(frame), labels)
    x = tensors(inputs)
    target = torch.tensor(labels, dtype=torch.long)
    model = train_model(
        DelayFeedForward(),
        TensorDataset(x[train], target[train]),
        TensorDataset(x[validation], target[validation]),
        nn.CrossEntropyLoss(),
    )
    baseline = int(np.argmax(np.bincount(labels[train], minlength=len(DELAY_LABELS))))
    metrics = classifier_metrics(
        model, (x[test],), target[test], DELAY_LABELS, baseline,
        EXPERIMENT_DIR / "delay_confusion_matrix.png",
    )
    metrics["split_examples"] = {
        "train": int(len(train)),
        "validation": int(len(validation)),
        "test": int(len(test)),
    }
    torch.save({"state_dict": model.state_dict()}, MODEL_DIR / "delay_ffn.pt")
    return metrics


def main():
    set_seeds()
    for directory in (MODEL_DIR, PROCESSED_DIR, EXPERIMENT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    priority_metrics, priority_provenance = train_priority()
    results = {
        "seed": SEED,
        "device": str(DEVICE),
        "datasets": {
            "priority": priority_provenance,
            "completion": {
                "source": "synthetic",
                "license": "Not applicable; generated data.",
                "records": 1800,
                "note": "No public source with compatible effort/complexity inputs and actual resolution dates was selected.",
            },
            "delay": {
                "source": "synthetic",
                "license": "Not applicable; generated data.",
                "records": 2400,
                "note": "The inspected Jira dataset has no project deadlines or progress history for delay labels.",
            },
        },
        "models": {
            "priority_bilstm": priority_metrics,
            "completion_mlp": train_completion(),
            "delay_ffn": train_delay(),
        },
    }
    report_path = EXPERIMENT_DIR / "evaluation.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"Saved evaluation to {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
