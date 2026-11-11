#!/usr/bin/env python3
"""Tạo bảng Excel theo dõi + chấm gợi ý Bài N từ repo lớp (mỗi SV một thư mục "Họ tên - MSSV").

    python bang_theo_doi.py repo-lop --bai 1 --dung-han "2026-11-05 19:00" --han "2026-11-05 23:59" -o TheoDoi_Bai1.xlsx
Cần: git, Python 3, openpyxl.
"""
import argparse, io, re, subprocess, tarfile, tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
VN = timezone(timedelta(hours=7))
from pathlib import Path
from urllib.parse import quote
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.formatting.rule import CellIsRule

XANH, VANG, DO, XAM, NHAP = "C6EFCE", "FFEB9C", "FFC7CE", "EDEDED", "FFF7E0"
fill = lambda c: PatternFill("solid", fgColor=c)

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=off", *args],
                          capture_output=True, text=True, encoding="utf-8").stdout

def doc(p):
    try: return p.read_text(encoding="utf-8", errors="ignore")
    except Exception: return ""

def cham(bai, so_commit):
    """Trả về dict gợi ý điểm + ghi chú cho từng tiêu chí (GV sửa lại nếu cần)."""
    files = [p for p in bai.rglob("*") if p.is_file()] if bai else []
    rel = lambda p: p.relative_to(bai).as_posix().lower()
    pick = lambda f: [p for p in files if f(rel(p))]
    api_cs = pick(lambda x: "submission.api/" in x and x.endswith("program.cs") and "/obj/" not in x)
    cli_cs = pick(lambda x: "submission.client/" in x and x.endswith("program.cs") and "/obj/" not in x)
    api = "".join(doc(p) for p in api_cs); cli = "".join(doc(p) for p in cli_cs)
    http = "".join(doc(p) for p in pick(lambda x: x.endswith(".http")))
    md_bai = pick(lambda x: re.search(r"(^|/)bai0?\d\.md$", x))
    md_all = pick(lambda x: x.endswith(".md") and not x.endswith("readme.md")) or md_bai
    nhatky = "".join(doc(p) for p in md_all)
    r = {}
    # 1. Chạy được: không chạy thử tự động được -> chỉ kiểm tra đủ cấu trúc
    du_api = bool(re.search(r"Map(Get|Post)", api)); du_cli = "HttpClient" in cli
    r["chay"] = (None if du_api and du_cli else 0, "Đủ code API + Client, GV chạy thử" if du_api and du_cli else
                 "Thiếu " + ", ".join(n for n, ok in [("Submission.Api", du_api), ("Submission.Client", du_cli)] if not ok)
                 + (" (chỉ có project: " + ", ".join(sorted({p.parent.name for p in pick(lambda x: x.endswith(".csproj"))})) + ")"
                    if pick(lambda x: x.endswith(".csproj")) else ""))
    # 2. Kiểm thử requests.http: 200 (GET) / 201 (POST hợp lệ) / 400 (POST lỗi)
    n_get = len(re.findall(r"^\s*GET\s", http, re.M)); n_post = len(re.findall(r"^\s*POST\s", http, re.M))
    d = 2 if n_get >= 1 and n_post >= 2 else (1 if n_get + n_post else 0)
    r["test"] = (d, f"{n_get} GET, {n_post} POST" if http else "Không có requests.http")
    # 3. Thí nghiệm lỗi: bảng >= 4 dòng trong nhật ký
    dong = [l for l in nhatky.splitlines() if l.strip().startswith("|") and not re.match(r"^\s*\|[\s:|-]+\|\s*$", l)]
    n_tn = max(0, len(dong) - 1)
    r["loi"] = (2 if n_tn >= 4 else (1 if n_tn else 0), f"Bảng {n_tn} dòng, GV xem giải thích" if n_tn else "Không thấy bảng thí nghiệm")
    # 4. Bài mở rộng GET /api/submissions/{id}
    co_get_id = bool(re.search(r'MapGet\(\s*"/api/submissions/\{', api))
    co_404 = "NotFound" in api
    r["mr"] = (1 if co_get_id and co_404 else (0.5 if co_get_id else 0),
               "Có GET {id} + 404" if co_get_id and co_404 else ("Có GET {id}, thiếu 404" if co_get_id else "Chưa làm"))
    # 5. Git & nhật ký
    d = (0.5 if md_bai else 0) + (0.5 if so_commit >= 2 else 0)
    r["git"] = (d, f"{'có' if md_bai else 'thiếu'} docs/bai1.md, {so_commit} commit")
    r["rac"] = any("/bin/" in "/" + rel(p) or "/obj/" in "/" + rel(p) for p in files)
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo"); ap.add_argument("--bai", type=int, default=1)
    ap.add_argument("--dung-han", help='mốc nộp đúng hạn, vd "2026-11-05 19:00"')
    ap.add_argument("--han", help='hạn chót, vd "2026-11-05 23:59"')
    ap.add_argument("--url", default="https://github.com/PTUDPTK23/CNTTK23C")
    ap.add_argument("-o", "--out", default="TheoDoi.xlsx")
    ap.add_argument("--diem-gv", help="file CSV điểm GV nhập tay (MSSV + các cột điểm); ô trống = dùng điểm máy gợi ý")
    ap.add_argument("--chay-thu", help="file JSON kết quả chạy thử tự động (chay_thu.py): điền điểm Chạy được + Bài mở rộng")
    ap.add_argument("--cong-khai", action="store_true", help="bản đăng lên repo công khai: bỏ các cột điểm")
    a = ap.parse_args()
    repo = Path(a.repo)
    tg = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M") if s else None
    dung_han, han = tg(a.dung_han), tg(a.han)
    goc = set(git(repo, "rev-list", "--max-parents=0", "HEAD").split())

    commit_sv = defaultdict(list); sua_ho = defaultdict(set)
    for khoi in git(repo, "log", "--name-only", "--format=@@%H|%an|%aI|%s").split("@@")[1:]:
        dong = khoi.strip().splitlines()
        h, an, ad, msg = dong[0].split("|", 3)
        dirs = {p.split("/", 1)[0] for p in dong[1:] if "/" in p}
        if len(dirs) > 10: continue   # commit khởi tạo thư mục cả lớp
        for d in dirs: commit_sv[d].append((datetime.fromisoformat(ad).astimezone(VN).replace(tzinfo=None), an, msg))
        if len(dirs) > 1:
            for d in dirs: sua_ho[d].add(an)

    # Bài đã gửi Pull Request nhưng GV chưa gộp (đọc refs/pull/*/head qua git, không cần API)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin", "+refs/pull/*/head:refs/remotes/pr/*"],
                   capture_output=True)
    cho_gop = {}   # thư mục -> (số PR, thời gian, tài khoản, ref)
    for line in git(repo, "for-each-ref", "refs/remotes/pr", "--format=%(refname)|%(authorname)|%(authordate:iso-strict)").splitlines():
        ref, an, ad = line.split("|")
        if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", ref, "HEAD"]).returncode == 0:
            continue
        for f in git(repo, "diff", "--name-only", "--diff-filter=AM", "HEAD", ref).splitlines():
            if "/" in f:
                d = f.split("/", 1)[0]
                cho_gop[d] = (ref.rsplit("/", 1)[1], datetime.fromisoformat(ad).astimezone(VN).replace(tzinfo=None), an, ref)

    COT_DIEM = ["Chay_duoc_4", "Kiem_thu_2", "Thi_nghiem_loi_2", "Mo_rong_1", "Git_nhat_ky_1"]
    diem_gv = {}
    if a.diem_gv and Path(a.diem_gv).exists():
        import csv
        for r in csv.DictReader(open(a.diem_gv, encoding="utf-8-sig")):
            diem_gv[(r.get("MSSV") or "").strip().lower()] = r

    chay_thu = {}
    if a.chay_thu and Path(a.chay_thu).exists():
        import json
        try: chay_thu = json.load(open(a.chay_thu, encoding="utf-8"))
        except Exception: chay_thu = {}

    pat_bai = re.compile(rf"^(bai|baitap|bt|lab)[_-]?0?{a.bai}$", re.I)
    wb = Workbook(); ws = wb.active; ws.title = f"Bài {a.bai}"
    cot = ["STT", "MSSV", "Họ và tên", "Link", "Trạng thái nộp", "Commit cuối", "Số commit",
           "Chạy được (4)", "Kiểm thử (2)", "Thí nghiệm lỗi (2)", "Bài mở rộng (1)", "Git & nhật ký (1)",
           "Tổng (10)", "Ghi chú tự động", "Cảnh báo", "Ghi chú GV"]
    ws.append(cot)
    sv = []
    for d in (p for p in repo.iterdir() if p.is_dir() and " - " in p.name):
        ten, mssv = d.name.rsplit(" - ", 1); sv.append((ten.split()[-1], ten, mssv, d))
    sv.sort(key=lambda x: (x[0], x[1]))
    for i, (_, ten, mssv, d) in enumerate(sv, 1):
        tim = lambda dd: next((c for c in dd.iterdir() if c.is_dir() and pat_bai.match(c.name.replace(" ", ""))), None) \
            or (dd if any(p.name not in ("README.md", ".gitkeep") for p in dd.iterdir()) else None)
        bai = tim(d)
        cm = commit_sv.get(d.name, []); cuoi = max((t for t, _, _ in cm), default=None)
        pr = cho_gop.get(d.name) if not bai else None
        if pr:   # lấy bài từ Pull Request chưa gộp ra thư mục tạm để chấm
            tmp = Path(tempfile.mkdtemp())
            arch = subprocess.run(["git", "-C", str(repo), "archive", pr[3], "--", d.name], capture_output=True).stdout
            tarfile.open(fileobj=io.BytesIO(arch)).extractall(tmp, filter='data')
            bai = tim(tmp / d.name); cm = [(pr[1], pr[2], "PR")]; cuoi = pr[1]
        if not bai: tt = "Chưa nộp"
        elif cuoi and han and cuoi > han: tt = "Quá hạn"
        elif cuoi and dung_han and cuoi > dung_han: tt = "Muộn"
        else: tt = "Đúng hạn"
        r = cham(bai, len(cm)) if bai else None
        ct = chay_thu.get(mssv.lower())
        if r and ct:   # kết quả chạy thử thật: điểm Chạy được; Bài mở rộng chỉ thay khi API đã chạy được
            r["chay"] = (ct["chay"], ct["ghi_chay"])
            if ct.get("api_len"): r["mr"] = (ct["mr"], ct["ghi_mr"])
        canh = []
        if len({an for _, an, _ in cm}) > 1: canh.append("nhiều tài khoản nộp: " + ", ".join(sorted({an for _, an, _ in cm})))
        if sua_ho.get(d.name): canh.append("có commit sửa cả thư mục bạn khác")
        if r and r["rac"]: canh.append("nộp cả bin/obj")
        if pr: canh.append(f"CHỜ CÔ GỘP: Pull request #{pr[0]}")
        if cm and not bai: canh.append(f"có commit nhưng không có thư mục Bai{a.bai}")
        ghichu = " | ".join(f"{k}: {r[v][1]}" for k, v in
                            [("Chạy", "chay"), ("Test", "test"), ("Lỗi", "loi"), ("MR", "mr"), ("Git", "git")]) if r else ""
        n = ws.max_row + 1
        diem = [r[k][0] for k in ("chay", "test", "loi", "mr", "git")] if r else [0, 0, 0, 0, 0]
        gv = diem_gv.get(mssv.lower(), {})
        for k, cot_gv in enumerate(COT_DIEM):
            v = (gv.get(cot_gv) or "").strip().replace(",", ".")
            if v:
                try: diem[k] = float(v)
                except ValueError: pass
        ghi_gv = (gv.get("Ghi_chu") or "").strip()
        ws.append([i, mssv, ten, "Mở", tt, cuoi.strftime("%d/%m/%Y %H:%M") if cuoi else "", len(cm),
                   *diem, f"=SUM(H{n}:L{n})", ghichu, "; ".join(canh), ghi_gv])
        ws.cell(n, 4).hyperlink = f"{a.url}/tree/main/{quote(d.name)}"
        ws.cell(n, 4).font = Font(color="0563C1", underline="single")
        ws.cell(n, 5).fill = fill({"Đúng hạn": XANH, "Muộn": VANG, "Quá hạn": DO, "Chưa nộp": XAM}[tt])
        for c in range(8, 13): ws.cell(n, c).fill = fill(NHAP)
        if r and diem[0] is None: ws.cell(n, 8).fill = fill(VANG)
        if canh: ws.cell(n, 15).fill = fill(VANG)
    last = ws.max_row
    if a.diem_gv and not Path(a.diem_gv).exists():
        import csv
        with open(a.diem_gv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["MSSV", "Ho_ten", *COT_DIEM, "Ghi_chu"])
            for _, ten, mssv, _d in sv: w.writerow([mssv, ten, "", "", "", "", "", ""])
    ws.auto_filter.ref = f"A1:P{last}"
    vien = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
    for row in ws.iter_rows(min_row=1, max_row=last, max_col=16):
        for c in row: c.border = vien
    for c in ws[1]:
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.font = Font(bold=True, color="FFFFFF"); c.fill = fill("1F3864")
    ws.row_dimensions[1].height = 48
    for j, w in enumerate([5, 14, 22, 6, 11, 16, 8, 9, 9, 10, 10, 10, 8, 60, 30, 24], 1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = w
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=13):
        for c in row: c.alignment = Alignment(horizontal="center")
    for row in ws.iter_rows(min_row=2, min_col=14, max_col=15):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.conditional_formatting.add(f"M2:M{last}", CellIsRule(operator="greaterThanOrEqual", formula=["8"], fill=fill(XANH)))
    ws.conditional_formatting.add(f"M2:M{last}", CellIsRule(operator="lessThan", formula=["5"], fill=fill(DO)))
    ws.freeze_panes = "D2"

    th = wb.create_sheet("Tổng hợp")
    rg = f"'{ws.title}'!"
    th.append(["Chỉ số", "Số SV"])
    for nhan in ["Đúng hạn", "Muộn", "Quá hạn", "Chưa nộp"]:
        th.append([nhan, f'=COUNTIF({rg}E2:E{last},"{nhan}")'])
    th.append(["Có cảnh báo", f'=COUNTIF({rg}O2:O{last},"?*")'])
    th.append(["Điểm TB (người đã nộp)", f'=IFERROR(AVERAGEIF({rg}E2:E{last},"<>Chưa nộp",{rg}M2:M{last}),"")'])
    th.append(["Tổng SV", f"=COUNTA({rg}B2:B{last})"])
    th.append([])
    th.append(["Đúng hạn", f"Commit cuối trước {dung_han:%H:%M %d/%m/%Y}" if dung_han else ""])
    th.append(["Muộn", f"Từ {dung_han:%H:%M} đến {han:%H:%M %d/%m/%Y}" if dung_han and han else ""])
    th.append(["Quá hạn", f"Sau {han:%H:%M %d/%m/%Y}" if han else ""])
    th.append(["Cập nhật lúc", datetime.now(VN).strftime("%d/%m/%Y %H:%M")]); th.append(["Nguồn", a.url])
    th.column_dimensions["A"].width = 24; th.column_dimensions["B"].width = 50
    th["A1"].font = th["B1"].font = Font(bold=True)

    hd = wb.create_sheet("Cách chấm")
    hd.append(["Tiêu chí", "Yêu cầu", "Điểm", "Máy gợi ý thế nào"])
    for row in [
        ["Chạy được", "API và Client tự viết chạy ở 2 tiến trình, client in đúng kết quả", 4,
         "Máy tự chạy thử (chay_thu.py): build 2 project (1) + GET / và /api/assignments đúng (1) + POST hợp lệ 201 và POST sai 400 (1) + Client in danh sách, mã GUID, received (1). Không có kết quả chạy thử → ô tô vàng, GV chạy tay"],
        ["Kiểm thử", "requests.http có đủ các trường hợp 200 / 201 / 400", 2,
         "≥1 GET và ≥2 POST → 2; có request nhưng ít hơn → 1; không có file → 0"],
        ["Thí nghiệm lỗi", "Bảng 4 thí nghiệm có dự đoán, kết quả và giải thích đúng", 2,
         "Bảng trong nhật ký ≥4 dòng → 2; 1–3 dòng → 1. GV đọc lại phần giải thích"],
        ["Bài mở rộng", "GET /api/submissions/{id} với 200/404, client đọc lại lượt nộp", 1,
         "Chạy thật: GET {id} có thật → 200 (0,4) + id không có → 404 (0,4) + client đọc lại lượt nộp (0,2). Nếu API không chạy được thì xét theo code: có MapGet {id} và NotFound → 1; chỉ có GET → 0,5"],
        ["Git & nhật ký", "Commit rõ nghĩa, có tag bai1, docs/bai1.md đầy đủ", 1,
         "Có docs/bai1.md → 0,5; ≥2 commit → 0,5. (Repo chung nên không dùng tag bai1 riêng từng SV)"]]:
        hd.append(row)
    hd.append([]); hd.append(["Lưu ý", "Các ô điểm nền kem là điểm GỢI Ý, cô sửa trực tiếp; cột Tổng tự cộng lại."])
    hd.append(["", "Thời gian nộp lấy theo giờ commit trên máy SV; muốn chắc chắn có thể đối chiếu giờ push trên GitHub."])
    for j, w in enumerate([16, 60, 7, 70], 1): hd.column_dimensions["ABCD"[j-1]].width = w
    for row in hd.iter_rows():
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    for c in hd[1]: c.font = Font(bold=True)
    if a.cong_khai:
        wb = ban_cong_khai(ws, last, dung_han, han, a.url)
    wb.save(a.out); print(f"Đã ghi {a.out}: {last-1} sinh viên")

