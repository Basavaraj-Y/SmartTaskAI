# Dataset provenance and model evaluation

## Priority classification data

- **Source:** [javichur/jira-issue-dataset](https://github.com/javichur/jira-issue-dataset), file `100k-jira-issues-apache.csv`; its README describes more than 100,000 Apache-project Jira issues and cites the 2020 Jira Predictions project.
- **License:** The dataset repository includes an [Apache-2.0 license](https://raw.githubusercontent.com/javichur/jira-issue-dataset/main/LICENSE). Keep its attribution/license with any redistribution and confirm the institution accepts use of the issue text. The downloaded copy is kept locally under `deep_learning/datasets/raw/` and is not committed.
- **Inspected source fields:** the semicolon-delimited file has no header row. The first record and file layout identify these six fields: Issue Type, Issue Key, Resolution, Summary, Priority, and Status.
- **Used inputs/target:** Summary text and Issue Type are inputs; Priority is the target. Issue Key is used only to group train/validation/test splits by Jira project, never as a model input. Resolution and Status are excluded. In particular, final resolution/status fields are not model inputs.
- **Preprocessing:** malformed rows with fewer than six fields and rows missing the required type, summary, or priority are dropped. Any extra semicolon-separated fields in a summary are joined back together. Issue types are grouped into Bug, Improvement, New feature, and Other. Priority labels are mapped as Trivial/Low → Low; Minor/Normal → Medium; Major/High → High; Critical/Blocker/Urgent → Critical. The priority-label mapping is an explicit modelling choice, not a source-provided equivalence.
- **Sampling and split:** a seeded random sample of at most 20,000 valid records is used to keep local MPS/CPU training practical. Grouped splits hold out entire Jira projects from training and validation/test to reduce project-specific leakage; label distributions can therefore differ across splits. This run has 7 training, 1 validation, and 2 test projects, so validation and test project counts are small. The text vocabulary and TF-IDF baseline are fitted on training text only. Evaluation compares against majority-class and TF-IDF logistic-regression baselines.
- **Limitations:** Apache Jira issue summaries and project conventions are not representative of SmartTask AI users by default. Label mapping, source imbalance, and cross-project domain shift mean this model needs validation and preferably retraining on consented, representative task data before operational use.

The script records observed row counts, dropped rows, records used, split-level class counts, per-class metrics, raw and row-normalized confusion matrices, and baseline results in `deep_learning/experiments/evaluation.json`.

### Current measured holdout results

These are the results from the reproducible 2026-11-23 MPS training run (seed 41), not expected guarantees. The priority test holds out two complete Jira projects:

| Model | Held-out result | Baseline | Interpretation |
| --- | ---: | ---: | --- |
| Priority BiLSTM | Accuracy 21.68%; macro-F1 17.71% (4,040 examples) | Majority: 75.84% / 21.57%; TF-IDF + logistic regression: 68.71% / 26.17% (accuracy / macro-F1) | The BiLSTM underperforms both baselines on this cross-project holdout. Keep it as a pipeline/research demonstration only. |
| Completion MLP | MAE 1.55 days; RMSE 1.92 days (270 examples) | Median-duration MAE 5.08 days | Both model and baseline use synthetic labels; this does not establish real-world duration accuracy. |
| Delay feedforward network | Accuracy 91.67%; macro-F1 89.72% (360 examples) | Majority: 57.22% / 24.26% (accuracy / macro-F1) | Measures recovery of the synthetic label rule, not whether actual projects will be delayed. |

### BiLSTM performance investigation

The test set is highly imbalanced: Low 36 (0.89%), Medium 345 (8.54%), High 3,064 (75.84%), and Critical 595 (14.73%). This grouped split also shifts from the training mix (High 56.46%) to the test mix (High 75.84%). The class-weighted training objective increases predictions for minority classes, but on the held-out projects this comes with only 17.62% recall for High and 21.68% overall accuracy.

| Priority | Test support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| Low | 36 | 1.26% | 55.56% | 2.46% |
| Medium | 345 | 5.69% | 10.14% | 7.29% |
| High | 3,064 | 78.26% | 17.62% | 28.77% |
| Critical | 595 | 24.56% | 47.23% | 32.32% |

The evidence points to severe class imbalance, cross-project distribution shift, and limited input context (summary plus issue type), rather than a serving/artifact failure. Only ten project groups are represented, with one validation and two test groups; the scores therefore have substantial project-sampling uncertainty. The TF-IDF baseline gets higher accuracy and macro-F1 than the BiLSTM but still has very low Critical recall (0.34%), so it is not a validated operational replacement. Do not select or tune a model against the test projects; future improvements need more representative project groups and validation-only tuning, followed by a new untouched test set.

The priority confusion-matrix plots include both counts and row-normalized values. The completion scatter plot and delay confusion matrices are generated from held-out examples as well.

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
