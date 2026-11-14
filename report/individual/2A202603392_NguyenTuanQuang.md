# Báo cáo Lab 07 · Agentic RAG

Nguyễn Tuấn Quang · 2A202603392 · L3A

## Dữ liệu và benchmark

- Dùng lại 297 chunk của chỉ mục B từ Lab 06, chia theo đoạn và câu với giới hạn 500 ký tự. Corpus gồm 28 trang vật lý của *A Survey of AI Agent Protocols* (arXiv:2504.16736v3, CC BY 4.0) và hai đơn vị MDX MCP Architecture, MCP Lifecycle tại commit `06e923405df3df242f1471b9300d9db90ebd10fd`. Nguồn và giấy phép đầy đủ nằm trong `data/manifest.json` của Lab 06.
- Embedding BAAI/bge-small-en-v1.5, 384 chiều, FastEmbed 0.9.1 chạy CPU với ONNX commit `aa8f8b060edb00e03bfdd08813a2949946c8ba55`. Dense tìm kiếm cosine chính xác trên PostgreSQL 16.16 và pgvector 0.8.7. Lab 07 đọc chỉ mục hiện có nên chi phí embedding tài liệu và nạp lại dữ liệu là 0. Bước khởi tạo dev mất khoảng 0,62 s.
- [Benchmark](../../data/questions.json) có 24 câu. Dev giữ 15 câu có đáp án của Lab 06 và thêm hai câu thiếu bằng chứng. Test có năm câu có đáp án và hai câu thiếu bằng chứng mới. Một câu test dùng chung nguồn MCP Lifecycle với dev nhưng hỏi điều kiện thương lượng phiên bản, khác câu dev về thứ tự Initialization. Các câu thiếu bằng chứng có ghi từ khóa đã kiểm tra trên toàn corpus và phần tài liệu liên quan.
- Hit@1, Evidence Hit@3 và Context Evidence Rate dùng cùng quy tắc tìm trích đoạn gold nguyên văn, đúng nguồn và trang. Mẫu số là số câu có đáp án. Chấm context riêng theo thang 0/1/2 để ghi nhận đoạn tương đương và kiểm tra từng điều kiện. Nhãn trong `reviews.json` do Codex đối chiếu câu trả lời và citation với nội dung trace.

## Retrieval và thử nghiệm trên dev

Mọi cấu hình dùng cùng corpus và cùng filter. Câu hỏi chứa đồng thời `official`, `mcp` và `specification` được giới hạn ở `document_type=specification`. Tool lấy câu hỏi gốc ở lượt đầu và dùng truy vấn model đề xuất ở lượt sau khi có. Agent và retriever chỉ nhận truy vấn và filter từ câu hỏi.

| Cấu hình | Phương pháp và giả thuyết | Top-k / budget / lượt tối đa |
|---|---|---|
| dense | Baseline cosine trên pgvector. | 3 / 2.000 ký tự / 1 |
| tfidf | Từ khóa theo token Unicode, TF-IDF cosine. Tên riêng và cụm thuật ngữ có thể tăng độ chính xác. | 3 / 2.000 ký tự / 1 |
| hybrid | Cải thiện 1. RRF với hệ số 60 và 12 ứng viên từ mỗi phương pháp để kết hợp độ tương đồng ngữ nghĩa và từ khóa. | 3 / 2.000 ký tự / 1 |
| hybrid-wide | Cải thiện 2. Mở rộng context lên sáu đoạn và cho phép tìm thêm một lượt khi bằng chứng thiếu. | 6 / 3.600 ký tự / 2 |

Thời gian là trung vị mỗi câu tính theo giây. Cột retrieval đo truy vấn gốc, có ảnh hưởng từ cache query embedding và sáu worker chạy đồng thời. Cột API là tổng chi phí cho cả split theo usage của OpenRouter.

| Cấu hình | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Retrieval / toàn lượt | API (USD) |
|---|---:|---:|---:|---:|---:|
| dense | 11/15 (73,3%) | 12/15 (80,0%) | 12/15 (80,0%) | 0,043 / 2,550 s | 0,007238 |
| tfidf | 9/15 (60,0%) | 12/15 (80,0%) | 12/15 (80,0%) | 0,002 / 2,474 s | 0,007056 |
| hybrid | 10/15 (66,7%) | 13/15 (86,7%) | 13/15 (86,7%) | 0,059 / 2,453 s | 0,006796 |
| hybrid-wide | 10/15 (66,7%) | 13/15 (86,7%) | 14/15 (93,3%) | 0,057 / 2,605 s | 0,009481 |

