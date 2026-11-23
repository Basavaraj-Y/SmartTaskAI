# Dataset provenance and model evaluation

## Priority classification data

- **Source:** [javichur/jira-issue-dataset](https://github.com/javichur/jira-issue-dataset), file `100k-jira-issues-apache.csv`; the repository describes more than 100,000 Apache-project Jira issues.
- **License:** Apache-2.0, verified from the repository's `LICENSE` file and GitHub repository metadata. The downloaded copy is kept locally under `deep_learning/datasets/raw/` and is not committed.
- **Inspected source fields:** the semicolon-delimited file has no header row. The first record and file layout identify these six fields: Issue Type, Issue Key, Resolution, Summary, Priority, and Status.
- **Used inputs/target:** Summary text and Issue Type are inputs; Priority is the target. Issue Key is used only to group train/validation/test splits by Jira project, never as a model input. Resolution and Status are excluded. In particular, final resolution/status fields are not model inputs.
- **Preprocessing:** malformed rows with fewer than six fields and rows missing the required type, summary, or priority are dropped. Any extra semicolon-separated fields in a summary are joined back together. Issue types are grouped into Bug, Improvement, New feature, and Other. Priority labels are mapped as Trivial/Low → Low; Minor/Normal → Medium; Major/High → High; Critical/Blocker/Urgent → Critical. The priority-label mapping is an explicit modelling choice, not a source-provided equivalence.
- **Sampling and split:** a seeded random sample of at most 20,000 valid records is used to keep local MPS/CPU training practical. Grouped splits hold out entire Jira projects from training and validation/test to reduce project-specific leakage; label distributions can therefore differ across splits. The text vocabulary is built using training text only. Evaluation compares against a majority-class baseline.
- **Limitations:** Apache Jira issue summaries and project conventions are not representative of SmartTask AI users by default. Label mapping, source imbalance, and cross-project domain shift mean this model needs validation and preferably retraining on consented, representative task data before operational use.

The script records observed row counts, dropped rows, records used, class metrics, and confusion matrix in `deep_learning/experiments/evaluation.json`.

### Current measured holdout results

These are the results from the checked-in evaluation report's 2026-11-23 MPS training run (seed 41), not expected guarantees. The priority test holds out two complete Jira projects:

| Model | Holdout metric | Simple baseline | Interpretation |
| --- | ---: | ---: | --- |
| Priority BiLSTM | Accuracy 21.68%; macro-F1 17.71% (4,040 examples) | Majority accuracy 75.84%; macro-F1 21.57% | Underperforms the majority baseline on this cross-project holdout. Keep it as a pipeline/research demonstration only. |
| Completion MLP | MAE 1.55 days; RMSE 1.92 days (270 examples) | Median-duration MAE 5.08 days | Both the model and baseline are evaluated on synthetic labels; this does not establish real-world duration accuracy. |
| Delay feedforward network | Accuracy 91.67%; macro-F1 89.72% (360 examples) | Majority accuracy 57.22%; macro-F1 24.26% | Measures how well the network recovers the synthetic label rule, not whether actual projects will be delayed. |

Classification score fields returned by the API are softmax outputs and are not probability-calibrated.

## Completion-time regression

No inspected public data file provides reliable task creation and resolution timestamps alongside the task-effort features required by this MVP. Training therefore uses generated synthetic examples only. Duration is generated from complexity, effort points, team size, and dependency count with bounded noise. These synthetic values are not real historical completion times. The random split is 70% training, 15% validation, and 15% test; model selection uses validation loss. The reported test MAE/RMSE are compared with a training-set median-duration baseline.

## Project-delay classification

The inspected Jira file contains no project deadline, project progress history, or project-level delivery outcome. Delay training therefore uses generated synthetic project snapshots. The On-time / At-risk / Likely delayed target is produced by a documented deterministic rule over generated progress, task counts, deadline distance, overdue-task count, and complexity. A random 70/15/15 train/validation/test split and a majority-class baseline are used. The result is a pipeline demonstration, not a validated delay predictor.

## Reproduce training and read results

```bash
python deep_learning/download_dataset.py
python deep_learning/train_models.py
```

If the raw priority file is not present, `train_models.py` explicitly records and uses a synthetic fallback for that model. It does not claim that fallback is public or historical data. Each model is trained and saved independently:

- `priority_bilstm.pt` and `priority_vocab.json`
- `completion_mlp.pt`
- `delay_ffn.pt`

All weights and raw/processed datasets are ignored by Git; regenerate them locally using the commands above. Holdout metrics and charts are emitted under `deep_learning/experiments/`. Scores in that report describe the recorded datasets and splits only and must not be presented as real-world accuracy.
