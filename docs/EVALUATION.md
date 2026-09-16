# Evaluation and honest accuracy claims

## What was measured

Training data: 1,152 generated samples, six classes, twelve template families per class,
sixteen records per family. Groups are disjoint across training, validation and test.
Names, dates and numbers are randomized; some examples contain simulated OCR character
substitutions. Template families remain stylistically related even across splits.

Both classifiers were trained. See artifacts/baseline/report.json and
artifacts/minilm/report.json for exact split sizes, histories, selected hyperparameters,
per-class metrics and confusion matrices. The baseline report has a group-bootstrap
accuracy interval. A [1,1] interval on perfect synthetic predictions says nothing about
real-world uncertainty.

The independent pipeline fixture set contains six fictional documents, six queries,
one unrelated question, and twelve rendered OCR images (clean and mildly degraded).
These are functional smoke checks, not statistically credible performance benchmarks.

## Underfitting and overfitting controls

Training-only augmentation; train-only feature fitting; group-disjoint splits; class
weights; validation-loss selection; patience-based early stopping; best-checkpoint
restoration. MiniLM adds dropout, weight decay, label smoothing and gradient clipping.

The simple alarms use training macro F1 below 0.85 for possible underfitting and a
train-minus-validation macro F1 gap above 0.08 for possible overfitting. These are
review prompts, not guarantees. Synthetic data is too easy to establish robustness.
Do not adjust models based on held-out test results.

## Real-world acceptance plan

Before reporting final-year-project accuracy:
- Collect consented, representative labelled documents and independent sources.
- Include photos, scans, blur, skew, multilingual documents and unsupported classes.
- Split by related person/source/template before augmentation and near-duplicate removal.
- Use train/validation data to tune; reserve a separate external test set.
- Report class counts, per-class precision/recall/F1, macro F1 and confidence intervals.
- Measure unknown-class rejection and calibrate confidence on held-out real validation data.
- Define and freeze application-specific targets before opening the external test results.

No universal target such as 99% is hard-coded as a guarantee.

## Module-specific metrics

| Module | Required evaluation |
|---|---|
| OCR | CER/WER by language, image quality and handwriting |
| Classification | Macro F1, per-class recall, unknown rejection and calibration |
| Entity extraction | Exact/partial span precision, recall and F1; date normalization accuracy |
| Retrieval | Recall@k and MRR on independently annotated queries |
| Generated answers | Factual entailment, citation correctness and unsupported-question abstention |
| Whisper | WER on user-representative accents and noise |
| Piper | Intelligibility and human listening assessment for the chosen language |
| IndicTrans2 | chrF/BLEU plus human preservation of names, dates and numbers |
| Reminders | Date correctness, catch-up behavior and no duplicate notifications |

No voice, translation, handwriting or LLM quality score is invented. The current
evaluation script explicitly lists those as not evaluated.

## Limitations affecting results

Transformer classification truncates at its configured training length. Labelled-field
parsing requires recognizable field labels. GLiNER considers only the first 12,000
characters. Retrieval is primarily lexical unless an embedding backend is configured.
Semantic score thresholds are generic defaults and need validation. Exact source
excerpts are evidence, not synthesized answers. Valid citations alone do not make an
LLM answer factually correct. Expiry reminders require a user-confirmed date.
