#!/usr/bin/env python3
"""Chạy thử TỰ ĐỘNG bài của từng SV theo đặc tả Bài 1 (Submission.Api + Submission.Client).

    python chay_thu.py repo-lop --bai 1 -o ketqua_chay.json

Với mỗi SV (bài ở nhánh main hoặc trong Pull Request chưa gộp):
  1. dotnet build Submission.Api và Submission.Client
  2. chạy API ở cổng riêng, gọi: GET /, GET /api/assignments, POST hợp lệ (201), POST sai (400),
     GET /api/submissions/{id} (200 / 404 - bài mở rộng)
  3. chạy Client, kiểm tra in ra danh sách bài tập, mã lượt nộp (GUID), trạng thái received
Điểm "Chạy được" (4) = build (1) + GET đúng (1) + POST 201/400 đúng (1) + client in đúng (1).
Điểm "Bài mở rộng" (1) = GET {id} 200 (0,4) + 404 (0,4) + client đọc lại lượt nộp (0,2).

AN TOÀN: code SV là code không tin cậy. Chạy trong job riêng quyền chỉ-đọc, không có secret;
mỗi SV được chép ra thư mục tạm, có giới hạn thời gian, tiến trình bị diệt sau khi chạy.
Chỉ cần Python 3 (thư viện chuẩn), git và .NET SDK 10.
"""
import argparse, io, json, os, re, shutil, signal, socket, subprocess, tarfile, tempfile, time, urllib.error, urllib.request, uuid
from pathlib import Path

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # không đi qua proxy


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=off", *args],
                          capture_output=True, text=True, encoding="utf-8").stdout


def moi_truong(home):
    """Môi trường tối thiểu cho code SV: bỏ mọi biến có vẻ là bí mật."""
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"TOKEN|SECRET|PASSWORD|KEY|CREDENTIAL", k, re.I) and not k.startswith(("GITHUB_", "RUNNER_", "ACTIONS_"))}
    env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
               DOTNET_CLI_HOME=str(home), NUGET_PACKAGES=os.environ.get("NUGET_PACKAGES", str(Path.home() / ".nuget/packages")))
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"): env.pop(k, None)
    return env


def chay(cmd, cwd, env, timeout):
    """Chạy lệnh, hết giờ thì diệt cả nhóm tiến trình. Trả (mã thoát hoặc None nếu quá giờ, đầu ra)."""
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="ignore", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        diet(p)
        out = p.communicate()[0] if p.stdout else ""
        return None, out


def diet(p):
    try: os.killpg(p.pid, signal.SIGKILL)
    except Exception: pass


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    try:
        with OPENER.open(req, timeout=10) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, {}, str(e)


def jload(text):
    try: return json.loads(text)
    except Exception: return None


def lay(d, key):
    """Lấy khóa JSON không phân biệt hoa/thường."""
    if isinstance(d, dict):
        for k, v in d.items():
            if k.lower() == key.lower(): return v
    return None


def cong_mo(port, tien_trinh, cho=45):
    t0 = time.time()
    while time.time() - t0 < cho and tien_trinh.poll() is None:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close(); return True
        except OSError: time.sleep(0.5)
    return False


def tim_csproj(goc):
    ds = [p for p in goc.rglob("*.csproj") if not {"bin", "obj"} & set(p.relative_to(goc).parts)]
    ds.sort(key=lambda p: len(p.parts))
    api = next((p for p in ds if "submission.api" in p.name.lower()), None)
    cli = next((p for p in ds if "submission.client" in p.name.lower()), None)
    if not api:   # dự phòng: project web
        api = next((p for p in ds if "Microsoft.NET.Sdk.Web" in p.read_text(encoding="utf-8", errors="ignore") and p != cli), None)
    if not cli:
        cli = next((p for p in ds if p != api and "Microsoft.NET.Sdk.Web" not in p.read_text(encoding="utf-8", errors="ignore")), None)
    return api, cli


