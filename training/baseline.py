import argparse
import copy
import json
import platform
import random
from pathlib import Path
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, f1_score, log_loss, classification_report, confusion_matrix
from .data import generate, load_rows, split_rows, audit, noise


def metrics(model, x, y):
    p = model.predict_proba(x)
    prediction = model.classes_[p.argmax(axis=1)]
    return {"accuracy": float(accuracy_score(y, prediction)),
            "macro_f1": float(f1_score(y, prediction, average="macro")),
            "loss": float(log_loss(y, p, labels=model.classes_))}


def train(dataset="data/synthetic/documents.csv", output="artifacts/baseline", max_epochs=60, seed=42):
    dataset, output = Path(dataset), Path(output)
    if not dataset.exists():
        raise FileNotFoundError("Generate synthetic data explicitly or provide a labelled CSV.")
    output.mkdir(parents=True, exist_ok=True)
    rows = load_rows(dataset)
    splits = split_rows(rows, seed)
    report = audit(rows, splits)
    report["seed"] = seed
    report["python"] = platform.python_version()
    (output / "split_manifest.json").write_text(json.dumps(report, indent=2))
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), min_df=2, max_features=35000, sublinear_tf=True)
    train_text = [r["text"] for r in splits["train"]]
    y_train = np.array([r["label"] for r in splits["train"]])
    x_train = vectorizer.fit_transform(train_text)
    x_val = vectorizer.transform([r["text"] for r in splits["validation"]])
    y_val = np.array([r["label"] for r in splits["validation"]])
    classes = np.unique(y_train)
    rng = random.Random(seed)
    candidates, histories, best_global = [], [], None
    best_loss = float("inf")
    # Stage 1: clean baseline. Stage 2: regularization search + train-only OCR augmentation.
    for stage, alpha, augment in [("clean_baseline", 1e-4, False),
                                   ("regularized_ocr", 1e-3, True),
                                   ("regularized_ocr", 1e-4, True)]:
        texts = train_text + [noise(t, rng, 0.12) for t in train_text] if augment else train_text
        x = vectorizer.transform(texts)
        y = np.tile(y_train, 2) if augment else y_train
        model = SGDClassifier(loss="log_loss", alpha=alpha, random_state=seed, learning_rate="optimal")
        weights = np.array([len(y) / (len(classes) * sum(y == label)) for label in y])
        local_best, wait, snapshot = float("inf"), 0, None
        for epoch in range(1, max_epochs+1):
            order = np.random.default_rng(seed+epoch).permutation(len(y))
            model.partial_fit(x[order], y[order], classes=classes, sample_weight=weights[order])
            tr, val = metrics(model, x_train, y_train), metrics(model, x_val, y_val)
            histories.append({"stage": stage, "alpha": alpha, "epoch": epoch,
                              **{"train_"+k: v for k,v in tr.items()}, **{"val_"+k:v for k,v in val.items()}})
            if val["loss"] < local_best - 1e-4:
                local_best, wait, snapshot = val["loss"], 0, copy.deepcopy(model)
            else:
                wait += 1
            if wait >= 6:
                break
        val = metrics(snapshot, x_val, y_val)
        candidates.append({"stage": stage, "alpha": alpha, "epochs_run": epoch, "validation": val})
        print(f"{stage} alpha={alpha}: val F1={val['macro_f1']:.4f}, loss={val['loss']:.4f}", flush=True)
        if val["loss"] < best_loss:
            best_loss, best_global = val["loss"], snapshot
            selected = candidates[-1]
    # Threshold selection uses validation only; uncalibrated probabilities are not guarantees.
    p_val = best_global.predict_proba(x_val)
    correct = best_global.classes_[p_val.argmax(1)] == y_val
    threshold = 0.7
    for t in np.linspace(0.5,0.95,10):
        accepted = p_val.max(1) >= t
        if accepted.sum() >= max(10, len(y_val)//4) and correct[accepted].mean() >= 0.95:
            threshold = float(t)
            break
    metadata = {"data_kind": report["data_kind"], "confidence_threshold": threshold, "seed": seed,
                "probability_note": "Validation-selected abstention threshold; probabilities are not calibrated."}
    joblib.dump({"vectorizer": vectorizer, "classifier": best_global, "metadata": metadata}, output / "model.joblib")
    # Test set is touched only after candidate and threshold selection.
    x_test = vectorizer.transform([r["text"] for r in splits["test"]])
    y_test = np.array([r["label"] for r in splits["test"]])
    predicted = best_global.predict(x_test)
    test = metrics(best_global, x_test, y_test)
    bootstrap = np.random.default_rng(seed)
    # Resample groups, not individual rows from correlated templates.
    test_groups = np.array([r["group"] for r in splits["test"]])
    unique_groups = np.unique(test_groups)
    accuracies = []
    for _ in range(500):
        sampled = bootstrap.choice(unique_groups, len(unique_groups), replace=True)
        ids = np.concatenate([np.flatnonzero(test_groups == g) for g in sampled])
        accuracies.append(float(np.mean(predicted[ids] == y_test[ids])))
    test["group_bootstrap_accuracy_95ci"] = np.quantile(accuracies,[0.025,0.975]).tolist()
    train_score = metrics(best_global, x_train, y_train)
    gap = train_score["macro_f1"] - selected["validation"]["macro_f1"]
    report.update({"candidates": candidates, "selected": selected, "train": train_score, "test": test,
                   "classification_report": classification_report(y_test,predicted,output_dict=True,zero_division=0),
                   "confusion_matrix": confusion_matrix(y_test,predicted,labels=classes).tolist(),
                   "labels": classes.tolist(), "history": histories, "metadata": metadata,
                   "diagnostics": {"train_validation_f1_gap": gap, "possible_overfit": gap > 0.08,
                                   "possible_underfit": train_score["macro_f1"] < 0.85,
                                   "note": "Heuristic flags, not proof that underfitting or overfitting is absent."}})
    (output / "report.json").write_text(json.dumps(report, indent=2))
    plot_report(report, output)
    return report


def plot_report(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,2,figsize=(12,4))
    for candidate in report["candidates"]:
        rows = [h for h in report["history"] if h["stage"] == candidate["stage"] and h["alpha"] == candidate["alpha"]]
        name = candidate["stage"] + " " + str(candidate["alpha"])
        axes[0].plot([r["epoch"] for r in rows],[r["train_loss"] for r in rows], "--", label=name+" train")
        axes[0].plot([r["epoch"] for r in rows],[r["val_loss"] for r in rows], label=name+" validation")
    axes[0].set(xlabel="Epoch",ylabel="Cross entropy",title="Train / validation learning curves")
    axes[0].legend(fontsize=6)
    axes[1].imshow(report["confusion_matrix"],cmap="Blues")
    axes[1].set(xticks=range(len(report["labels"])),yticks=range(len(report["labels"])),
                xticklabels=report["labels"],yticklabels=report["labels"],xlabel="Predicted",ylabel="True",title="Held-out synthetic test")
    axes[1].tick_params(axis="x",rotation=45)
    fig.tight_layout()
    fig.savefig(Path(output)/"training_report.png",dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/synthetic/documents.csv")
    parser.add_argument("--output", default="artifacts/baseline")
    parser.add_argument("--generate-demo", action="store_true")
    args = parser.parse_args()
    if args.generate_demo:
        if Path(args.dataset).exists():
            raise SystemExit("Dataset exists; omit --generate-demo to reuse it.")
        generate(args.dataset)
    result = train(args.dataset,args.output)
    print(json.dumps({"test":result["test"],"diagnostics":result["diagnostics"]},indent=2))
