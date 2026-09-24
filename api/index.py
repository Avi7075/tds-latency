from fastapi import FastAPI, Request
from fastapi.responses import Response
import io, re, traceback
from contextlib import redirect_stdout
from pydantic import BaseModel
import csv, urllib.request
from fastapi import Query

app = FastAPI()

@app.middleware("http")
async def cors(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# (latency_ms, uptime_pct) per region, from q-vercel-latency.json
DATA = {
    "apac": [(147.28, 98.279), (200.89, 99.086), (183.77, 98.557), (136.78, 99.038), (173.3, 97.143), (226.16, 97.804),
             (165.82, 98.519), (208.73, 99.176), (109.6, 99.477), (217.71, 98.546), (129.52, 97.387), (169.58, 97.236)],
    "emea": [(141.28, 99.273), (156.85, 97.515), (127.37, 98.525), (217.5, 97.285), (134.42, 98.978), (141.25, 98.353),
             (170.55, 98.975), (172.56, 98.332), (142.13, 99.028), (155.91, 98.835), (207.08, 98.839), (159.22, 97.465)],
    "amer": [(161.16, 99.106), (206.49, 98.273), (216.76, 98.99), (231.11, 98.421), (161.71, 97.699), (209.54, 99.223),
             (129.45, 98.965), (146.25, 97.237), (168.49, 97.191), (181, 98.376), (148.42, 97.162), (139.91, 98.733)],
}

def p95(values):
    s = sorted(values)
    pos = (len(s) - 1) * 0.95
    lo = int(pos)
    return s[lo] + (pos - lo) * (s[lo + 1] - s[lo]) if lo + 1 < len(s) else s[lo]

@app.post("/")
@app.post("/api/latency")
async def latency(request: Request):
    body = await request.json()
    threshold = body.get("threshold_ms", 180)
    out = []
    for region in body.get("regions", []):
        rows = DATA.get(region, [])
        lat = [r[0] for r in rows]
        up = [r[1] for r in rows]
        out.append({
            "region": region,
            "avg_latency": round(sum(lat) / len(lat), 2),
            "p95_latency": round(p95(lat), 2),
            "avg_uptime": round(sum(up) / len(up), 3),
            "breaches": sum(1 for x in lat if x > threshold),
        })
    return {"regions": out}

class CodeRequest(BaseModel):
    code: str

def execute_python_code(code: str) -> dict:
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(code, {"__name__": "__main__"})
        return {"success": True, "output": buf.getvalue()}
    except BaseException:
        return {"success": False, "output": traceback.format_exc()}

def error_lines(tb: str) -> list[int]:
    lines = re.findall(r'File "<string>", line (\d+)', tb)
    return [int(lines[-1])] if lines else []

@app.post("/code-interpreter")
def code_interpreter(req: CodeRequest):
    res = execute_python_code(req.code)
    if res["success"]:
        return {"error": [], "result": res["output"]}
    return {"error": error_lines(res["output"]), "result": res["output"]}

CSV_URL = "https://raw.githubusercontent.com/Avi7075/tds-latency/main/api/q-fastapi.csv"
_students = None

def load_students():
    global _students
    if _students is None:
        text = urllib.request.urlopen(CSV_URL).read().decode("utf-8-sig")
        _students = [{"studentId": int(r["studentId"]), "class": r["class"]}
                     for r in csv.DictReader(text.splitlines())]
    return _students

@app.get("/api")
def get_students(class_: list[str] | None = Query(None, alias="class")):
    students = load_students()
    if not class_:
        return {"students": students}
    wanted = set(class_)
    return {"students": [s for s in students if s["class"] in wanted]}
