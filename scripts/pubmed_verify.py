import json, time, urllib.request, urllib.parse
BASE="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
UA={"User-Agent":"NutriScoreML-research/0.1 (academic)"}
def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=30))
def search(term, n=3):
    u=BASE+"esearch.fcgi?"+urllib.parse.urlencode({"db":"pubmed","term":term,"retmode":"json","retmax":n})
    ids=get(u).get("esearchresult",{}).get("idlist",[])
    if not ids: return []
    time.sleep(0.4)
    u2=BASE+"esummary.fcgi?"+urllib.parse.urlencode({"db":"pubmed","id":",".join(ids),"retmode":"json"})
    res=get(u2).get("result",{})
    out=[]
    for i in ids:
        r=res.get(i,{})
        au=r.get("authors",[])
        a1=au[0]["name"] if au else "?"
        out.append(dict(pmid=i, title=r.get("title","")[:90], j=r.get("source",""),
                        y=(r.get("pubdate","") or "")[:4], vol=r.get("volume",""), pg=r.get("pages",""),
                        a1=a1, n_au=len(au)))
    return out

queries = {
 "TRIPOD+AI (Collins BMJ 2024)": "TRIPOD+AI statement Collins prediction machine learning",
 "FoodProX (Menichetti NatCommun 2023)": "Menichetti machine learning degree food processing",
 "NLP nutrient-profiling+extval (L'Abbe AJCN 2023)": "machine learning nutrient profiling food label text L'Abbe",
 "Nutri-Score 2023 update (Merz NatFood)": "Nutri-Score 2023 update algorithm",
 "JMIR micronutrient ML (2023)": "predicting unreported micronutrients food labels machine learning",
 "BFPD label nutrients ML (Ma 2021)": "machine learning estimating label nutrients branded food products database",
 "ML Nutri-Score (Tachie CRFS 2023)": "machine learning Nutri-Score prediction food",
 "Rule FVNL from ingredients (Dunford 2020)": "fruit vegetable nut legume content ingredient list nutrient profiling Dunford",
 "Nutri-Score effect on choices (Egnell)": "Nutri-Score front-of-pack label food choices randomized Egnell",
 "UPF cardiovascular cohort": "ultra-processed food cardiovascular disease prospective cohort",
 "Smartphone dietary self-monitoring apps": "smartphone applications dietary self-monitoring review",
}
for label, q in queries.items():
    print(f"\n### {label}\n  query: {q}")
    try:
        for r in search(q):
            print(f"  PMID {r['pmid']} | {r['a1']} (+{r['n_au']-1}) | {r['j']} {r['y']};{r['vol']}:{r['pg']}\n     {r['title']}")
    except Exception as e:
        print("  ERR", str(e)[:60])
    time.sleep(0.5)
