# Document classification model card

## Intended use
Demonstration of classification for passport, PAN, Aadhaar, medical, insurance and invoice
text in a personal document assistant. Suggestions require review. Not an identity
verification, fraud detection, medical interpretation or financial decision model.

## Models
- Baseline: character-within-word TF-IDF, n-grams 3–5, maximum 35,000 features, SGD logistic classifier.
- Transformer: microsoft/MiniLM-L12-H384-uncased with a newly initialized six-class head.
- The provided training script also accepts distilbert/distilbert-base-uncased.

## Provenance
1,152 generated records. No real user documents were used for training. Public pretrained
MiniLM weights were downloaded and locally fine-tuned on the GPU. No personal document
contents were transmitted to a model provider.

## Training
Seed 42. Training/validation/test groups are disjoint. Baseline candidates compare clean
text and OCR-augmented text with alpha values 0.0001 and 0.001. Candidate selection uses
validation cross entropy. MiniLM runs head warmup then full fine-tuning with learning
rates 0.0002 and 0.00002, dropout 0.15, weight decay 0.01, smoothing 0.05 and gradient
norm clipping at 1.0. Batch size 4, sequence length 192, six epochs maximum.

## Reported performance
Both models reached 100% accuracy and macro F1 on the synthetic test set. See exact
machine-readable reports under artifacts/. This dataset does not support a real-world
accuracy estimate. Low-confidence predictions are marked unknown; confidence is not
calibrated and unknown-class rejection has not been validated on a representative corpus.

## Limitations
Generated text differs from real personal records. Template vocabulary strongly predicts
class, so the task is easy. No handwriting, multilingual classification or adversarial
document robustness claim is made. The transformer truncates long inputs. Exact-text
deduplication does not eliminate all near-duplicates. Model artifacts must be loaded only
from trusted local sources.

## Model and dependency terms
Pretrained weights and dependencies retain their original licenses and access conditions.
Check those before redistribution. In particular, PyMuPDF and Piper have copyleft licensing
considerations, and Llama/IndicTrans2 model access conditions are separate from this code.
