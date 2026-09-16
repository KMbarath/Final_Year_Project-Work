"""Synthetic examples are engineering fixtures, not an accuracy benchmark."""
import csv
import hashlib
import random
import re
from pathlib import Path
from collections import Counter
from sklearn.model_selection import StratifiedGroupKFold

SEED = 42
HEADINGS = {
    "passport": ["Republic of India Passport", "International travel passport", "Passport holder particulars",
                 "Travel identity booklet", "Passport services record", "Personal passport details",
                 "Immigration travel document", "Passport issuing authority", "Republic passport record",
                 "International passport identification", "Passport renewal particulars", "Travel passport certificate"],
    "pan": ["Income Tax Department PAN", "Permanent Account Number card", "Taxpayer PAN particulars",
            "Income tax identity", "PAN allotment confirmation", "Permanent tax account record",
            "Tax identification PAN card", "Indian income tax account", "Taxpayer permanent account",
            "PAN registration details", "Income Tax PAN verification", "Permanent account identification"],
    "aadhaar": ["Unique Identification Authority Aadhaar", "Aadhaar identity letter", "Resident Aadhaar record",
                "Government unique identification card", "Aadhaar enrollment confirmation", "UIDAI identity particulars",
                "Resident unique identity", "Aadhaar demographic details", "UIDAI resident certificate",
                "Aadhaar verification slip", "Unique resident identification number", "Aadhaar card record"],
    "medical": ["Laboratory medical report", "Hospital patient discharge summary", "Diagnostic blood test report",
                "Clinical patient examination", "Pathology laboratory results", "Medical consultation record",
                "Patient diagnostic findings", "Hospital treatment summary", "Clinical laboratory investigation",
                "Medical health assessment", "Patient pathology report", "Hospital laboratory certificate"],
    "insurance": ["Insurance policy schedule", "Health insurance certificate", "Motor insurance policy",
                  "Life assurance coverage", "Insurance renewal notice", "Policyholder benefit schedule",
                  "Insurance coverage confirmation", "Insurer policy particulars", "Insurance contract summary",
                  "Policy protection certificate", "Insurance premium receipt", "Assured coverage statement"],
    "invoice": ["Tax invoice", "Purchase invoice receipt", "Commercial billing statement",
                "Sales invoice details", "Goods and services bill", "Supplier invoice summary",
                "Payment invoice record", "Customer billing receipt", "GST tax invoice",
                "Sales purchase receipt", "Itemized invoice statement", "Business billing document"]
}
DETAILS = {
    "passport": ["Passport number: P{number}", "Nationality: Indian", "Place of issue: {city}", "Expiry date: {expiry}"],
    "pan": ["PAN number: ABCDE{digits}F", "Income tax account status: active", "Signature of taxpayer", "Father name: {parent}"],
    "aadhaar": ["Aadhaar number: 9999 {digits} {digits2}", "Address: {city}", "Unique identification resident", "Enrollment: {number}"],
    "medical": ["Patient ID: MED{number}", "Hemoglobin: {level} g/dL", "Test: complete blood count", "Doctor: Dr. {parent}"],
    "insurance": ["Policy number: INS{number}", "Sum insured: INR {amount}", "Premium paid: INR {premium}", "Policy end date: {expiry}"],
    "invoice": ["Invoice number: INV{number}", "Subtotal: INR {amount}", "GST: 18 percent", "Payment due: {expiry}"]
}


def noise(text, rng, rate=0.025):
    swaps = {"O": "0", "o": "0", "I": "1", "l": "1", "e": "c"}
    return "".join(swaps.get(c, c) if rng.random() < rate else c for c in text)


