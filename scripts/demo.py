"""Simulates a real citizen conversation against a running server."""
import sys, httpx

BASE = "http://127.0.0.1:8077"
V = {"likely_eligible":"LIKELY   ","possibly_eligible":"maybe    ",
     "unlikely":"no       ","excluded":"EXCLUDED "}

def show(turn, said, profile=None):
    r = httpx.post(f"{BASE}/api/assess",
                   json={"text": said, "profile": profile}, timeout=30)
    d = r.json()["assessment"]
    print(f"\n{'='*66}\nTURN {turn} — she says:\n  \"{said}\"")
    known = {k:v for k,v in d["applicant"].items() if v is not None}
    print(f"\n  understood: {known}")
    hits = [x for x in d["results"] if x["verdict"] in ("likely_eligible","possibly_eligible")]
    print(f"\n  {len(hits)} schemes still in play:")
    for x in hits:
        print(f"    {V[x['verdict']]} {x['name_en'][:52]}")
    if d["follow_up_questions_en"]:
        print(f"\n  it asks next (highest-yield first):")
        for q in d["follow_up_questions_en"][:2]:
            print(f"    -> {q}")
    return d["applicant"]

print("\n" + "#"*66)
print("#  URIMAI — live client walkthrough")
print("#  Persona: 65-year-old widow, rural Tamil Nadu, BPL ration card")
print("#"*66)

p = show(1, "எனக்கு 65 வயது, நான் விதவை")
p.update({"state":"TN","is_bpl":True})
p = show(2, "Yes I have a BPL ration card, I live in Tamil Nadu", p)
p.update({"area_type":"rural","owns_pucca_house":False,"has_lpg_connection":False})
p = show(3, "I live in a village, no concrete house, no gas connection", p)

print(f"\n{'='*66}\nFINAL — what she actually walks away with:\n")
r = httpx.post(f"{BASE}/api/assess", json={"text":"summary","profile":p}, timeout=30).json()
for x in r["assessment"]["results"]:
    if x["verdict"] == "likely_eligible":
        print(f"  * {x['name_en']}")
        print(f"      {x['benefit_en']}")
        print(f"      verify at: {x['verify_at_en']}\n")
print(f"  {r['disclaimer_en']}")
