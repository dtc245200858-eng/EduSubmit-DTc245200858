# Bảng theo dõi nộp bài

- **Bảng Excel** (tình trạng nộp + điểm): ở nhánh `bang-theo-doi`
  → https://github.com/PTUDPTK23/CNTTK23E/tree/bang-theo-doi (bấm vào file `TheoDoi_BaiN.xlsx` → nút tải xuống).
  GitHub tự tạo bảng một lần sau hạn chót (00:05 ngày 12/11/2026). Muốn tạo lại bất cứ lúc nào (sau khi gộp thêm bài, nhập điểm...):
  tab **Actions** → *Bang theo doi nop bai* → **Run workflow**. Bài gửi Pull Request chưa gộp cũng được tính ("CHỜ CÔ GỘP").
  Trước khi tạo bảng, máy **tự chạy thử bài của từng sinh viên** theo đặc tả Bài 1 (build, chạy API, gọi GET/POST 200–201–400–404, chạy Client) để chấm ô "Chạy được" và "Bài mở rộng".
  Khi bấm Run workflow có thể bỏ tích *chay_thu* để ra bảng ngay (chỉ chấm tĩnh); để tích thì mất vài chục phút.
- **`DiemGV_BaiN.csv`** (thư mục này): giảng viên nhập điểm tại đây (bấm vào file → bút chì → sửa → Commit changes).
  Ô trống = dùng điểm máy gợi ý. Cột `Chay_duoc_4` máy không chấm được, giảng viên nhập sau khi chạy thử.

Điểm máy gợi ý chỉ là tham khảo; điểm chính thức là điểm giảng viên nhập.