def cham_chay(goc, port, env):
    """Chạy thử một bài. Trả dict điểm + ghi chú."""
    kq = {"chay": 0.0, "mr": 0.0, "api_len": False, "ghi_chay": "", "ghi_mr": ""}
    api, cli = tim_csproj(goc)
    ghi = []
    if not api or not cli:
        kq["ghi_chay"] = "Không tìm thấy " + " và ".join(n for n, p in [("Submission.Api.csproj", api), ("Submission.Client.csproj", cli)] if not p)
        return kq
    # 1. Build
    ok_build = True
    for ten, cs in (("Api", api), ("Client", cli)):
        rc, out = chay(["dotnet", "build", str(cs), "-c", "Debug", "--nologo", "-v", "q"], cs.parent, env, 300)
        if rc != 0:
            ok_build = False
            loi = next((l.strip() for l in out.splitlines() if "error" in l.lower()), "quá giờ" if rc is None else "lỗi build")
            ghi.append(f"build {ten} LỖI ({loi[:90]})")
    if ok_build:
        kq["chay"] += 1; ghi.append("build OK")
    if not ok_build:   # build lỗi thì không chạy (tránh chạy nhầm bin/obj SV lỡ nộp lên)
        kq["ghi_chay"] = "; ".join(ghi); return kq
    # 2. Chạy API
    url = f"http://127.0.0.1:{port}"
    p = subprocess.Popen(["dotnet", "run", "--no-build", "--project", str(api), "--urls", url], cwd=api.parent, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        if not cong_mo(port, p):
            ghi.append(f"API không mở cổng {port} (code có thể cố định cổng/URL)")
            kq["ghi_chay"] = "; ".join(ghi); return kq
        kq["api_len"] = True
        # GET / và /api/assignments
        s1, _, b1 = http("GET", url + "/")
        j1 = jload(b1)
        ok1 = s1 == 200 and lay(j1, "service") is not None and lay(j1, "status") is not None
        s2, _, b2 = http("GET", url + "/api/assignments")
        j2 = jload(b2)
        ok2 = (s2 == 200 and isinstance(j2, list) and len(j2) >= 2
               and all(lay(x, "id") is not None and lay(x, "title") is not None and lay(x, "description") is not None for x in j2))
        if ok1 and ok2: kq["chay"] += 1
        ghi.append("GET /" + (" ok" if ok1 else f" sai({s1})") + ", GET /api/assignments" + (" ok" if ok2 else f" sai({s2})"))
        # POST hợp lệ -> 201
        hop_le = {"assignmentId": 1, "studentCode": "SV001", "repositoryUrl": "https://github.com/sv001/EduSubmit"}
        s3, h3, b3 = http("POST", url + "/api/submissions", hop_le)
        j3 = jload(b3); sub_id = lay(j3, "id")
        ok3 = (s3 == 201 and "location" in h3 and isinstance(sub_id, str) and GUID.fullmatch(sub_id) is not None
               and str(lay(j3, "status")).lower() == "received")
        s4, _, _ = http("POST", url + "/api/submissions", {**hop_le, "studentCode": ""})
        s5, _, _ = http("POST", url + "/api/submissions", {**hop_le, "assignmentId": 0})
        ok4 = s4 == 400 and s5 == 400
        if ok3 and ok4: kq["chay"] += 1
        ghi.append("POST hợp lệ " + ("201 ok" if ok3 else f"sai({s3}{'' if 'location' in h3 else ', thiếu Location'})")
                   + ", POST lỗi " + ("400 ok" if ok4 else f"sai({s4}/{s5})"))
        # Bài mở rộng: GET {id}
        mr = 0.0; ghi_mr = []
        if isinstance(sub_id, str):
            sa, _, ba = http("GET", f"{url}/api/submissions/{sub_id}")
            if sa == 200 and str(lay(jload(ba), "id")).lower() == sub_id.lower(): mr += 0.4; ghi_mr.append("GET{id} 200 ok")
            else: ghi_mr.append(f"GET{{id}} có thật → {sa}")
        else: ghi_mr.append("không có id để thử GET{id}")
        sb, _, _ = http("GET", f"{url}/api/submissions/{uuid.uuid4()}")
        if sb == 404: mr += 0.4; ghi_mr.append("404 ok")
        else: ghi_mr.append(f"GET{{id}} không có → {sb} (cần 404)")
        # 3. Client
        rc, out = chay(["dotnet", "run", "--no-build", "--project", str(cli), "--", url], cli.parent, env, 90)
        guids = GUID.findall(out)
        ok_cli = rc == 0 and len(guids) >= 1 and "received" in out.lower() and len(re.findall(r"^\s*-?\s*\d+\s*[:\-]", out, re.M)) >= 2
        if ok_cli: kq["chay"] += 1
        ghi.append("Client " + ("in đúng" if ok_cli else ("quá giờ" if rc is None else f"chưa đúng (mã thoát {rc}, {len(guids)} GUID)")))
        if ok_cli and len(guids) >= 2: mr += 0.2; ghi_mr.append("client đọc lại lượt nộp")
        elif ok_cli: ghi_mr.append("client chưa đọc lại lượt nộp")
        kq["mr"] = round(mr, 1); kq["ghi_mr"] = ", ".join(ghi_mr)
    finally:
        diet(p)
    kq["ghi_chay"] = "; ".join(ghi)
    return kq


def tim_bai(d, bai):
    pat = re.compile(rf"^(bai|baitap|bt|lab)[_-]?0?{bai}$", re.I)
    return next((c for c in d.iterdir() if c.is_dir() and pat.match(c.name.replace(" ", ""))), None) \
        or (d if any(p.name not in ("README.md", ".gitkeep") for p in d.iterdir()) else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo"); ap.add_argument("--bai", type=int, default=1)
    ap.add_argument("--port-goc", type=int, default=5100)
    ap.add_argument("-o", "--out", default="ketqua_chay.json")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin", "+refs/pull/*/head:refs/remotes/pr/*"], capture_output=True)
    cho_gop = {}   # thư mục -> ref PR
    for line in git(repo, "for-each-ref", "refs/remotes/pr", "--format=%(refname)").splitlines():
        ref = line.strip()
        if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", ref, "HEAD"]).returncode == 0: continue
        for f in git(repo, "diff", "--name-only", "--diff-filter=AM", "HEAD", ref).splitlines():
            if "/" in f: cho_gop[f.split("/", 1)[0]] = ref

    work = Path(tempfile.mkdtemp(prefix="chaythu_"))
    env = moi_truong(work / "home"); (work / "home").mkdir()
    ket_qua = {}
    sv = sorted(p for p in repo.iterdir() if p.is_dir() and " - " in p.name)
    for i, d in enumerate(sv):
        mssv = d.name.rsplit(" - ", 1)[1].lower()
        dich = work / mssv
        if tim_bai(d, a.bai):
            shutil.copytree(d, dich, ignore=shutil.ignore_patterns(".git"))
        elif d.name in cho_gop:
            dich.mkdir()
            arch = subprocess.run(["git", "-C", str(repo), "archive", cho_gop[d.name], "--", d.name], capture_output=True).stdout
            with tarfile.open(fileobj=io.BytesIO(arch)) as t: t.extractall(work / f"_{mssv}", filter="data")
            shutil.copytree(work / f"_{mssv}" / d.name, dich, dirs_exist_ok=True)
        else:
            continue
        goc = tim_bai(dich, a.bai) or dich
        print(f"[{i+1}/{len(sv)}] {d.name}", flush=True)
        try:
            ket_qua[mssv] = cham_chay(goc, a.port_goc + i, env)
        except Exception as e:   # một bài lỗi không làm hỏng cả lượt chấm
            ket_qua[mssv] = {"chay": 0.0, "mr": 0.0, "api_len": False, "ghi_chay": f"Lỗi chạy thử: {type(e).__name__}", "ghi_mr": ""}
        print("   ", ket_qua[mssv]["chay"], ket_qua[mssv]["ghi_chay"], flush=True)
        shutil.rmtree(dich, ignore_errors=True)
    Path(a.out).write_text(json.dumps(ket_qua, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã chạy thử {len(ket_qua)} bài -> {a.out}")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