| Cấu hình dev | Tool use | Điểm câu trả lời 0/1/2 · TB /2 | Citation hợp lệ | Câu trả lời có citation | Từ chối đúng | Từ chối nhầm |
|---|---:|---:|---:|---:|---:|---:|
| dense | 17/17 | 7/0/8 · 1,07 | 8/10 | 9/9 | 1/2 | 7/15 |
| tfidf | 17/17 | 3/2/10 · 1,47 | 14/17 | 15/15 | 0/2 | 2/15 |
| hybrid | 17/17 | 3/2/10 · 1,47 | 12/13 | 12/12 | 2/2 | 3/15 |
| hybrid-wide | 17/17 | 7/0/8 · 1,07 | 9/10 | 8/8 | 2/2 | 7/15 |

Mỗi câu dev gọi retrieval một lần, kể cả hybrid-wide. Context trung bình lần lượt là 1.439, 1.413, 1.399 và 2.769 ký tự. Prompt / completion token lần lượt là 11.514 / 1.645, 11.508 / 1.533, 11.451 / 1.385 và 16.606 / 1.774. Lần chạy tích hợp đầu nhận HTTP 404 khi yêu cầu router kiểm tra toàn bộ tham số. Sau khi bỏ cờ định tuyến này, các cấu hình dev đều chạy thành công với cùng model.

### Lỗi dev và lựa chọn cấu hình

- **q14, thiếu bằng chứng về quan hệ 1:1.** Dense truy xuất các đoạn đúng loại tài liệu nhưng thiếu câu khẳng định mỗi client ứng với một server. TF-IDF cũng trượt và trả lời về thương lượng capability. Hybrid tìm `mcp-architecture:1:2` trong top-3 và trả lời đúng. Đây là trường hợp hai cách xếp hạng bổ sung cho nhau.
- **q05, đoạn gần chủ đề thiếu điều kiện.** Dense tìm đoạn trang 10 nêu tài nguyên có thể ở local hoặc remote. Hybrid top-3 dùng đoạn trang 9 chỉ nêu ba loại tài nguyên. Tăng top-k lên 6 đưa đoạn trang 10 vào context và khôi phục câu trả lời đầy đủ.
- **q03, có bằng chứng tương đương nhưng citation sai dạng.** Dense và hybrid-wide có đoạn trang 7 đủ hai trục và bốn nhóm. Model gộp ID trong một cặp ngoặc, có cả ID viết rút gọn. Bộ kiểm tra citation chỉ nhận từng `[chunk-id]`, nên cả hai câu bị từ chối. Hybrid top-3 chỉ nêu tên hai trục, được 1/2. Điều này giải thích vì sao tăng context có thể nâng tỷ lệ chứa evidence mà điểm câu trả lời vẫn giảm.

Chốt cấu hình theo thứ tự ưu tiên đã ghi trong [selection.json](../../results/selection.json). So sánh tỷ lệ câu có đáp án đạt 2 điểm, tỷ lệ từ chối đúng, Context Evidence Rate, Evidence Hit@3 rồi chi phí. Hybrid và TF-IDF hòa 10/15 câu đạt đủ điểm. Hybrid được chọn vì từ chối đúng 2/2 so với 0/2 của TF-IDF. Hybrid-wide đạt context tốt nhất nhưng chỉ có 8/15 câu đạt đủ điểm và tốn thêm 0,002684 USD so với hybrid.

## Agent và cách chấm

Agent dùng `openai/gpt-4.1-mini` qua OpenRouter, temperature 0. Lượt đầu model phải gọi tool `search`. Context giữ nguyên đoạn và nguồn, bỏ đoạn trùng ID, bỏ đoạn vượt budget. Nếu có lượt tìm tiếp, context xen kẽ ứng viên mới với ứng viên trước. Agent trả lời kèm ID trong context hoặc xuất `INSUFFICIENT_EVIDENCE`. Dạng citation sai được ghi lại cùng câu trả lời gốc và dẫn đến từ chối. Trace phân biệt lỗi API và lỗi truy xuất, lưu usage do provider báo.