def generate(path, per_template=16, seed=SEED):
    rng = random.Random(seed)
    names = ["Arun", "Meera", "Dev", "Riya", "Kiran", "Anita", "Sam", "Priya", "Asha", "Ravi"]
    surnames = ["Rao", "Shah", "Patel", "Das", "Kumar", "Nair", "Singh", "Sen"]
    rows = []
    for label, headings in HEADINGS.items():
        for family, heading in enumerate(headings):
            for sample in range(per_template):
                v = dict(number=rng.randrange(1000000, 9999999), digits=rng.randrange(1000,9999), digits2=rng.randrange(1000,9999),
                         city=rng.choice(["Chennai", "Mumbai", "Kochi", "Delhi", "Pune"]), parent=rng.choice(names),
                         expiry=f"{rng.randrange(2027,2036)}-{rng.randrange(1,13):02d}-{rng.randrange(1,29):02d}",
                         amount=rng.randrange(10,1000)*100, premium=rng.randrange(10,100)*100, level=round(rng.uniform(9,16),1))
                full_name = rng.choice(names) + " " + rng.choice(surnames)
                fields = [line.format(**v) for line in DETAILS[label]]
                fields += ["Name: " + full_name, f"Date of birth: {rng.randrange(1960,2005)}-03-12"]
                if family % 3 == 1:
                    rng.shuffle(fields)
                separator = "\n" if family % 3 != 2 else "; "
                text = heading + "\n" + separator.join(fields)
                if sample % 4 == 0:
                    text = noise(text, rng)
                rows.append({"text": text, "label": label, "group": f"{label}:layout-{family}",
                             "data_kind": "synthetic"})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label", "group", "data_kind"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def fingerprint(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()


def load_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or not {"text", "label", "group"}.issubset(rows[0]):
        raise ValueError("CSV requires text, label, group columns.")
    seen, clean = {}, []
    for row in rows:
        if not all(row.get(k, "").strip() for k in ["text", "label", "group"]):
            raise ValueError("Empty text, label or group.")
        key = fingerprint(row["text"])
        if key in seen:
            if seen[key] != row["label"]:
                raise ValueError("Duplicate text has conflicting labels.")
            continue
        seen[key] = row["label"]
        clean.append(row)
    if len(set(r["label"] for r in clean)) < 2:
        raise ValueError("At least two document classes are required.")
    for label in set(r["label"] for r in clean):
        if len(set(r["group"] for r in clean if r["label"] == label)) < 6:
            raise ValueError(f"{label}: need at least six independent groups for a reliable split.")
    return clean


def split_rows(rows, seed=SEED):
    labels, groups = [r["label"] for r in rows], [r["group"] for r in rows]
    splitter = StratifiedGroupKFold(n_splits=6, shuffle=True, random_state=seed)
    folds = [list(test) for _, test in splitter.split(rows, labels, groups)]
    indices = {"train": [i for fold in folds[:4] for i in fold], "validation": folds[4], "test": folds[5]}
    splits = {name: [rows[i] for i in ids] for name, ids in indices.items()}
    classes = set(labels)
    for name, subset in splits.items():
        if set(r["label"] for r in subset) != classes:
            raise ValueError(f"{name} lacks classes. Provide more independent groups.")
    for a, b in [("train","validation"), ("train","test"), ("validation","test")]:
        assert not {r["group"] for r in splits[a]} & {r["group"] for r in splits[b]}
        assert not {fingerprint(r["text"]) for r in splits[a]} & {fingerprint(r["text"]) for r in splits[b]}
    return splits


def audit(rows, splits):
    return {"data_kind": "synthetic" if all(r.get("data_kind") == "synthetic" for r in rows) else "user_supplied_unverified",
            "dataset_sha256": hashlib.sha256(str(rows).encode()).hexdigest(),
            "samples": len(rows), "classes": dict(Counter(r["label"] for r in rows)),
            "split_sizes": {k: len(v) for k,v in splits.items()},
            "groups": {k: sorted(set(r["group"] for r in v)) for k,v in splits.items()},
            "warning": "Synthetic scores do not estimate performance on real documents. Group related people/templates/scans together."}
