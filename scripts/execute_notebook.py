from pathlib import Path
import nbformat
from nbclient import NotebookClient
root=Path(__file__).resolve().parents[1]
nb=nbformat.read(root/"notebooks/model_training.ipynb",as_version=4)
NotebookClient(nb,timeout=600,kernel_name="python3",resources={"metadata":{"path":str(root)}}).execute()
out=root/"notebooks/model_training.executed.ipynb"
nbformat.write(nb,out)
print("Executed:",out)
