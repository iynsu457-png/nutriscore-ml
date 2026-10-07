import time, sys
from huggingface_hub import hf_hub_download
t0 = time.time()
print("Downloading OFF food.parquet ...", flush=True)
path = hf_hub_download(
    repo_id="openfoodfacts/product-database",
    filename="food.parquet",
    repo_type="dataset",
    local_dir="data",
)
print(f"DONE in {time.time()-t0:.0f}s -> {path}", flush=True)
