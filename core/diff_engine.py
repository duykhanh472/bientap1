#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/diff_engine.py
-------------------
Bộ tổng hợp sai khác (Diff Engine) và quản lý tọa độ lỗi chuẩn sản xuất:
1. Xác định tọa độ ký tự chính xác (start, end) trực tiếp trên văn bản gốc.
2. Không xé vụn ký tự (bảo tồn trọn vẹn từ lỗi và cụm dấu câu).
3. Đóng gói danh sách DiffIssue chuẩn hóa gửi cho Web UI / API.
4. Áp dụng các quyết định duyệt lỗi (Apply Decisions) bằng kỹ thuật Reverse Patching.
"""

import html
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Đảm bảo đường dẫn gốc dự án luôn có trong sys.path khi chạy trực tiếp
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.normalizer import normalize_text
from core.spell_checker import SpellingIssue, get_spell_checker

# Các từ viết tắt thông dụng tránh viết hoa nhầm
ABBREVIATIONS = r'v\.v|th\.s|ts|gs|pgs|tr|sđd|tp|tt|bt|q|đ\/c'
ABBREV_WITH_DOT = rf'\b(?:{ABBREVIATIONS}|[A-ZÀ-ỸĐ])\.'

# Lời dẫn thoại ngoại lệ sau dấu ! hoặc ?
SPEECH_TAG_PRONOUNS = r'(?:tôi|hắn|nó|ông|bà|thị|chàng|nàng|người|chúng tôi)'
SPEECH_TAG_VERBS = r'(?:hỏi|đáp|bảo|nói|thưa|cười|nghĩ|kêu|la|than|thốt|rằng|tiếp)'
SPEECH_TAG_PATTERN = re.compile(
    rf'^{SPEECH_TAG_PRONOUNS}\s+{SPEECH_TAG_VERBS}\b',
    re.IGNORECASE
)

# Ký tự chữ cái tiếng Việt
VIET_LOWER = r'[a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]'


@dataclass
class DiffIssue:
    """Đối tượng biểu diễn một điểm khác biệt / lỗi cần người dùng duyệt."""
    id: str                  # Mã định danh duy nhất (vd: "iss_1", "iss_2")
    category: str            # 'TYPOGRAPHY' | 'CAPITALIZATION' | 'OCR_SPLIT' | 'TYPO_OCR'
    start: int               # Tọa độ bắt đầu trên văn bản gốc
    end: int                 # Tọa độ kết thúc trên văn bản gốc
    original: str            # Đoạn văn bản gốc
    replacement: str         # Đề xuất sửa đổi mặc định
    suggestions: List[str]   # Danh sách các từ gợi ý thay thế
    explanation: str         # Diễn giải nguyên nhân sửa
    rule: str                # Mã định danh quy tắc
    confidence: float        # Độ tin cậy (0.0 đến 1.0)


@dataclass
class DiffResult:
    """Kết quả hoàn chỉnh sau khi quét toàn bộ văn bản."""
    original_text: str       # Văn bản gốc đã qua chuẩn hóa cơ sở
    proposed_text: str       # Văn bản hoàn thiện nếu chấp nhận toàn bộ đề xuất
    issues: List[DiffIssue]  # Danh sách toàn bộ các lỗi phát hiện được
    annotated_html: str      # Văn bản được bao bọc thẻ HTML highlight phục vụ Web UI
    stats: Dict[str, int]    # Thống kê số lượng lỗi theo từng danh mục


class DiffEngine:
    """
    Hệ thống phân tích sai khác và tổng hợp lỗi trực tiếp trên văn bản.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.spell_checker = get_spell_checker()

    def analyze_text(self, raw_text: str) -> DiffResult:
        """
        Thực thi phân tích toàn diện trực tiếp trên văn bản cơ sở:
        1. Chuẩn hóa Unicode NFC và dọn rác ẩn.
        2. Bóc tách lỗi chính tả & dính chữ với tọa độ thực.
        3. Bóc tách lỗi Typography & Viết hoa thành từng cụm nguyên vẹn.
        4. Hợp nhất, sắp xếp và sinh bản đề xuất hoàn chỉnh.
        """
        if not raw_text:
            return DiffResult("", "", [], "", {})

        # Bước 1: Chuẩn hóa kỹ thuật cơ sở (Unicode NFC, ngắt dòng)
        base_text = normalize_text(raw_text)

        issues: List[DiffIssue] = []
        issue_counter = 1
        occupied_spans: List[Tuple[int, int]] = []

        # -------------------------------------------------------------
        # BƯỚC 2: QUÉT LỖI CHÍNH TẢ & DÍNH CHỮ TRỰC TIẾP TRÊN BASE_TEXT
        # (Đảm bảo 100% tọa độ start/end khớp tuyệt đối với bản gốc)
        # -------------------------------------------------------------
        spelling_issues = self.spell_checker.check_document(base_text)
        for sp in spelling_issues:
            best_sug = sp.suggestions[0] if sp.suggestions else sp.original
            issues.append(DiffIssue(
                id=f"iss_{issue_counter}",
                category=sp.issue_type,
                start=sp.start,
                end=sp.end,
                original=sp.original,
                replacement=best_sug,
                suggestions=sp.suggestions,
                explanation=sp.reason,
                rule=sp.issue_type,
                confidence=sp.confidence
            ))
            occupied_spans.append((sp.start, sp.end))
            issue_counter += 1

        # -------------------------------------------------------------
        # BƯỚC 3: QUÉT LỖI TYPOGRAPHY & VIẾT HOA THEO CỤM NGUYÊN VẸN
        # -------------------------------------------------------------

        # 3.1 Gạch đầu dòng hội thoại: - hoặc – -> —
        for m in re.finditer(r'(?m)^[ \t]*([-–—]{1,2})[ \t]+', base_text):
            # Bỏ qua nếu là đường kẻ ngang phân cách Markdown (--- hoặc ***)
            line = base_text[m.start():base_text.find('\n', m.start()) if '\n' in base_text[m.start():] else len(base_text)]
            if re.match(r'^([-*_]\s*){3,}$', line.strip()):
                continue

            if m.group(0) != "— ":
                s, e = m.start(), m.end()
                if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                    issues.append(DiffIssue(
                        id=f"iss_{issue_counter}",
                        category="TYPOGRAPHY",
                        start=s,
                        end=e,
                        original=m.group(0),
                        replacement="— ",
                        suggestions=["— "],
                        explanation="Chuẩn hóa gạch đầu dòng thoại thành Em-dash (—)",
                        rule="DIALOGUE_EM_DASH",
                        confidence=0.98
                    ))
                    occupied_spans.append((s, e))
                    issue_counter += 1

        # 3.2 Viết hoa sau gạch đầu dòng thoại
        for m in re.finditer(rf'(?m)^[ \t]*[-–—]{{1,2}}[ \t]+({VIET_LOWER})', base_text):
            s, e = m.start(1), m.end(1)
            if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                issues.append(DiffIssue(
                    id=f"iss_{issue_counter}",
                    category="CAPITALIZATION",
                    start=s,
                    end=e,
                    original=m.group(1),
                    replacement=m.group(1).upper(),
                    suggestions=[m.group(1).upper()],
                    explanation="Viết hoa chữ cái đầu tiên sau gạch thoại",
                    rule="DIALOGUE_CAPITALIZATION",
                    confidence=0.95
                ))
                occupied_spans.append((s, e))
                issue_counter += 1

        # 3.3 Khoảng trắng quanh dấu phẩy: bắt trọn cụm ' ,' hoặc ',b' -> chuẩn hóa thành ', '
        for m in re.finditer(r'[ \t]*,[ \t]*(?=[^\d\)\],;:!?\"\'”»\n])', base_text):
            if m.group(0) != ", ":
                s, e = m.start(), m.end()
                if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                    issues.append(DiffIssue(
                        id=f"iss_{issue_counter}",
                        category="TYPOGRAPHY",
                        start=s,
                        end=e,
                        original=m.group(0),
                        replacement=", ",
                        suggestions=[", "],
                        explanation="Chuẩn hóa khoảng trắng quanh dấu phẩy",
                        rule="COMMA_SPACING",
                        confidence=0.98
                    ))
                    occupied_spans.append((s, e))
                    issue_counter += 1

        # 3.4 Khoảng trắng thừa trước các dấu câu khác (; : ! ?)
        for m in re.finditer(r'[ \t]+([;:!?])', base_text):
            s, e = m.start(), m.end()
            if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                issues.append(DiffIssue(
                    id=f"iss_{issue_counter}",
                    category="TYPOGRAPHY",
                    start=s,
                    end=e,
                    original=m.group(0),
                    replacement=m.group(1),
                    suggestions=[m.group(1)],
                    explanation=f"Xóa khoảng trắng thừa trước dấu {m.group(1)}",
                    rule="PUNCTUATION_SPACING",
                    confidence=0.98
                ))
                occupied_spans.append((s, e))
                issue_counter += 1

        # 3.5 Khoảng trắng thừa trước dấu chấm câu (.)
        for m in re.finditer(r'[ \t]+(?<!\.)\.(?!\.)', base_text):
            s, e = m.start(), m.end()
            if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                issues.append(DiffIssue(
                    id=f"iss_{issue_counter}",
                    category="TYPOGRAPHY",
                    start=s,
                    end=e,
                    original=m.group(0),
                    replacement=".",
                    suggestions=["."],
                    explanation="Xóa khoảng trắng thừa trước dấu chấm câu",
                    rule="PERIOD_SPACING",
                    confidence=0.98
                ))
                occupied_spans.append((s, e))
                issue_counter += 1

        # 3.6 Viết hoa đầu dòng / đầu đoạn văn
        for m in re.finditer(rf'(?m)^({VIET_LOWER})', base_text):
            s, e = m.start(1), m.end(1)
            if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                issues.append(DiffIssue(
                    id=f"iss_{issue_counter}",
                    category="CAPITALIZATION",
                    start=s,
                    end=e,
                    original=m.group(1),
                    replacement=m.group(1).upper(),
                    suggestions=[m.group(1).upper()],
                    explanation="Viết hoa chữ cái đầu đoạn văn",
                    rule="PARAGRAPH_CAPITALIZATION",
                    confidence=0.95
                ))
                occupied_spans.append((s, e))
                issue_counter += 1

        # 3.7 Viết hoa sau dấu kết thúc câu (., !, ?, ...)
        sent_end_re = re.compile(
            rf'({ABBREV_WITH_DOT})|(\.{{3}}|[\.!\?])(["”»\)]*)(\s+)({VIET_LOWER})'
        )
        for m in sent_end_re.finditer(base_text):
            # Nếu là từ viết tắt -> bỏ qua
            if m.group(1):
                continue

            punct = m.group(2)
            following_char = m.group(5)
            s, e = m.start(5), m.end(5)

            # Ngoại lệ: Lời dẫn thoại sau ! hoặc ? (vd: "? tôi hỏi")
            if punct in ('!', '?') and SPEECH_TAG_PATTERN.match(base_text[s:]):
                continue

            if not any(not (e <= start or s >= end) for start, end in occupied_spans):
                issues.append(DiffIssue(
                    id=f"iss_{issue_counter}",
                    category="CAPITALIZATION",
                    start=s,
                    end=e,
                    original=following_char,
                    replacement=following_char.upper(),
                    suggestions=[following_char.upper()],
                    explanation="Viết hoa sau dấu kết thúc câu",
                    rule="SENTENCE_CAPITALIZATION",
                    confidence=0.95
                ))
                occupied_spans.append((s, e))
                issue_counter += 1

        # Sắp xếp các issue tăng dần theo tọa độ bắt đầu
        issues.sort(key=lambda x: x.start)

        # -------------------------------------------------------------
        # BƯỚC 4: SINH BẢN ĐỀ XUẤT HOÀN THIỆN & HTML HIGHLIGHT
        # -------------------------------------------------------------
        all_accepted_decisions = {iss.id: iss.replacement for iss in issues}
        proposed_text = self.apply_decisions(base_text, issues, all_accepted_decisions)
        annotated_html = self._generate_annotated_html(base_text, issues)
        stats = self._compute_stats(issues)

        return DiffResult(
            original_text=base_text,
            proposed_text=proposed_text,
            issues=issues,
            annotated_html=annotated_html,
            stats=stats
        )

    def _generate_annotated_html(self, text: str, issues: List[DiffIssue]) -> str:
        """Sinh chuỗi HTML có gắn các thẻ <mark> highlight phân loại màu cho Web UI."""
        if not text:
            return ""

        parts: List[str] = []
        last_idx = 0

        for iss in issues:
            if iss.start > last_idx:
                parts.append(html.escape(text[last_idx:iss.start]))

            escaped_orig = html.escape(iss.original)
            escaped_repl = html.escape(iss.replacement)
            escaped_expl = html.escape(iss.explanation)
            cat_lower = iss.category.lower()

            mark_tag = (
                f'<mark class="diff-issue diff-{cat_lower}" '
                f'data-id="{iss.id}" '
                f'data-repl="{escaped_repl}" '
                f'title="{escaped_expl}">'
                f'{escaped_orig}'
                f'</mark>'
            )
            parts.append(mark_tag)
            last_idx = iss.end

        if last_idx < len(text):
            parts.append(html.escape(text[last_idx:]))

        return "".join(parts)

    def _compute_stats(self, issues: List[DiffIssue]) -> Dict[str, int]:
        """Tổng hợp số lượng lỗi theo từng nhóm."""
        stats: Dict[str, int] = {
            "TOTAL": len(issues),
            "TYPOGRAPHY": 0,
            "CAPITALIZATION": 0,
            "OCR_SPLIT": 0,
            "TYPO_OCR": 0
        }
        for iss in issues:
            stats[iss.category] = stats.get(iss.category, 0) + 1
        return stats

    @classmethod
    def apply_decisions(
        cls,
        original_text: str,
        issues: List[DiffIssue],
        decisions: Dict[str, str]
    ) -> str:
        """
        Áp dụng các lựa chọn của người dùng vào văn bản gốc:
        - decisions: Từ điển mapping {issue_id: từ_thay_thế_được_chọn}
        - Kỹ thuật: Reverse Patching (áp dụng từ cuối lên đầu để không bao giờ lệch offset).
        """
        if not original_text or not issues:
            return original_text

        issue_map = {iss.id: iss for iss in issues}

        valid_patches = []
        for iss_id, chosen_repl in decisions.items():
            if chosen_repl == "__IGNORE__":
                continue
            if iss_id in issue_map:
                iss = issue_map[iss_id]
                valid_patches.append((iss.start, iss.end, chosen_repl))

        # Sắp xếp giảm dần theo tọa độ start
        valid_patches.sort(key=lambda p: p[0], reverse=True)

        patched_text = original_text
        for start, end, repl in valid_patches:
            patched_text = patched_text[:start] + repl + patched_text[end:]

        return patched_text