def ban_cong_khai(ws, last, dung_han, han, url):
    """Chỉ giữ thông tin nộp bài, không có điểm (để đăng công khai)."""
    giu = [1, 2, 3, 4, 5, 6, 7, 15]
    wb = Workbook(); w = wb.active; w.title = ws.title
    for r in range(1, last + 1):
        for j, c in enumerate(giu, 1):
            src, dst = ws.cell(r, c), w.cell(r, j)
            dst.value = src.value
            if src.hyperlink: dst.hyperlink = src.hyperlink.target; dst.font = Font(color="0563C1", underline="single")
            if src.fill and src.fill.fgColor and src.fill.fill_type: dst.fill = PatternFill("solid", fgColor=src.fill.fgColor.rgb)
            if r == 1: dst.font = Font(bold=True, color="FFFFFF"); dst.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
            elif j in (5, 6, 7): dst.alignment = Alignment(horizontal="center")
    for j, wd in enumerate([5, 14, 22, 6, 11, 16, 8, 45], 1):
        w.column_dimensions[w.cell(1, j).column_letter].width = wd
    w.row_dimensions[1].height = 36; w.freeze_panes = "D2"; w.auto_filter.ref = f"A1:H{last}"
    th = wb.create_sheet("Tổng hợp"); rg = f"'{w.title}'!E2:E{last}"
    th.append(["Trạng thái", "Số SV"])
    for nhan in ["Đúng hạn", "Muộn", "Quá hạn", "Chưa nộp"]:
        th.append([nhan, f'=COUNTIF({rg},"{nhan}")'])
    th.append([]); 
    if dung_han: th.append(["Đúng hạn", f"Trước {dung_han:%H:%M %d/%m/%Y}"])
    if han: th.append(["Hạn chót", f"{han:%H:%M %d/%m/%Y}"])
    th.append(["Cập nhật lúc", datetime.now(VN).strftime("%d/%m/%Y %H:%M")]); th.append(["Nguồn", url])
    th.column_dimensions["A"].width = 16; th.column_dimensions["B"].width = 45
    return wb

if __name__ == "__main__":
    main()
