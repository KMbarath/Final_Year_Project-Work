"""Independent, explicit synthetic pipeline smoke benchmark."""
import io
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, timedelta
import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from folio.config import Settings, ROOT
from folio.service import Assistant
from folio.extraction import Extractor

SAMPLES = {
    "passport": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nRepublic of India Passport\nName: Sam Kumar\nPassport number: P1234567\nNationality: Indian\nDate of birth: 1995-03-12\nExpiry date: 2032-06-10",
    "pan": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nIncome Tax Department\nPermanent Account Number card\nName: Meera Rao\nPAN number: ABCDE1234F\nDate of birth: 1993-08-19",
    "aadhaar": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nUnique Identification Authority\nAadhaar identity letter\nName: Arun Nair\nAadhaar number: 9999 1234 5678\nDate of birth: 1990-02-20\nAddress: Chennai",
    "medical": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nHospital diagnostic laboratory report\nPatient name: Riya Shah\nPatient ID: MED98765\nTest: complete blood count\nHemoglobin: 12.5 g/dL",
    "insurance": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nHealth insurance policy\nInsured name: Dev Patel\nPolicy number: INS7654321\nSum insured: INR 500000\nPremium paid: INR 12000\nPolicy end date: " + (date.today()+timedelta(days=20)).isoformat(),
    "invoice": "FICTIONAL SAMPLE - NOT A VALID DOCUMENT\nTax invoice\nInvoice number: INV4567890\nName: Asha Sen\nSubtotal: INR 10000\nGST: 18 percent\nAmount due: INR 11800"
}
QUERIES = [("When does my passport expire?","passport"),("What is my PAN number?","pan"),
           ("What is the Aadhaar number?","aadhaar"),("What was the hemoglobin result?","medical"),
           ("What is my insurance policy number?","insurance"),("What is the invoice subtotal?","invoice")]


def render(text):
    image=Image.new("RGB",(1500,900),"white")
    font_path=Path("C:/Windows/Fonts/arial.ttf")
    font=ImageFont.truetype(str(font_path),32) if font_path.exists() else ImageFont.load_default(size=32)
    ImageDraw.Draw(image).multiline_text((65,65),text,font=font,fill="black",spacing=25)
    return image


def samples(folder="data/samples"):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    for label,text in SAMPLES.items():
        (folder/(label+".txt")).write_text(text,encoding="utf-8")
        pdf=pymupdf.open()
        page=pdf.new_page()
        page.insert_textbox(pymupdf.Rect(40,40,560,790),text,fontsize=14)
        pdf.save(folder/(label+".pdf"))
        pdf.close()
    image=render(SAMPLES["passport"])
    image.save(folder/"passport_scan.png")
    scanned=pymupdf.open()
    page=scanned.new_page(width=750,height=450)
    buffer=io.BytesIO();image.save(buffer,format="PNG")
    page.insert_image(page.rect,stream=buffer.getvalue())
    scanned.save(folder/"passport_scanned.pdf")
    scanned.close()


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def evaluate(output="artifacts/evaluation", ocr=True):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    metrics,details={},{}
    with TemporaryDirectory() as temp:
        assistant=Assistant(Settings(data_dir=Path(temp),classifier_path=ROOT/"artifacts/baseline/model.joblib"))
        ids={}
        for label,text in SAMPLES.items():
            document=assistant.ingest(text.encode(),label+".txt")
            ids[label]=document["id"]
        docs=assistant.store.list()
        hits=[assistant.retriever.search(q,docs) for q,_ in QUERIES]
        metrics["retrieval_recall_at_1"]=sum(bool(h) and h[0]["document_id"]==ids[label] for h,(_,label) in zip(hits,QUERIES))/len(QUERIES)
        metrics["retrieval_recall_at_3"]=sum(any(x["document_id"]==ids[label] for x in h[:3]) for h,(_,label) in zip(hits,QUERIES))/len(QUERIES)
        metrics["classification_accuracy"]=sum(d["classification"]["label"]==d["filename"].split(".")[0] for d in docs)/len(docs)
        metrics["unrelated_question_abstained"]=assistant.ask("How tall is Mount Everest?")["mode"]=="abstained"
        expected={"passport":{"name":"Sam Kumar","document_number":"P1234567","expiry_date":"2032-06-10"},
                  "pan":{"name":"Meera Rao","document_number":"ABCDE1234F"},
                  "insurance":{"name":"Dev Patel","document_number":"INS7654321"}}
        correct=total=0
        for label,fields in expected.items():
            actual={e["label"]:e["text"] for e in assistant.store.get(ids[label])["entities"]}
            for key,value in fields.items():
                total+=1;correct+=actual.get(key)==value
        metrics["labelled_field_exact_match"]=correct/total
        details["retrieval"]=[{"question":q,"expected":label,"top":h[0]["filename"] if h else None} for (q,label),h in zip(QUERIES,hits)]
    if ocr:
        extractor=Extractor("tesseract")
        results=[]
        for label,text in SAMPLES.items():
            for variant in ["clean","blurred_rotated"]:
                image=render(text)
                if variant=="blurred_rotated":
                    image=image.rotate(1.2,fillcolor="white").filter(ImageFilter.GaussianBlur(.4))
                predicted=extractor.ocr(image)
                normalize=lambda t: re.sub(r"\s+"," ",t).strip()
                truth,prediction=normalize(text),normalize(predicted)
                results.append({"label":label,"variant":variant,"cer":edit_distance(truth,prediction)/max(1,len(truth)),
                                "wer":edit_distance(truth.split(),prediction.split())/max(1,len(truth.split()))})
        metrics["ocr_mean_cer"]=sum(r["cer"] for r in results)/len(results)
        metrics["ocr_mean_wer"]=sum(r["wer"] for r in results)/len(results)
        details["ocr"]=results
    report={"data_kind":"synthetic","metrics":metrics,"details":details,
            "warning":"Twelve rendered OCR fixtures and six document/query fixtures only; not a real-world benchmark. Voice, translation and LLM quality require separate datasets.",
            "not_evaluated":["voice WER","translation chrF/BLEU","LLM factual entailment","real scans","handwriting"]}
    (output/"report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__=="__main__":
    samples()
    print(json.dumps(evaluate(),indent=2))