# Module-level API tiện ích
_global_engine: Optional[DiffEngine] = None


def get_diff_engine() -> DiffEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = DiffEngine()
    return _global_engine


def analyze_document(text: str) -> DiffResult:
    return get_diff_engine().analyze_text(text)


def apply_document_decisions(original_text: str, issues: List[DiffIssue], decisions: Dict[str, str]) -> str:
    return DiffEngine.apply_decisions(original_text, issues, decisions)


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 68)
    print(" CORE/DIFF_ENGINE: KIỂM THỬ TỔNG HỢP SAI KHÁC VÀ TOẠ ĐỘ LỖI")
    print("=" * 68)

    sample_doc = (
        "# Chương I: Cuộc Gặp Gỡ\n\n"
        "- chào bác ,bác đi đâu đấy ? tôi hỏi .\n"
        "Hắn nhìn tôi với vẻ mặt **nghi ngại**, tronglòng dường như có điều gì giấu giếm.\n"
        "Bức tranh này rất đep, do một ngưòi thợ xưa vẽ lại ở dinh Gia Định.\n"
        "hôm nay trời quang mây tạnh, việc quốc-gia coi như đã định."
    )

    print("-> Văn bản kiểm thử ban đầu:")
    print("-" * 50)
    print(sample_doc)
    print("-" * 50)

    engine = DiffEngine()
    result = engine.analyze_text(sample_doc)

    print(f"\n-> Phân tích hoàn tất! Phát hiện {result.stats['TOTAL']} vấn đề:")
    for cat, count in result.stats.items():
        if cat != "TOTAL" and count > 0:
            print(f"   • {cat:<15}: {count} lỗi")

    print("\n-> Chi tiết các Issue phát hiện được:")
    for iss in result.issues:
        print(f"  [{iss.id}] [{iss.category:<14}] [{iss.start:>2}:{iss.end:<2}] "
              f"'{iss.original}' -> '{iss.replacement}' ({iss.explanation})")

    # Kiểm tra tính toàn vẹn của tọa độ (Slicing verification)
    print("\n-> Kiểm tra tính chính xác của tọa độ ký tự:")
    for iss in result.issues:
        extracted = result.original_text[iss.start:iss.end]
        assert extracted == iss.original, f"Lệch tọa độ: {extracted!r} != {iss.original!r}"
    print("  ✓ 100% tọa độ start:end khớp chính xác với lát cắt văn bản gốc!")

    # Giả lập người dùng duyệt lỗi trên Web
    decisions = {}
    for iss in result.issues:
        decisions[iss.id] = iss.suggestions[0] if iss.suggestions else iss.replacement

    final_text = engine.apply_decisions(result.original_text, result.issues, decisions)

    print("\n-> Văn bản sau khi áp dụng toàn bộ quyết định (Reverse Patching):")
    print("-" * 50)
    print(final_text)
    print("-" * 50)

    # Xác thực các tiêu chuẩn cốt lõi:
    assert "# Chương I:" in final_text, "Lỗi: Làm hỏng tiêu đề Markdown!"
    assert "**nghi ngại**" in final_text, "Lỗi: Làm hỏng thẻ in đậm Markdown!"
    assert "— Chào bác," in final_text, "Lỗi: Chưa sửa gạch thoại Em-dash!"
    assert "tôi hỏi." in final_text, "Lỗi: Viết hoa nhầm lời dẫn thoại!"
    assert "trong lòng" in final_text, "Lỗi: Chưa tách dính chữ 'tronglòng'!"
    assert "rất đẹp," in final_text, "Lỗi: Chưa sửa lỗi chính tả 'đep'!"
    assert "người thợ" in final_text, "Lỗi: Chưa sửa lỗi dấu OCR 'ngưòi'!"
    assert "Hôm nay" in final_text, "Lỗi: Chưa viết hoa đầu câu 'hôm nay'!"
    assert "quốc-gia" in final_text, "Lỗi: Làm mất dấu gạch nối lịch sử 'quốc-gia'!"
    assert "dinh Gia Định" in final_text, "Lỗi: Đụng chạm vào địa danh 'dinh Gia Định'!"

    print("\n[THÀNH CÔNG] Module core/diff_engine.py đã vượt qua toàn bộ các bài test!")
