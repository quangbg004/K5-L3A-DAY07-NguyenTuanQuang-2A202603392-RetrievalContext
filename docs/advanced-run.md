# Chạy phần nâng cao Lab 07

Tài liệu gốc là World Bank. 2024. *World Development Report 2024: The Middle-Income Trap*. Washington, DC: World Bank. DOI 10.1596/978-1-4648-2078-6. Trang bản quyền PDF số 6 nêu giấy phép CC BY 3.0 IGO và lưu ý riêng cho thành phần bên thứ ba. Repo lưu câu hỏi, vị trí evidence và kết quả kiểm tra. Tải PDF từ nguồn chính thức hoặc dùng bản đã chuẩn bị. Đối chiếu SHA-256 với manifest trong `results/advanced/dev/run.json`. [Trang của World Bank](https://www.worldbank.org/en/publication/wdr2024)

Phần nghiên cứu này chuyển một số nội dung sang dữ liệu trích xuất phục vụ truy xuất.

> This is an adaptation of an original work by The World Bank. Views and opinions expressed in the adaptation are the sole responsibility of the author or authors of the adaptation and are not endorsed by The World Bank.

## Chuẩn bị và chạy

Dùng Python 3.11 trở lên và `ANTHROPIC_API_KEY` trong biến môi trường hoặc trong `starter/.env`. Phần nâng cao gọi Anthropic Messages API trực tiếp bằng `claude-haiku-5-5`. Model hỗ trợ ảnh và có giá tiêu chuẩn 0,10 USD mỗi triệu token đầu vào, 0,50 USD mỗi triệu token đầu ra với prompt dưới 100.000 token. Chi phí trong trace là ước tính từ số token thực tế và bảng giá. Chỉ các ảnh trang nguồn công khai được truy xuất mới đi vào request. [Thông tin model và đơn giá](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

```powershell
python -m pip install -r starter/advanced-requirements.txt
$pdf = Resolve-Path '../World Development Report 2024.pdf'
$idx = 'tmp/pdfs/wdr-index.json'
$out = 'results-advanced-reproduction'
python starter/advanced_pdf.py --pdf $pdf --index $idx
python starter/advanced.py dev --pdf $pdf --index $idx --output $out --env-file starter/.env
# Đọc bản gốc và điền reviews.json cho từng cấu hình dev.
python starter/advanced.py select --output $out
python starter/advanced.py test --pdf $pdf --index $idx --output $out --env-file starter/.env
# Đọc bản gốc và điền reviews.json cho toàn bộ test.
python starter/advanced.py review-test --output $out
```

`reviews.json` là mảng các object có `id`, `pass` kiểu boolean và `reason`. Với câu có đáp án, kiểm tra đủ câu trả lời, điều kiện, đơn vị, citation và vùng nguồn. Với câu thiếu bằng chứng, kiểm tra phản hồi thực sự từ chối và có trích dẫn rỗng. Lỗi chạy được tính vào mẫu số. Dùng nhãn tương ứng với trace của lần chạy đang chấm. [Benchmark nâng cao](../data/advanced/benchmark.json)

`select` dùng số câu dev đạt rồi chi phí để chọn cấu hình, ghi lại hash benchmark và hash index. `test` dùng cấu hình đã chốt và cùng chỉ mục. Để xem ảnh bằng chứng, mở PDF ở số trang `page` của citation ví dụ `p201`, rồi đối chiếu nhãn trang in `label` và vùng trong `locations` của câu hỏi. `image_sent` đánh dấu trang đã được render cho model. Chỉ mục lưu lớp văn bản và số hiệu caption. Tool `search_report` ưu tiên số hiệu nêu trong câu hỏi, dựa thêm vào TF-IDF để tìm các đoạn văn và trang liên quan.

Nếu đang tiếp tục một lần chạy bị gián đoạn, giữ cùng PDF, tệp index và thư mục kết quả. Thêm `--retry-errors` để chỉ thử lại các lỗi hệ thống theo cấu hình đã chốt. Trace giữ lần thử trước trong `prior_attempts`. Sau đó cập nhật các nhãn tương ứng và chạy lại `review-test`.

Kết quả Haiku 5.5 mặc định được lưu ở `results/advanced-haiku`. Kết quả Nemotron và lần thử GPT-4o mini trước đó nằm ở `results/advanced` và `results/advanced-gpt4o-mini`.
