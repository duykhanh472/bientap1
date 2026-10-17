#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server/app.py
-------------
FastAPI Backend Server cho VietLit-Proofreader:
- POST /api/scan      : Tiếp nhận văn bản Markdown, chạy DiffEngine và trả về danh sách Issue + Tọa độ.
- POST /api/apply     : Tiếp nhận các quyết định duyệt lỗi, thực thi Reverse Patching và xuất Markdown sạch.
- POST /api/whitelist : Thêm từ mới vào data/whitelist.txt để miễn kiểm tra chính tả.
- GET  /api/whitelist : Lấy danh sách toàn bộ từ đã được đưa vào Whitelist.
- POST /api/upload    : Tải tệp .md từ máy tính lên để đọc nội dung.
"""

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

# Đảm bảo đường dẫn gốc dự án luôn có trong sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.diff_engine import DiffEngine, DiffIssue, DiffResult, get_diff_engine
from core.spell_checker import get_spell_checker

# Khởi tạo FastAPI App
app = FastAPI(
    title="VietLit-Proofreader API",
    description="Hệ thống soát lỗi chính tả và quy chuẩn sắp chữ văn học chữ Quốc ngữ (1880–1975)",
    version="1.0.0"
)

# Cho phép CORS để thuận tiện debug giao diện
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thư mục chứa giao diện tĩnh (HTML/CSS/JS)
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==============================================================================
# PYDANTIC SCHEMAS (Định dạng dữ liệu vào / ra)
# ==============================================================================

class ScanRequest(BaseModel):
    text: str = Field(..., description="Nội dung văn bản Markdown cần soát lỗi")


class IssueModel(BaseModel):
    id: str
    category: str
    start: int
    end: int
    original: str
    replacement: str
    suggestions: List[str]
    explanation: str
    rule: str
    confidence: float


class ScanResponse(BaseModel):
    original_text: str
    proposed_text: str
    issues: List[IssueModel]
    annotated_html: str
    stats: Dict[str, int]


class ApplyRequest(BaseModel):
    original_text: str = Field(..., description="Văn bản gốc ban đầu")
    issues: List[IssueModel] = Field(..., description="Danh sách các Issue do /api/scan trả về")
    decisions: Dict[str, str] = Field(
        ...,
        description="Từ điển quyết định: {issue_id: từ_thay_thế}. Nếu giá trị là '__IGNORE__' sẽ giữ nguyên gốc."
    )


class ApplyResponse(BaseModel):
    result: str
    applied_count: int
    ignored_count: int


class WhitelistRequest(BaseModel):
    word: str = Field(..., description="Từ hoặc cụm từ cần thêm vào danh sách bỏ qua")


class WhitelistResponse(BaseModel):
    success: bool
    word: str
    message: str


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/")
async def root():
    """Phục vụ file giao diện chính index.html khi truy cập trang chủ."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "online",
        "message": "VietLit-Proofreader API đang chạy. Giao diện Web UI sẽ xuất hiện tại đây ở Giai đoạn 5.",
        "docs": "/docs"
    }


@app.post("/api/scan", response_model=ScanResponse)
async def scan_markdown(payload: ScanRequest):
    """
    [POST /api/scan]
    Nhận chuỗi Markdown, phân tích toàn diện và trả về:
    - Danh sách Issues kèm tọa độ start/end chính xác trên văn bản gốc.
    - Bản text đề xuất (proposed_text) nếu chấp nhận toàn bộ đề xuất.
    - Bản mã HTML gắn thẻ <mark> highlight phân loại màu cho Web UI.
    - Thống kê số lượng lỗi theo từng nhóm.
    """
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản đầu vào không được để trống.")

    engine = get_diff_engine()
    result: DiffResult = engine.analyze_text(payload.text)

    # Chuyển đổi các dataclass DiffIssue thành danh sách Pydantic IssueModel
    issues_data = [IssueModel(**asdict(iss)) for iss in result.issues]

    return ScanResponse(
        original_text=result.original_text,
        proposed_text=result.proposed_text,
        issues=issues_data,
        annotated_html=result.annotated_html,
        stats=result.stats
    )


@app.post("/api/apply", response_model=ApplyResponse)
async def apply_fixes(payload: ApplyRequest):
    """
    [POST /api/apply]
    Nhận văn bản gốc kèm từ điển quyết định duyệt lỗi {issue_id: chosen_replacement}.
    Áp dụng kỹ thuật Reverse Patching để xuất ra tệp Markdown hoàn chỉnh mà không lệch tọa độ.
    """
    engine = get_diff_engine()

    # Chuyển đổi các Pydantic IssueModel thành DiffIssue dataclass
    diff_issues = [
        DiffIssue(
            id=iss.id,
            category=iss.category,
            start=iss.start,
            end=iss.end,
            original=iss.original,
            replacement=iss.replacement,
            suggestions=iss.suggestions,
            explanation=iss.explanation,
            rule=iss.rule,
            confidence=iss.confidence
        )
        for iss in payload.issues
    ]

    # Thực thi vá lỗi ngược từ dưới lên trên
    final_text = engine.apply_decisions(
        original_text=payload.original_text,
        issues=diff_issues,
        decisions=payload.decisions
    )

    applied = sum(1 for v in payload.decisions.values() if v != "__IGNORE__")
    ignored = sum(1 for v in payload.decisions.values() if v == "__IGNORE__")

    return ApplyResponse(
        result=final_text,
        applied_count=applied,
        ignored_count=ignored
    )


@app.post("/api/whitelist", response_model=WhitelistResponse)
async def add_to_whitelist(payload: WhitelistRequest):
    """
    [POST /api/whitelist]
    Ghi một từ mới vào tệp data/whitelist.txt và cập nhật bộ nhớ đệm RAM.
    Từ này sẽ lập tức được miễn kiểm tra lỗi chính tả trong toàn bộ phiên làm việc.
    """
    word_to_add = payload.word.strip()
    if not word_to_add:
        raise HTTPException(status_code=400, detail="Từ cần thêm vào Whitelist không được để trống.")

    checker = get_spell_checker()
    added = checker.add_to_whitelist(word_to_add)

    if added:
        msg = f"Đã thêm '{word_to_add}' vào từ điển Whitelist thành công."
    else:
        msg = f"Từ '{word_to_add}' đã tồn tại trong Whitelist từ trước."

    return WhitelistResponse(
        success=True,
        word=word_to_add,
        message=msg
    )


@app.get("/api/whitelist")
async def get_whitelist_entries():
    """Lấy danh sách toàn bộ các từ hiện đang có trong Whitelist."""
    checker = get_spell_checker()
    return {
        "total": len(checker.whitelist),
        "whitelist": sorted(list(checker.whitelist))
    }


@app.post("/api/upload")
async def upload_markdown_file(file: UploadFile = File(...)):
    """Tiện ích tải trực tiếp tệp .md từ máy tính lên để lấy nội dung văn bản thô."""
    if not file.filename.lower().endswith(('.md', '.txt', '.markdown')):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp định dạng .md hoặc .txt")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        # Dự phòng trường hợp mã hóa khác UTF-8
        text = content.decode("utf-8-sig", errors="ignore")

    return {
        "filename": file.filename,
        "size_bytes": len(content),
        "text": text
    }


if __name__ == "__main__":
    import uvicorn
    print("=" * 68)
    print(" KHỞI CHẠY VIETLIT-PROOFREADER FASTAPI SERVER")
    print(" Địa chỉ truy cập: http://127.0.0.1:8000")
    print(" Tài liệu API Swagger: http://127.0.0.1:8000/docs")
    print("=" * 68)
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=True)