Mỗi citation được kiểm tra theo claim mà đoạn trích hỗ trợ. Ví dụ ở q15, danh sách ba pha chỉ cho biết thứ tự. Khẳng định Initialization bắt buộc là tương tác đầu tiên cần đoạn có yêu cầu MUST. Xem [cách chạy](../../docs/day7-run.md) và [trace cùng nhãn dev](../../results/dev).

## Test sau khi chốt cấu hình

| Cấu hình | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Context 0/1/2 | Retrieval / toàn lượt | API (USD) |
|---|---:|---:|---:|---:|---:|---:|
| dense | 3/5 (60%) | 5/5 (100%) | 5/5 (100%) | 0/0/5 | 0,136 / 3,109 s | 0,002910 |
| hybrid | 3/5 (60%) | 5/5 (100%) | 5/5 (100%) | 0/0/5 | 0,070 / 2,386 s | 0,002852 |

| Cấu hình | Tool use | Số lượt | Điểm câu trả lời 0/1/2 · TB /2 | Citation hợp lệ | Câu trả lời có citation | Từ chối đúng | Từ chối nhầm |
|---|---:|---|---:|---:|---:|---:|---:|
| dense | 7/7 | 7 câu × 1 lượt | 2/0/3 · 1,20 | 3/3 | 3/3 | 2/2 | 2/5 |
| hybrid | 7/7 | 7 câu × 1 lượt | 2/0/3 · 1,20 | 4/4 | 3/3 | 2/2 | 2/5 |

Dense dùng 4.831 prompt token và 611 completion token, hybrid dùng 4.871 và 565. Context trung bình lần lượt là 1.441 và 1.453 ký tự. Hai cấu hình không gặp lỗi kết nối trên test. Dense chạy trước nên chịu thời gian tạo embedding cho các câu gốc, hybrid dùng lại cache. So sánh thời gian retrieval chịu ảnh hưởng của thứ tự chạy.

| Câu | Bằng chứng trong context của cả hai cấu hình | Kết quả đã chấm |
|---|---|---|
| t01 | `survey-v3:14:1` | Cả hai nêu đủ dữ liệu chuyến bay, hành khách và thanh toán. Context 2, câu trả lời 2. |
| t02 | `survey-v3:16:2` | Cả hai nêu đủ nghĩa của cognitive và normative alignment. Hybrid dẫn thêm `survey-v3:16:1` cho ý về minh bạch và kỳ vọng của con người. Context 2, câu trả lời 2. |
| t03 | `survey-v3:17:2` | Cả hai bị loại vì citation gộp. Nháp của hybrid nêu đúng ba thách thức. Nháp dense ưu tiên nhầm nhóm coordination, perception và spatial reasoning rồi mới nêu ba ý được hỏi. Context 2, câu trả lời 0. |
| t04 | `survey-v3:24:2` | Cả hai ghép đúng Windows/Chrome và macOS/Safari trong nháp. Câu cuối từ chối vì citation gộp có ID rút gọn. Context 2, câu trả lời 0. |
| t05 | `mcp-lifecycle:1:5` | Cả hai nêu đúng hai nhánh thương lượng phiên bản, kèm quy tắc ngắt kết nối nếu client không hỗ trợ phiên bản server trả về. Context 2, câu trả lời 2. |
| t06 | Corpus không nêu phí vận hành ANP. | Cả hai từ chối, không đưa giá tiền. |
| t07 | Các đoạn về HTTP shutdown và timeout không quy định khoảng thời gian retry. | Cả hai từ chối, không đưa số giây. |

[Trace và nhãn dense](../../results/test/dense) · [Trace và nhãn hybrid](../../results/test/hybrid)

Trên bộ test này, hai cấu hình cùng đạt 5/5 về context nhưng chỉ 3/5 về câu trả lời đầy đủ. Hai lỗi từ chối nhầm đều qua bước kiểm tra định dạng citation. Tập test nhỏ và mỗi cấu hình chỉ chạy một lần nên chưa đo được độ ổn định khi chạy lại. Chi phí API của 82 lượt đánh giá cấu hình–câu hỏi đã lưu là 0,0363332 USD. Phạm vi bài làm là phần cơ bản.
