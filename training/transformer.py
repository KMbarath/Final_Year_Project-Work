"""MiniLM/DistilBERT fine-tuning with staged training, validation and locked test."""
import argparse
import copy
import json
import random
from pathlib import Path
import numpy as np
from .data import load_rows, split_rows, audit, noise



def train(dataset="data/synthetic/documents.csv", output="artifacts/minilm",
          model_name="microsoft/MiniLM-L12-H384-uncased", epochs=6, batch_size=4,
          max_length=192, seed=42, patience=2):
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, DataCollatorWithPadding
    from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = load_rows(dataset)
    splits = split_rows(rows, seed)
    report = audit(rows, splits)
    labels = sorted({r["label"] for r in rows})
    mapping = {label: i for i,label in enumerate(labels)}
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=len(labels), id2label=dict(enumerate(labels)), label2id=mapping,
        hidden_dropout_prob=0.15, attention_probs_dropout_prob=0.1)
    model.to(device)
    padder = DataCollatorWithPadding(tokenizer, pad_to_multiple_of=8)
    rng = random.Random(seed)

    def loader(subset, augment=False, shuffle=False):
        examples = []
        for row in subset:
            texts = [row["text"]]
            if augment:
                texts.append(noise(row["text"], rng, 0.10))
            for text in texts:
                encoded = tokenizer(text, truncation=True, max_length=max_length)
                encoded["labels"] = mapping[row["label"]]
                examples.append(encoded)
        return DataLoader(examples, batch_size=batch_size, shuffle=shuffle, collate_fn=padder,
                          generator=torch.Generator().manual_seed(seed), num_workers=0)

    train_loader = loader(splits["train"], augment=True, shuffle=True)
    train_eval = loader(splits["train"])
    val_loader = loader(splits["validation"])
    counts = np.bincount([mapping[r["label"]] for r in splits["train"]],minlength=len(labels))
    weights = torch.tensor(len(splits["train"])/(len(labels)*counts),dtype=torch.float32,device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)

    def evaluate(data):
        model.eval()
        total, n, predicted, truth, probs = 0., 0, [], [], []
        with torch.inference_mode():
            for batch in data:
                batch = {k:v.to(device) for k,v in batch.items()}
                target = batch.pop("labels")
                logits = model(**batch).logits
                total += float(torch.nn.functional.cross_entropy(logits,target,reduction="sum"))
                n += len(target)
                p = logits.softmax(-1)
                probs.extend(p.cpu().tolist())
                predicted.extend(p.argmax(-1).cpu().tolist())
                truth.extend(target.cpu().tolist())
        return {"loss":total/n,"accuracy":float(accuracy_score(truth,predicted)),
                "macro_f1":float(f1_score(truth,predicted,average="macro"))}, truth, predicted, np.array(probs)

    history, best_loss, best_state, stale = [], float("inf"), None, 0
    # First train the new classification head, then unfreeze the pretrained encoder.
    for epoch in range(epochs):
        head_only = epoch == 0
        for parameter in model.base_model.parameters():
            parameter.requires_grad = not head_only
        if epoch in (0,1):
            optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                                         lr=2e-4 if head_only else 2e-5,weight_decay=0.01)
        model.train()
        for batch in train_loader:
            batch = {k:v.to(device) for k,v in batch.items()}
            target = batch.pop("labels")
            optimizer.zero_grad(set_to_none=True)
            logits = model(**batch).logits
            loss = loss_fn(logits,target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
        tr,_,_,_ = evaluate(train_eval)
        val,_,_,_ = evaluate(val_loader)
        history.append({"epoch":epoch+1,"stage":"head_warmup" if head_only else "encoder_finetuning",
                        **{"train_"+k:v for k,v in tr.items()},**{"val_"+k:v for k,v in val.items()}})
        print(json.dumps(history[-1]),flush=True)
        (output/"history.json").write_text(json.dumps(history,indent=2))
        if val["loss"] < best_loss-0.001:
            best_loss, stale = val["loss"], 0
            best_state = {k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        else:
            stale += 1
        if not head_only and stale >= patience:
            break
    model.load_state_dict(best_state)
    validation, truth, predicted, p = evaluate(val_loader)
    threshold = 0.7
    for t in np.linspace(0.5,0.95,10):
        selected = p.max(1)>=t
        if selected.sum() >= max(10,len(truth)//4) and np.mean(np.array(truth)[selected]==np.array(predicted)[selected])>=0.95:
            threshold = float(t)
            break
    metadata = {"data_kind":report["data_kind"],"confidence_threshold":threshold,"model":model_name,
                "seed":seed,"max_length":max_length,"probability_note":"Not calibrated; validate on real documents."}
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    (output/"folio_metadata.json").write_text(json.dumps(metadata,indent=2))
    # No test feedback is used for checkpoint or threshold selection.
    test, truth, predicted, _ = evaluate(loader(splits["test"]))
    tr,_,_,_ = evaluate(train_eval)
    report.update({"model":model_name,"device":str(device),"seed":seed,"history":history,
                   "train":tr,"validation":validation,"test":test,"metadata":metadata,
                   "labels":labels,"classification_report":classification_report(truth,predicted,target_names=labels,output_dict=True,zero_division=0),
                   "confusion_matrix":confusion_matrix(truth,predicted,labels=list(range(len(labels)))).tolist(),
                   "diagnostics":{"possible_underfit":tr["macro_f1"]<0.85,
                                  "possible_overfit":tr["macro_f1"]-validation["macro_f1"]>0.08,
                                  "train_validation_f1_gap":tr["macro_f1"]-validation["macro_f1"]}})
    (output/"report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="data/synthetic/documents.csv")
    p.add_argument("--output", default="artifacts/minilm")
    p.add_argument("--model", default="microsoft/MiniLM-L12-H384-uncased")
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--batch-size", type=int, default=4)
    a = p.parse_args()
    result = train(a.dataset,a.output,a.model,a.epochs,a.batch_size)
    print(json.dumps({"test":result["test"],"diagnostics":result["diagnostics"]},indent=2))
