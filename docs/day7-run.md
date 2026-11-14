# Chạy lại bài Lab 07

Lab 07 dùng trực tiếp chỉ mục B của Lab 06. Corpus gồm các trang vật lý 3–30 của *A Survey of AI Agent Protocols* v3 (CC BY 4.0), cùng MCP Architecture và MCP Lifecycle ở snapshot 2025-03-26. Xem `data/manifest.json` trong Lab 06 để lấy đúng phiên bản, nguồn và giấy phép.

## Chuẩn bị

1. Đặt hai repo cạnh nhau. Làm theo `starter/README.md` trong Lab 06 để chuẩn bị corpus, môi trường Python và pgvector. Nếu bảng `day06_protocol_chunks` đã có 297 chunk ở strategy B, khởi động lại container bằng `docker compose -p day6_student_starter up -d --wait` từ `starter/` của Lab 06. Với database mới, chạy ingestion Lab 06 để tạo chỉ mục.
2. Đặt `DATABASE_URL` và `OPENROUTER_API_KEY` trong môi trường hoặc trong `starter/.env` của Lab 06. Biến môi trường có quyền ưu tiên. Agent dùng `openai/gpt-4.1-mini` qua OpenRouter. Các đoạn trích công khai trong context được gửi tới model qua API.

## Benchmark

Chạy từ gốc Lab 07 bằng PowerShell. Chọn thư mục kết quả mới cho mỗi lần thí nghiệm.

```powershell
$lab6 = Resolve-Path '..\K5-L3A-DAY06-NguyenTuanQuang-2A202603392-DataIngestion'
$python = Join-Path $lab6 'starter\.venv\Scripts\python.exe'
& $python -m unittest discover -s tests -v
& $python starter/day7.py dev --day6 $lab6 --output results-reproduction
```

Đọc trace và đối chiếu câu trả lời với bằng chứng. Đặt `reviews.json` cạnh mỗi `traces.json` theo mẫu trong [kết quả dev](../results/dev). Mỗi câu có đáp án cần `context_grade` và `answer_grade` từ 0 đến 2. Với câu thiếu bằng chứng, ghi `abstention_correct`. Ghi `citation_support` theo thứ tự citation, kèm lý do. Giữ nhãn ở lần chạy đã chấm vì câu trả lời model có thể thay đổi giữa các lần chạy.

```powershell
& $python starter/day7.py select --output results-reproduction
& $python starter/day7.py test --day6 $lab6 --output results-reproduction
# Đọc và chấm test, sau đó tổng hợp.
& $python starter/day7.py review-test --output results-reproduction
```

`select` ghi cấu hình chốt vào `selection.json`. Lần chạy test dùng dense và cấu hình đã chọn, đồng thời kiểm tra hash benchmark và fingerprint của chỉ mục. Trace chứa xếp hạng top-3 theo câu hỏi gốc, tool call, kết quả, context, câu trả lời, citation, thời gian và usage do OpenRouter báo. Chi phí tính bằng USD. `context_hit` kiểm tra đoạn gold nguyên văn và đúng nguồn/trang. Nhãn `context_grade` đánh giá cả đoạn diễn đạt tương đương và các điều kiện của câu hỏi.

Tool calling dùng [Chat Completions của OpenRouter](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).
