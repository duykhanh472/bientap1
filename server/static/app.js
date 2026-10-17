/**
 * server/static/app.js
 * --------------------
 * Điều khiển giao diện Web UI cho VietLit-Proofreader (Vanilla JS):
 * - Kết nối API /api/scan, /api/apply, /api/whitelist.
 * - Điều hướng phím tắt siêu tốc (J, K, Enter, X, W).
 * - Cuộn đồng bộ 2 cột (Synchronized Scrolling).
 * - Quản lý Popover duyệt lỗi và xuất file Markdown sạch.
 */

(() => {
    'use strict';

    // =========================================================================
    // 1. TRẠNG THÁI ỨNG DỤNG (APPLICATION STATE)
    // =========================================================================
    const state = {
        originalText: '',
        proposedText: '',
        issues: [],             // Danh sách các đối tượng IssueModel từ Backend
        issueMap: new Map(),    // Map tra cứu nhanh: id -> IssueModel
        decisions: {},          // { issue_id: chosen_replacement hoặc "__IGNORE__" }
        activeIssueIndex: -1,   // Chỉ số lỗi đang được chọn (active target)
        fileName: 'chuong_sach.md',
        isSyncingScroll: false, // Cờ chống lặp vô hạn khi cuộn đồng bộ
    };

    // =========================================================================
    // 2. CÁC THÀNH PHẦN DOM (DOM ELEMENTS)
    // =========================================================================
    const dom = {
        // Nút bấm & Tệp
        fileInput: document.getElementById('fileInput'),
        btnUpload: document.getElementById('btnUpload'),
        btnNewText: document.getElementById('btnNewText'),
        currentFileName: document.getElementById('currentFileName'),
        btnQuickAcceptTypo: document.getElementById('btnQuickAcceptTypo'),
        btnExport: document.getElementById('btnExport'),

        // Thống kê
        statTotal: document.getElementById('statTotal'),
        statTypo: document.getElementById('statTypo'),
        statCase: document.getElementById('statCase'),
        statSplit: document.getElementById('statSplit'),
        statOcr: document.getElementById('statOcr'),

        // 2 Cột hiển thị
        leftContent: document.getElementById('leftContent'),
        leftCharCount: document.getElementById('leftCharCount'),
        rightContent: document.getElementById('rightContent'),
        rightStatus: document.getElementById('rightStatus'),

        // Điều hướng đáy trang
        btnPrevIssue: document.getElementById('btnPrevIssue'),
        btnNextIssue: document.getElementById('btnNextIssue'),
        issueProgress: document.getElementById('issueProgress'),

        // Popover
        popover: document.getElementById('issuePopover'),
        popoverCategory: document.getElementById('popoverCategory'),
        popoverId: document.getElementById('popoverId'),
        popoverCloseBtn: document.getElementById('btnPopoverClose'),
        popoverOriginal: document.getElementById('popoverOriginal'),
        popoverReplacement: document.getElementById('popoverReplacement'),
        popoverExplanation: document.getElementById('popoverExplanation'),
        popoverSugContainer: document.getElementById('popoverSuggestionsContainer'),
        popoverSugList: document.getElementById('popoverSuggestionsList'),
        btnPopoverAccept: document.getElementById('btnPopoverAccept'),
        btnPopoverIgnore: document.getElementById('btnPopoverIgnore'),
        btnPopoverWhitelist: document.getElementById('btnPopoverWhitelist'),

        // Modal nhập text
        textModal: document.getElementById('textInputModal'),
        rawTextInput: document.getElementById('rawTextInput'),
        btnModalClose: document.getElementById('btnModalClose'),
        btnModalCancel: document.getElementById('btnModalCancel'),
        btnModalStartScan: document.getElementById('btnModalStartScan'),
    };

    // =========================================================================
    // 3. KHỞI TẠO ỨNG DỤNG & LẮNG NGHE SỰ KIỆN
    // =========================================================================
    function init() {
        bindEvents();
        setupSynchronizedScrolling();
        loadFromLocalStorage();
    }

    function bindEvents() {
        // 1. Quản lý tải tệp và nhập văn bản
        dom.btnUpload.addEventListener('click', () => dom.fileInput.click());
        dom.fileInput.addEventListener('change', handleFileUpload);
        dom.btnNewText.addEventListener('click', openTextModal);
        dom.btnModalClose.addEventListener('click', closeTextModal);
        dom.btnModalCancel.addEventListener('click', closeTextModal);
        dom.btnModalStartScan.addEventListener('click', handleModalScan);

        // 2. Thao tác duyệt lỗi
        dom.btnQuickAcceptTypo.addEventListener('click', handleQuickAcceptTypo);
        dom.btnExport.addEventListener('click', handleExport);
        dom.btnPrevIssue.addEventListener('click', () => navigateIssue(-1));
        dom.btnNextIssue.addEventListener('click', () => navigateIssue(1));

        // 3. Tương tác trên Popover
        dom.popoverCloseBtn.addEventListener('click', hidePopover);
        dom.btnPopoverAccept.addEventListener('click', acceptActiveIssue);
        dom.btnPopoverIgnore.addEventListener('click', ignoreActiveIssue);
        dom.btnPopoverWhitelist.addEventListener('click', whitelistActiveIssue);

        // 4. Lắng nghe phím tắt toàn cục
        window.addEventListener('keydown', handleGlobalKeydown);

        // 5. Bấm vào các thẻ highlight trên cột phải (Event Delegation)
        dom.rightContent.addEventListener('click', handleRightContentClick);

        // Đóng popover khi click ra ngoài
        document.addEventListener('mousedown', (e) => {
            if (!dom.popover.contains(e.target) && !e.target.closest('.diff-issue')) {
                hidePopover();
            }
        });
    }

    // =========================================================================
    // 4. GỌI API /api/scan & XỬ LÝ DỮ LIỆU
    // =========================================================================
    async function executeScan(text, fileName = 'chuong_sach.md') {
        if (!text || !text.trim()) {
            alert('Vui lòng cung cấp nội dung văn bản để quét lỗi!');
            return;
        }

        state.fileName = fileName;
        dom.currentFileName.textContent = fileName;
        dom.rightStatus.textContent = 'Đang phân tích cú pháp & từ điển...';
        dom.rightStatus.style.color = '#d97706';

        try {
            const response = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Không thể quét văn bản.');
            }

            const data = await response.json();

            // Cập nhật State
            state.originalText = data.original_text;
            state.proposedText = data.proposed_text;
            state.issues = data.issues;
            state.issueMap.clear();
            state.decisions = {};

            data.issues.forEach(iss => state.issueMap.set(iss.id, iss));

            // Render giao diện
            renderOriginal(state.originalText);
            renderAnnotated(data.annotated_html);
            updateStatsBar(data.stats);

            dom.rightStatus.textContent = `Hoàn tất! Tìm thấy ${data.issues.length} vấn đề.`;
            dom.rightStatus.style.color = '#15803d';

            // Kích hoạt lỗi đầu tiên nếu có
            if (state.issues.length > 0) {
                setActiveIssueIndex(0);
            } else {
                updateProgress();
            }

            // Lưu bộ nhớ đệm
            saveToLocalStorage();

        } catch (error) {
            console.error('Lỗi API /api/scan:', error);
            alert(`Đã xảy ra lỗi khi quét: ${error.message}`);
            dom.rightStatus.textContent = 'Lỗi phân tích!';
            dom.rightStatus.style.color = '#dc2626';
        }
    }

    // =========================================================================
    // 5. RENDER NỘI DUNG VÀ HIGHLIGHT LÊN GIAO DIỆN
    // =========================================================================
    function renderOriginal(text) {
        dom.leftContent.textContent = text;
        const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
        dom.leftCharCount.textContent = `${wordCount.toLocaleString()} từ`;
    }

    function renderAnnotated(annotatedHtml) {
        dom.rightContent.innerHTML = annotatedHtml;
    }

    function updateStatsBar(stats) {
        dom.statTotal.textContent = stats.TOTAL || 0;
        dom.statTypo.textContent = stats.TYPOGRAPHY || 0;
        dom.statCase.textContent = stats.CAPITALIZATION || 0;
        dom.statSplit.textContent = stats.OCR_SPLIT || 0;
        dom.statOcr.textContent = stats.TYPO_OCR || 0;
    }

    function updateProgress() {
        const total = state.issues.length;
        const current = state.activeIssueIndex >= 0 ? state.activeIssueIndex + 1 : 0;
        dom.issueProgress.textContent = `${current} / ${total}`;
    }

    // =========================================================================
    // 6. ĐIỀU HƯỚNG VÀ CHỌN LỖI (ACTIVE ISSUE FOCUS)
    // =========================================================================
    function setActiveIssueIndex(index) {
        if (state.issues.length === 0) {
            state.activeIssueIndex = -1;
            updateProgress();
            hidePopover();
            return;
        }

        // Bọc vòng tuần hoàn nếu vượt quá biên
        if (index >= state.issues.length) index = 0;
        if (index < 0) index = state.issues.length - 1;

        state.activeIssueIndex = index;
        updateProgress();

        const issue = state.issues[index];
        const targetEl = dom.rightContent.querySelector(`.diff-issue[data-id="${issue.id}"]`);

        // Bỏ active cũ
        dom.rightContent.querySelectorAll('.diff-issue.is-active-target').forEach(el => {
            el.classList.remove('is-active-target');
        });

        if (targetEl) {
            targetEl.classList.add('is-active-target');
            targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            showPopover(issue, targetEl);
        }
    }

    function navigateIssue(direction) {
        if (state.issues.length === 0) return;
        setActiveIssueIndex(state.activeIssueIndex + direction);
    }

    function handleRightContentClick(e) {
        const target = e.target.closest('.diff-issue');
        if (!target) return;

        const issueId = target.getAttribute('data-id');
        const index = state.issues.findIndex(iss => iss.id === issueId);
        if (index !== -1) {
            setActiveIssueIndex(index);
        }
    }

    // =========================================================================
    // 7. POPOVER DUYỆT LỖI TƯƠNG TÁC
    // =========================================================================
    function showPopover(issue, targetEl) {
        dom.popoverId.textContent = `#${issue.id}`;
        dom.popoverCategory.textContent = issue.category;
        dom.popoverOriginal.textContent = issue.original;
        dom.popoverReplacement.textContent = issue.replacement;
        dom.popoverExplanation.textContent = issue.explanation || 'Không có mô tả quy tắc.';

        // Màu sắc nhãn nhóm
        dom.popoverCategory.className = 'badge-cat';
        dom.popoverCategory.classList.add(`chip-${issue.category.toLowerCase()}`);

        // Xử lý danh sách gợi ý thay thế (SymSpell)
        dom.popoverSugList.innerHTML = '';
        if (issue.suggestions && issue.suggestions.length > 1) {
            dom.popoverSugContainer.style.display = 'block';
            issue.suggestions.forEach(sug => {
                const btn = document.createElement('button');
                btn.className = 'sug-chip';
                btn.textContent = sug;
                btn.title = `Chọn từ '${sug}'`;
                btn.addEventListener('click', () => {
                    dom.popoverReplacement.textContent = sug;
                    acceptActiveIssue(sug);
                });
                dom.popoverSugList.appendChild(btn);
            });
        } else {
            dom.popoverSugContainer.style.display = 'none';
        }

        // Định vị vị trí Popover nổi bên dưới target element
        dom.popover.style.display = 'flex';

        const rect = targetEl.getBoundingClientRect();
        const popoverWidth = 320;
        let left = rect.left + window.scrollX - (popoverWidth / 2) + (rect.width / 2);
        let top = rect.bottom + window.scrollY + 8;

        // Tránh tràn viền màn hình bên phải
        if (left + popoverWidth > window.innerWidth - 20) {
            left = window.innerWidth - popoverWidth - 20;
        }
        if (left < 20) left = 20;

        dom.popover.style.left = `${left}px`;
        dom.popover.style.top = `${top}px`;
    }

    function hidePopover() {
        dom.popover.style.display = 'none';
        dom.rightContent.querySelectorAll('.diff-issue.is-active-target').forEach(el => {
            el.classList.remove('is-active-target');
        });
    }

    // =========================================================================
    // 8. CÁC QUYẾT ĐỊNH DUYỆT (ACCEPT / IGNORE / WHITELIST)
    // =========================================================================
    function acceptActiveIssue(customReplacement = null) {
        if (state.activeIssueIndex < 0 || state.activeIssueIndex >= state.issues.length) return;

        const issue = state.issues[state.activeIssueIndex];
        const chosenReplacement = typeof customReplacement === 'string' ? customReplacement : issue.replacement;

        state.decisions[issue.id] = chosenReplacement;

        // Cập nhật hiển thị trên DOM
        const targetEl = dom.rightContent.querySelector(`.diff-issue[data-id="${issue.id}"]`);
        if (targetEl) {
            targetEl.textContent = chosenReplacement;
            targetEl.style.backgroundColor = '#dcfce7';
            targetEl.style.color = '#15803d';
            targetEl.style.borderBottom = '2px solid #22c55e';
        }

        saveToLocalStorage();

        // Tự động nhảy sang lỗi kế tiếp
        navigateIssue(1);
    }

    function ignoreActiveIssue() {
        if (state.activeIssueIndex < 0 || state.activeIssueIndex >= state.issues.length) return;

        const issue = state.issues[state.activeIssueIndex];
        state.decisions[issue.id] = '__IGNORE__';

        // Cập nhật DOM (làm mờ nhãn)
        const targetEl = dom.rightContent.querySelector(`.diff-issue[data-id="${issue.id}"]`);
        if (targetEl) {
            targetEl.textContent = issue.original;
            targetEl.style.opacity = '0.4';
            targetEl.style.textDecoration = 'none';
            targetEl.style.borderBottom = 'none';
        }

        saveToLocalStorage();
        navigateIssue(1);
    }

    async function whitelistActiveIssue() {
        if (state.activeIssueIndex < 0 || state.activeIssueIndex >= state.issues.length) return;

        const issue = state.issues[state.activeIssueIndex];
        const wordToWhitelist = issue.original.trim();

        if (!confirm(`Bạn có chắc chắn muốn thêm từ '${wordToWhitelist}' vào Whitelist để miễn kiểm tra cho toàn bộ cuốn sách?`)) {
            return;
        }

        try {
            const res = await fetch('/api/whitelist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ word: wordToWhitelist })
            });

            const data = await res.json();
            if (data.success) {
                // Tự động bỏ qua lỗi hiện tại
                ignoreActiveIssue();

                // Quét bỏ qua toàn bộ các lỗi có cùng từ này trong văn bản
                state.issues.forEach(iss => {
                    if (iss.original.trim().toLowerCase() === wordToWhitelist.toLowerCase()) {
                        state.decisions[iss.id] = '__IGNORE__';
                        const el = dom.rightContent.querySelector(`.diff-issue[data-id="${iss.id}"]`);
                        if (el) {
                            el.style.opacity = '0.4';
                            el.style.borderBottom = 'none';
                        }
                    }
                });

                saveToLocalStorage();
            }
        } catch (err) {
            alert(`Lỗi thêm Whitelist: ${err.message}`);
        }
    }

    // =========================================================================
    // 9. THAO TÁC DUYỆT NHANH ĐỊNH DẠNG & XUẤT FILE MARKDOWN
    // =========================================================================
    function handleQuickAcceptTypo() {
        let count = 0;
        state.issues.forEach(iss => {
            if (iss.category === 'TYPOGRAPHY' || iss.category === 'CAPITALIZATION') {
                state.decisions[iss.id] = iss.replacement;
                const el = dom.rightContent.querySelector(`.diff-issue[data-id="${iss.id}"]`);
                if (el) {
                    el.textContent = iss.replacement;
                    el.style.backgroundColor = '#dcfce7';
                    el.style.color = '#15803d';
                    el.style.borderBottom = '2px solid #22c55e';
                }
                count++;
            }
        });

        saveToLocalStorage();
        alert(`Đã tự động duyệt xong ${count} lỗi định dạng dấu câu và viết hoa!`);
    }

    async function handleExport() {
        if (!state.originalText) {
            alert('Chưa có văn bản để xuất!');
            return;
        }

        // Với các lỗi người dùng chưa thao tác bấm, mặc định chọn đề xuất sửa
        const finalDecisions = {};
        state.issues.forEach(iss => {
            if (state.decisions[iss.id] !== undefined) {
                finalDecisions[iss.id] = state.decisions[iss.id];
            } else {
                finalDecisions[iss.id] = iss.replacement;
            }
        });

        try {
            dom.btnExport.textContent = '⏳ Đang đóng gói...';
            dom.btnExport.disabled = true;

            const res = await fetch('/api/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    original_text: state.originalText,
                    issues: state.issues,
                    decisions: finalDecisions
                })
            });

            if (!res.ok) throw new Error('Lỗi khi xuất file.');

            const data = await res.json();
            const cleanMarkdown = data.result;

            // Kích hoạt tải tệp .md về máy tính
            downloadFile(cleanMarkdown, `clean_${state.fileName}`);

        } catch (err) {
            alert(`Lỗi xuất file: ${err.message}`);
        } finally {
            dom.btnExport.textContent = '💾 Xuất Markdown';
            dom.btnExport.disabled = false;
        }
    }

    function downloadFile(content, fileName) {
        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // 10. PHÍM TẮT TOÀN CỤC (KEYBOARD SHORTCUTS: J, K, Enter, X, W)
    // =========================================================================
    function handleGlobalKeydown(e) {
        // Nếu đang gõ trong ô nhập liệu (textarea / input) hoặc modal mở -> Không kích hoạt phím tắt
        if (['TEXTAREA', 'INPUT'].includes(document.activeElement.tagName) || dom.textModal.style.display === 'flex') {
            if (e.key === 'Escape') closeTextModal();
            return;
        }

        const key = e.key.toUpperCase();

        if (key === 'J') {
            e.preventDefault();
            navigateIssue(1);
        } else if (key === 'K') {
            e.preventDefault();
            navigateIssue(-1);
        } else if (key === 'ENTER') {
            e.preventDefault();
            acceptActiveIssue();
        } else if (key === 'X') {
            e.preventDefault();
            ignoreActiveIssue();
        } else if (key === 'W') {
            e.preventDefault();
            whitelistActiveIssue();
        } else if (e.key === 'Escape') {
            hidePopover();
        }
    }

    // =========================================================================
    // 11. CUỘN ĐỒNG BỘ 2 CỘT (SYNCHRONIZED SCROLLING)
    // =========================================================================
    function setupSynchronizedScrolling() {
        const left = dom.leftContent;
        const right = dom.rightContent;

        function syncScroll(source, target) {
            if (state.isSyncingScroll) return;
            state.isSyncingScroll = true;

            const maxSource = source.scrollHeight - source.clientHeight;
            const maxTarget = target.scrollHeight - target.clientHeight;

            if (maxSource > 0 && maxTarget > 0) {
                const ratio = source.scrollTop / maxSource;
                target.scrollTop = ratio * maxTarget;
            }

            requestAnimationFrame(() => {
                state.isSyncingScroll = false;
            });
        }

        left.addEventListener('scroll', () => syncScroll(left, right));
        right.addEventListener('scroll', () => syncScroll(right, left));
    }

    // =========================================================================
    // 12. QUẢN LÝ TẢI FILE & MODAL DÁN VĂN BẢN
    // =========================================================================
    function handleFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target.result;
            executeScan(content, file.name);
        };
        reader.readAsText(file, 'utf-8');
    }

    function openTextModal() {
        dom.rawTextInput.value = state.originalText || '';
        dom.textModal.style.display = 'flex';
        dom.rawTextInput.focus();
    }

    function closeTextModal() {
        dom.textModal.style.display = 'none';
    }

    function handleModalScan() {
        const content = dom.rawTextInput.value;
        if (content.trim()) {
            closeTextModal();
            executeScan(content, 'van_ban_nhap.md');
        } else {
            alert('Vui lòng không để trống văn bản!');
        }
    }

    // =========================================================================
    // 13. LƯU VÀ KHÔI PHỤC TIẾN ĐỘ BẰNG LOCALSTORAGE
    // =========================================================================
    function saveToLocalStorage() {
        try {
            const cache = {
                originalText: state.originalText,
                proposedText: state.proposedText,
                issues: state.issues,
                decisions: state.decisions,
                fileName: state.fileName,
                annotatedHtml: dom.rightContent.innerHTML
            };
            localStorage.setItem('vietlit_proofreader_cache', JSON.stringify(cache));
        } catch (e) {
            // Tràn quota LocalStorage nếu chương sách quá dài -> bỏ qua
        }
    }

    function loadFromLocalStorage() {
        try {
            const raw = localStorage.getItem('vietlit_proofreader_cache');
            if (!raw) return;

            const cache = JSON.parse(raw);
            if (!cache.originalText) return;

            state.originalText = cache.originalText;
            state.proposedText = cache.proposedText;
            state.issues = cache.issues || [];
            state.decisions = cache.decisions || {};
            state.fileName = cache.fileName || 'chuong_sach.md';

            state.issueMap.clear();
            state.issues.forEach(iss => state.issueMap.set(iss.id, iss));

            dom.currentFileName.textContent = state.fileName;
            renderOriginal(state.originalText);
            renderAnnotated(cache.annotatedHtml);

            // Tính toán lại stats
            const stats = { TOTAL: state.issues.length, TYPOGRAPHY: 0, CAPITALIZATION: 0, OCR_SPLIT: 0, TYPO_OCR: 0 };
            state.issues.forEach(iss => stats[iss.category] = (stats[iss.category] || 0) + 1);
            updateStatsBar(stats);

            if (state.issues.length > 0) {
                setActiveIssueIndex(0);
            }
        } catch (e) {
            localStorage.removeItem('vietlit_proofreader_cache');
        }
    }

    // Khởi chạy
    document.addEventListener('DOMContentLoaded', init);
})();
