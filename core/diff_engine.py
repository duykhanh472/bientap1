#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/diff_engine.py
-------------------
Bộ tổng hợp sai khác (Diff Engine) và quản lý tọa độ lỗi:
1. Tích hợp Normalizer -> MarkdownGuard -> Typography -> SpellChecker thành pipeline duy nhất.
2. Xác định tọa độ ký tự chính xác (start, end) của từng lỗi trên văn bản gốc.
3. Đóng gói danh sách DiffIssue chuẩn hóa gửi cho Web UI / API.
4. Áp dụng các quyết định duyệt lỗi (Apply Decisions) an toàn tuyệt đối bằng kỹ thuật Reverse Patching.
"""

import difflib
import html
import os
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Đảm bảo đường dẫn gốc dự án luôn có trong sys.path khi chạy trực tiếp
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.markdown_guard import MarkdownGuard
from core.normalizer import normalize_text
from core.spell_checker import SpellingIssue, get_spell_checker
from core.typography import standardize_typography


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
    Hệ thống phân tích sai khác và tổng hợp lỗi xuyên suốt toàn bộ các tầng.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.guard = MarkdownGuard()
        self.spell_checker = get_spell_checker()

    def analyze_text(self, raw_text: str) -> DiffResult:
        """
        Thực thi toàn bộ Pipeline kiểm định trên văn bản và trả về DiffResult:
        1. Chuẩn hóa cơ sở (Unicode NFC, ngắt dòng).
        2. Che chắn cú pháp Markdown.
        3. Dò lỗi chính tả và dính chữ (SpellChecker).
        4. Dò lỗi định dạng và viết hoa (Typography).
        5. So khớp tính toán tọa độ và gắn thẻ HTML.
        """
        if not raw_text:
            return DiffResult("", "", [], "", {})

        # Bước 1: Chuẩn hóa kỹ thuật cơ sở
        base_text = normalize_text(raw_text)

        # Bước 2: Bảo vệ cú pháp Markdown bằng Masking
        masked_text, mask_map = self.guard.mask(base_text)

        # Bước 3: Dò lỗi chính tả & dính chữ trên phần chữ lộ ra
        spelling_issues = self.spell_checker.check_document(masked_text)

        # Tạo bản văn bản tạm thời đã thay thế các lỗi chính tả được đề xuất cao nhất
        spell_fixed_masked = masked_text
        for sp in sorted(spelling_issues, key=lambda x: x.start, reverse=True):
            if sp.suggestions:
                best_sug = sp.suggestions[0]
                spell_fixed_masked = (
                    spell_fixed_masked[:sp.start] + best_sug + spell_fixed_masked[sp.end:]
                )

        # Bước 4: Chạy toàn bộ quy tắc Typography & Viết hoa
        fully_fixed_masked = standardize_typography(spell_fixed_masked)

        # Bước 5: Hoàn trả lại các thẻ Markdown ban đầu
        proposed_clean_text = self.guard.unmask(fully_fixed_masked, mask_map)

        # Bước 6: So khớp bằng SequenceMatcher giữa base_text và proposed_clean_text
        # để trích xuất tọa độ ký tự chính xác trên văn bản gốc
        issues = self._compute_diff_issues(base_text, proposed_clean_text, spelling_issues)

        # Bước 7: Sinh văn bản HTML highlight và thống kê
        annotated_html = self._generate_annotated_html(base_text, issues)
        stats = self._compute_stats(issues)

        return DiffResult(
            original_text=base_text,
            proposed_text=proposed_clean_text,
            issues=issues,
            annotated_html=annotated_html,
            stats=stats
        )

    def _compute_diff_issues(
        self,
        original_text: str,
        proposed_text: str,
        spelling_issues: List[SpellingIssue]
    ) -> List[DiffIssue]:
        """Tính toán và phân loại các điểm khác biệt giữa bản gốc và bản đề xuất."""
        matcher = difflib.SequenceMatcher(None, original_text, proposed_text, autojunk=False)
        diff_issues: List[DiffIssue] = []
        issue_counter = 1

        # 1. Đưa toàn bộ các lỗi từ vựng (Spell & Split) vào danh sách trước với tọa độ nguyên vẹn
        occupied_spans: List[Tuple[int, int]] = []
        for sp in spelling_issues:
            best_sug = sp.suggestions[0] if sp.suggestions else sp.original
            diff_issues.append(DiffIssue(
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

        # 2. Quét các sai khác định dạng/typography bằng SequenceMatcher nhưng bỏ qua vùng của lỗi từ vựng
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue

            # Nếu vùng diff này nằm trong hoặc giao với từ bị bắt lỗi chính tả -> Đã xử lý ở trên, bỏ qua
            if any(not (i2 <= start or i1 >= end) for start, end in occupied_spans):
                continue

            orig_chunk = original_text[i1:i2]
            repl_chunk = proposed_text[j1:j2]

            # Phân loại lỗi viết hoa vs lỗi khoảng trắng/dấu câu
            if orig_chunk.strip().lower() == repl_chunk.strip().lower() and orig_chunk != repl_chunk:
                category = "CAPITALIZATION"
                explanation = "Tự động viết hoa sau dấu kết thúc câu hoặc đầu dòng thoại"
                rule_name = "SENTENCE_CAPITALIZATION"
            elif orig_chunk.startswith(("-", "–")) and repl_chunk.startswith("—"):
                category = "TYPOGRAPHY"
                explanation = "Chuẩn hóa gạch đầu dòng thoại thành Em-dash (—)"
                rule_name = "DIALOGUE_EM_DASH"
            else:
                category = "TYPOGRAPHY"
                explanation = "Chuẩn hóa khoảng trắng quanh dấu câu và trích dẫn"
                rule_name = "PUNCTUATION_SPACING"

            diff_issues.append(DiffIssue(
                id=f"iss_{issue_counter}",
                category=category,
                start=i1,
                end=i2,
                original=orig_chunk,
                replacement=repl_chunk,
                suggestions=[repl_chunk],
                explanation=explanation,
                rule=rule_name,
                confidence=0.95
            ))
            issue_counter += 1

        # Sắp xếp toàn bộ issue theo thứ tự xuất hiện trong văn bản
        diff_issues.sort(key=lambda x: x.start)
        return diff_issues

    def _generate_annotated_html(self, text: str, issues: List[DiffIssue]) -> str:
        """Sinh chuỗi HTML có gắn các thẻ <mark> highlight phân loại màu cho Web UI."""
        if not text:
            return ""

        parts: List[str] = []
        last_idx = 0

        for iss in issues:
            # Đoạn văn bản bình thường trước lỗi
            if iss.start > last_idx:
                parts.append(html.escape(text[last_idx:iss.start]))

            # Thẻ highlight cho lỗi
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

        # Đoạn văn bản còn lại ở cuối
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
          Nếu issue_id không có trong decisions hoặc giá trị là '__IGNORE__' -> Giữ nguyên gốc.
        - Kỹ thuật: Reverse Patching (áp dụng từ cuối lên đầu để không lệch offset).
        """
        if not original_text or not issues:
            return original_text

        issue_map = {iss.id: iss for iss in issues}

        # Lọc ra các issue được người dùng đồng ý sửa
        valid_patches = []
        for iss_id, chosen_repl in decisions.items():
            if chosen_repl == "__IGNORE__":
                continue
            if iss_id in issue_map:
                iss = issue_map[iss_id]
                valid_patches.append((iss.start, iss.end, chosen_repl))

        # Sắp xếp theo chiều giảm dần của tọa độ start (áp dụng từ dưới lên trên)
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

    # Giả lập người dùng duyệt lỗi trên Web:
    # - Đồng ý sửa toàn bộ lỗi Typography và Viết hoa
    # - Đồng ý sửa dính chữ 'tronglòng' -> 'trong lòng'
    # - Chọn từ 'người' cho 'ngưòi'
    # - Chọn từ 'đẹp' cho 'đep'
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

