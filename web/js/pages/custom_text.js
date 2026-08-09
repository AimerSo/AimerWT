/**
 * 自定义文本模块
 */
const CustomText = {
    name: '自定义文本',
    icon: 'ri-sparkling-2-line',
    viewId: 'view-custom_text',
    _initialized: false,
    groups: [],
    groupMap: {},
    currentGroup: '',
    currentCsvFile: 'menu.csv',
    csvFiles: [],
    currentLanguage: 'Chinese',
    csvFileDropdown: null,
    languageDropdown: null,
    dirtyEntries: new Set(),
    _busy: false,
    _loadRequestId: 0,

    init() {
        this.render();
        this.bindEvents();
        this.loadData();
    },

    render() {
        const container = document.getElementById('resource_content_container');
        if (!container) return;

        const view = document.createElement('div');
        view.className = 'resource-view';
        view.id = this.viewId;
        view.innerHTML = `
            <div class="resource-view-header">
                <h2><i class="${this.icon}"></i> ${this.name}</h2>
                <div class="resource-view-header-right custom-text-actions">
                    <div id="custom-text-csv-file-dropdown"></div>
                    <select id="custom-text-csv-file" class="custom-text-select custom-text-native-select" aria-hidden="true" tabindex="-1"></select>
                    <div id="custom-text-language-dropdown"></div>
                    <select id="custom-text-language" class="custom-text-select custom-text-native-select" aria-hidden="true" tabindex="-1"></select>
                    <button class="btn-v2" id="btn-custom-text-backup" title="备份 / 还原"><i class="ri-archive-line"></i></button>
                    <button class="btn-v2" id="btn-custom-text-import" title="导入"><i class="ri-upload-2-line"></i></button>
                    <button class="btn-v2" id="btn-custom-text-export" title="导出"><i class="ri-download-2-line"></i></button>
                    <button class="btn-v2" id="btn-custom-text-reload" title="刷新"><i class="ri-refresh-line"></i></button>
                    <button class="btn-v2 primary" id="btn-custom-text-save"><i class="ri-save-3-line"></i><span>保存当前语言</span></button>
                </div>
            </div>
            <div class="custom-text-wrap">
                <aside class="custom-text-groups">
                    <div class="custom-text-groups-head">分组</div>
                    <div class="custom-text-groups-search-wrap">
                        <input id="custom-text-group-search" class="custom-text-group-search" placeholder="搜索分组...">
                    </div>
                    <div class="custom-text-groups-list" id="custom-text-groups-list"></div>
                </aside>
                <section class="custom-text-main">
                    <div class="custom-text-toolbar">
                        <input id="custom-text-search" class="custom-text-search" placeholder="搜索 ID 或文本...">
                        <div class="custom-text-summary" id="custom-text-summary">等待加载...</div>
                    </div>
                    <div class="custom-text-table" id="custom-text-table"></div>
                </section>
            </div>
        `;
        container.appendChild(view);
    },

    bindEvents() {
        const reloadBtn = document.getElementById('btn-custom-text-reload');
        const saveBtn = document.getElementById('btn-custom-text-save');
        const importBtn = document.getElementById('btn-custom-text-import');
        const exportBtn = document.getElementById('btn-custom-text-export');
        const backupBtn = document.getElementById('btn-custom-text-backup');
        const searchEl = document.getElementById('custom-text-search');
        const groupSearchEl = document.getElementById('custom-text-group-search');
        const langEl = document.getElementById('custom-text-language');
        const csvEl = document.getElementById('custom-text-csv-file');

        if (reloadBtn) reloadBtn.onclick = () => this.reloadData();
        if (saveBtn) saveBtn.onclick = () => this.saveData();
        if (importBtn) importBtn.onclick = () => this.importData();
        if (exportBtn) exportBtn.onclick = () => this.exportData();
        if (backupBtn) backupBtn.onclick = () => this.showBackupRestoreDialog();
        if (searchEl) searchEl.oninput = () => this.renderRows();
        if (groupSearchEl) groupSearchEl.oninput = () => this.renderGroupList();
        if (csvEl) {
            csvEl.onchange = async (e) => {
                const nextCsvFile = String(e.target.value || '').trim();
                if (!nextCsvFile || nextCsvFile === this.currentCsvFile) return;
                if (this._busy) {
                    csvEl.value = this.currentCsvFile;
                    this.syncHeaderDropdown(this.csvFileDropdown, csvEl);
                    return;
                }
                if (!await this.confirmDiscardChanges('切换 CSV')) {
                    csvEl.value = this.currentCsvFile;
                    this.syncHeaderDropdown(this.csvFileDropdown, csvEl);
                    return;
                }
                this.dirtyEntries.clear();
                this.currentCsvFile = nextCsvFile;
                this.setBusy(true);
                try {
                    await this.loadData();
                } finally {
                    this.setBusy(false);
                }
            };
        }
        if (langEl) {
            langEl.onchange = (e) => {
                if (this._busy) {
                    langEl.value = this.currentLanguage;
                    this.syncHeaderDropdown(this.languageDropdown, langEl);
                    return;
                }
                this.currentLanguage = String(e.target.value || 'Chinese');
                this.renderRows();
            };
        }
        this.initHeaderDropdowns();
    },

    makeDirtyKey(csvFile, language, textId) {
        return `${String(csvFile)}\u0001${String(language)}\u0001${String(textId)}`;
    },

    hasDirtyEntries() {
        return this.dirtyEntries.size > 0;
    },

    async confirmDiscardChanges(actionName) {
        if (!this.hasDirtyEntries()) return true;
        return app.showConfirmDialog(
            '存在未保存修改',
            `当前还有 <strong>${this.dirtyEntries.size}</strong> 条未保存修改。${this.escapeHtml(actionName)}会丢弃这些内容，是否继续？`
        );
    },

    setBusy(busy) {
        this._busy = Boolean(busy);
        [
            'btn-custom-text-backup',
            'btn-custom-text-import',
            'btn-custom-text-export',
            'btn-custom-text-reload',
            'btn-custom-text-save'
        ].forEach((id) => {
            const button = document.getElementById(id);
            if (button) button.disabled = this._busy;
        });
        const view = document.getElementById(this.viewId);
        if (view) view.setAttribute('aria-busy', this._busy ? 'true' : 'false');
    },

    async reloadData() {
        if (this._busy) return;
        if (!await this.confirmDiscardChanges('刷新')) return;
        this.dirtyEntries.clear();
        this.setBusy(true);
        try {
            await this.loadData();
        } finally {
            this.setBusy(false);
        }
    },

    initHeaderDropdowns() {
        if (!window.AppDropdownMenu) return;

        const csvEl = document.getElementById('custom-text-csv-file');
        const langEl = document.getElementById('custom-text-language');

        if (!this.csvFileDropdown && csvEl) {
            this.csvFileDropdown = new AppDropdownMenu({
                id: 'custom-text-csv-file-ui',
                containerId: 'custom-text-csv-file-dropdown',
                options: [],
                placeholder: '选择 CSV',
                size: 'md',
                width: '285px',
                onChange: (value) => {
                    if (csvEl.value === value) return;
                    csvEl.value = value;
                    csvEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }

        if (!this.languageDropdown && langEl) {
            this.languageDropdown = new AppDropdownMenu({
                id: 'custom-text-language-ui',
                containerId: 'custom-text-language-dropdown',
                options: [],
                placeholder: '选择语言',
                size: 'md',
                width: '165px',
                onChange: (value) => {
                    if (langEl.value === value) return;
                    langEl.value = value;
                    langEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }
    },

    async loadData() {
        const requestId = ++this._loadRequestId;
        const requestedCsvFile = this.currentCsvFile;
        const summaryEl = document.getElementById('custom-text-summary');
        if (summaryEl) summaryEl.textContent = '加载中...';

        if (!window.pywebview?.api?.get_custom_text_data) {
            app.showAlert('错误', '后端接口不可用', 'error');
            if (summaryEl) summaryEl.textContent = '接口不可用';
            return;
        }

        try {
            const res = await pywebview.api.get_custom_text_data({
                csv_file: requestedCsvFile
            });
            if (requestId !== this._loadRequestId) return;
            if (!res || !res.success) {
                const msg = (res && res.msg) ? res.msg : '加载失败';
                if (res && res.need_restart) {
                    app.showAlert('提示', msg, 'warn');
                } else {
                    app.showAlert('错误', msg, 'error');
                }
                if (summaryEl) summaryEl.textContent = msg;
                this.groups = [];
                this.groupMap = {};
                this.renderGroupList();
                this.renderRows();
                return;
            }

            this.csvFiles = Array.isArray(res.csv_files) ? res.csv_files : [];
            this.currentCsvFile = String(res.csv_file || this.currentCsvFile || 'menu.csv');
            this.renderCsvFileOptions(this.csvFiles);

            this.groups = Array.isArray(res.groups) ? res.groups : [];
            this.groupMap = {};
            this.groups.forEach(g => {
                const key = String(g.group || 'no_prefix');
                this.groupMap[key] = Array.isArray(g.items) ? g.items : [];
            });
            this.currentLanguage = String(res.default_language || 'Chinese');
            if (!this.currentGroup || !this.groupMap[this.currentGroup]) {
                this.currentGroup = this.groups.length > 0 ? String(this.groups[0].group || 'no_prefix') : '';
            }

            this.renderLanguageOptions(Array.isArray(res.language_keys) ? res.language_keys : ['Chinese']);
            this.renderGroupList();
            this.renderRows();

            if (summaryEl) {
                summaryEl.textContent = `${this.currentCsvFile} · 总计 ${Number(res.total || 0)} 条`;
            }
        } catch (e) {
            if (requestId !== this._loadRequestId) return;
            app.showAlert('错误', `加载失败: ${e.message || e}`, 'error');
            if (summaryEl) summaryEl.textContent = '加载失败';
        }
    },

    renderCsvFileOptions(files) {
        const csvEl = document.getElementById('custom-text-csv-file');
        if (!csvEl) return;
        csvEl.innerHTML = '';
        (files || []).forEach((f) => {
            const op = document.createElement('option');
            const fileName = typeof f === 'string' ? f : (f.name || '');
            const isModified = typeof f === 'object' && f.modified;
            op.value = String(fileName);
            op.textContent = isModified ? `★ ${fileName}` : String(fileName);
            if (String(fileName) === this.currentCsvFile) op.selected = true;
            csvEl.appendChild(op);
        });
        this.syncHeaderDropdown(this.csvFileDropdown, csvEl);
    },

    renderLanguageOptions(keys) {
        const langEl = document.getElementById('custom-text-language');
        if (!langEl) return;
        langEl.innerHTML = '';
        keys.forEach((k) => {
            const op = document.createElement('option');
            op.value = String(k);
            op.textContent = String(k);
            if (String(k) === this.currentLanguage) op.selected = true;
            langEl.appendChild(op);
        });
        this.syncHeaderDropdown(this.languageDropdown, langEl);
    },

    syncHeaderDropdown(dropdown, selectEl) {
        if (!dropdown || !selectEl) return;
        const options = Array.from(selectEl.options).map(op => ({
            value: String(op.value),
            label: String(op.textContent || op.value)
        }));
        dropdown.setOptions(options, false);
        if (options.length) {
            dropdown.setValue(String(selectEl.value || options[0].value), false);
        } else {
            dropdown.clear();
        }
    },

    renderGroupList() {
        const listEl = document.getElementById('custom-text-groups-list');
        const groupSearchEl = document.getElementById('custom-text-group-search');
        if (!listEl) return;

        if (!this.groups.length) {
            listEl.innerHTML = '<div class="custom-text-empty">暂无数据</div>';
            return;
        }

        const keyword = String(groupSearchEl?.value || '').trim().toLowerCase();
        const displayGroups = this.groups.filter((g) => {
            const group = String(g.group || 'no_prefix').toLowerCase();
            return !keyword || group.includes(keyword);
        });

        if (!displayGroups.length) {
            listEl.innerHTML = '<div class="custom-text-empty">没有匹配的分组</div>';
            return;
        }

        listEl.innerHTML = displayGroups.map(g => {
            const group = String(g.group || 'no_prefix');
            const count = Array.isArray(g.items) ? g.items.length : 0;
            const active = group === this.currentGroup ? ' active' : '';
            return `<button class="custom-text-group-item${active}" data-group="${this.escapeHtml(group)}">${this.escapeHtml(group)}<span>${count}</span></button>`;
        }).join('');

        listEl.querySelectorAll('.custom-text-group-item').forEach(btn => {
            btn.onclick = () => {
                this.currentGroup = String(btn.dataset.group || '');
                this.renderGroupList();
                this.renderRows();
            };
        });
    },

    renderRows() {
        const tableEl = document.getElementById('custom-text-table');
        const searchEl = document.getElementById('custom-text-search');
        const summaryEl = document.getElementById('custom-text-summary');
        if (!tableEl) return;

        const rawItems = this.groupMap[this.currentGroup] || [];
        const keyword = String(searchEl?.value || '').trim().toLowerCase();
        const items = rawItems.filter((it) => {
            const id = String(it.id || '').toLowerCase();
            const val = String((it.languages && it.languages[this.currentLanguage]) || '').toLowerCase();
            return !keyword || id.includes(keyword) || val.includes(keyword);
        });

        if (!items.length) {
            tableEl.innerHTML = '<div class="custom-text-empty">当前分组没有可显示文本</div>';
            if (summaryEl) summaryEl.textContent = `分组 ${this.currentGroup || '-'}：0 条`;
            return;
        }

        tableEl.innerHTML = items.map((it, idx) => {
            const id = String(it.id || '');
            const val = String((it.languages && it.languages[this.currentLanguage]) || '');
            const isModified = it.modified === true;
            const modifiedClass = isModified ? ' modified' : '';
            const modifiedMark = isModified ? '<span class="modified-mark" title="已修改">★</span>' : '';
            return `
                <div class="custom-text-row${modifiedClass}">
                    <div class="custom-text-id" title="${this.escapeHtml(id)}">${modifiedMark}${this.escapeHtml(id)}</div>
                    <textarea class="custom-text-input" data-id="${this.escapeHtml(id)}" data-index="${idx}">${this.escapeHtml(val)}</textarea>
                </div>
            `;
        }).join('');

        tableEl.querySelectorAll('.custom-text-input').forEach((el) => {
            el.oninput = () => {
                const id = String(el.dataset.id || '');
                const groupItems = this.groupMap[this.currentGroup] || [];
                const target = groupItems.find(x => String(x.id) === id);
                if (!target) return;
                if (!target.languages || typeof target.languages !== 'object') target.languages = {};
                target.languages[this.currentLanguage] = String(el.value || '');
                this.dirtyEntries.add(this.makeDirtyKey(
                    this.currentCsvFile,
                    this.currentLanguage,
                    id
                ));
            };
        });

        if (summaryEl) summaryEl.textContent = `分组 ${this.currentGroup || '-'}：${items.length} 条`;
    },

    async saveData() {
        if (this._busy) return;
        if (!window.pywebview?.api?.save_custom_text_data) {
            app.showAlert('错误', '后端保存接口不可用', 'error');
            return;
        }

        const savedCsvFile = this.currentCsvFile;
        const savedLanguage = this.currentLanguage;
        const changedItems = [];
        Object.values(this.groupMap).forEach((items) => {
            (items || []).forEach((item) => {
                const textId = String(item.id || '');
                const dirtyKey = this.makeDirtyKey(savedCsvFile, savedLanguage, textId);
                if (!this.dirtyEntries.has(dirtyKey)) return;
                changedItems.push({
                    id: textId,
                    text: String((item.languages && item.languages[savedLanguage]) || '')
                });
            });
        });

        if (!changedItems.length) {
            app.showAlert('提示', '当前语言没有未保存修改', 'info');
            return;
        }

        this.setBusy(true);
        try {
            const res = await pywebview.api.save_custom_text_data({
                csv_file: savedCsvFile,
                language: savedLanguage,
                entries: changedItems
            });
            if (res && res.success) {
                const savedIds = new Set(changedItems.map(item => String(item.id)));
                changedItems.forEach((item) => {
                    this.dirtyEntries.delete(this.makeDirtyKey(
                        savedCsvFile,
                        savedLanguage,
                        item.id
                    ));
                });
                Object.values(this.groupMap).forEach((items) => {
                    (items || []).forEach((item) => {
                        if (savedIds.has(String(item.id))) item.modified = true;
                    });
                });
                this.csvFiles = this.csvFiles.map((fileInfo) => {
                    const fileName = typeof fileInfo === 'string' ? fileInfo : String(fileInfo.name || '');
                    if (fileName !== savedCsvFile) return fileInfo;
                    return { name: fileName, modified: true };
                });
                this.renderCsvFileOptions(this.csvFiles);
                this.renderRows();
                app.showAlert('成功', res.msg || '保存成功', 'success');
            } else {
                app.showAlert('错误', (res && res.msg) ? res.msg : '保存失败', 'error');
            }
        } catch (e) {
            app.showAlert('错误', `保存失败: ${e.message || e}`, 'error');
        } finally {
            this.setBusy(false);
        }
    },

    async importData() {
        if (this._busy) return;
        if (!window.pywebview?.api?.import_custom_text) {
            app.showAlert('错误', '后端导入接口不可用', 'error');
            return;
        }
        if (!await this.confirmDiscardChanges('导入')) return;

        this.setBusy(true);
        try {
            const result = await pywebview.api.select_custom_text_file();
            if (!result || !result.success || !result.file_path) return;

            const res = await pywebview.api.import_custom_text({
                file_path: result.file_path
            });
            this.showImportResult(res, result.file_path);
            if (res && res.success) {
                this.dirtyEntries.clear();
                await this.loadData();
            }
        } catch (e) {
            app.showAlert('错误', `导入失败: ${e.message || e}`, 'error');
        } finally {
            this.setBusy(false);
        }
    },

    async exportData() {
        if (this._busy) return;
        if (this.hasDirtyEntries()) {
            app.showAlert('提示', '存在未保存修改，请先保存后再导出。', 'warn');
            return;
        }
        if (!window.pywebview?.api?.select_custom_text_export_folder || !window.pywebview?.api?.export_custom_text_package) {
            app.showAlert('错误', '后端导出接口不可用', 'error');
            return;
        }

        this.setBusy(true);
        try {
            const folderRes = await pywebview.api.select_custom_text_export_folder();
            if (!folderRes || !folderRes.success || !folderRes.folder_path) return;

            const res = await pywebview.api.export_custom_text_package({
                export_folder: folderRes.folder_path
            });
            if (res && res.success) {
                const msg = `${res.msg || '导出成功'}\nCSV: ${Number(res.csv_count || 0)} 个，BLK: ${Number(res.blk_count || 0)} 个\n${res.zip_path || ''}`;
                app.showAlert('成功', msg, 'success');
            } else {
                app.showAlert('错误', (res && res.msg) ? res.msg : '导出失败', 'error');
            }
        } catch (e) {
            app.showAlert('错误', `导出失败: ${e.message || e}`, 'error');
        } finally {
            this.setBusy(false);
        }
    },

    async showBackupRestoreDialog() {
        if (this._busy) return;
        if (this.hasDirtyEntries()) {
            app.showAlert('提示', '存在未保存修改，请先保存后再创建或还原备份。', 'warn');
            return;
        }
        let backups = [];
        this.setBusy(true);
        try {
            if (window.pywebview?.api?.get_custom_text_backups) {
                const res = await pywebview.api.get_custom_text_backups();
                if (res && res.success) backups = res.backups || [];
            }
        } catch (e) {
            console.error('获取备份列表失败:', e);
            app.showAlert('错误', `获取备份列表失败: ${e.message || e}`, 'error');
        } finally {
            this.setBusy(false);
        }

        const existing = document.getElementById('modal-custom-text-backup');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'modal-custom-text-backup';
        overlay.className = 'custom-text-backup-overlay';
        overlay.onclick = (e) => {
            if (e.target === overlay) this.closeBackupRestoreDialog(overlay);
        };

        const modal = document.createElement('div');
        modal.className = 'custom-text-backup-modal';
        modal.onclick = (e) => e.stopPropagation();

        // 备份列表 HTML
        let backupListHtml = '';
        if (backups.length > 0) {
            backupListHtml = `
                <div class="custom-text-backup-list">
                    ${backups.map(b => `
                        <div class="custom-text-backup-item" data-name="${this.escapeHtml(b.name)}">
                            <div class="custom-text-backup-item-info">
                                <div class="custom-text-backup-item-name">
                                    <span class="custom-text-backup-file-icon"><i class="ri-file-zip-line"></i></span>
                                    <span>${this.escapeHtml(b.name)}</span>
                                </div>
                                <div class="custom-text-backup-item-meta">${this.escapeHtml(b.time)} · ${this.escapeHtml(b.size_kb)} KB</div>
                            </div>
                            <button class="btn primary custom-text-backup-restore-btn" data-name="${this.escapeHtml(b.name)}">
                                <i class="ri-history-line"></i>
                                <span>还原</span>
                            </button>
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            backupListHtml = `
                <div class="custom-text-backup-empty">
                    <div class="custom-text-backup-empty-icon"><i class="ri-inbox-archive-line"></i></div>
                    <div class="custom-text-backup-empty-title">暂无备份记录</div>
                    <div class="custom-text-backup-empty-text">先创建一份备份，之后就可以在这里快速还原。</div>
                </div>
            `;
        }

        modal.innerHTML = `
            <button class="modal-close-x custom-text-backup-close" id="backup-dialog-close" aria-label="关闭">
                <i class="ri-close-line"></i>
            </button>
            <div class="custom-text-backup-head">
                <div class="custom-text-backup-title-row">
                    <div class="custom-text-backup-title-block">
                        <h2 class="custom-text-backup-title">备份与还原</h2>
                        <p class="custom-text-backup-subtitle">统一管理当前自定义文本，手动备份并从历史快照恢复。</p>
                    </div>
                    <div class="custom-text-backup-head-stat" aria-label="历史备份数量">
                        <span class="custom-text-backup-head-stat-label">历史备份</span>
                        <strong class="custom-text-backup-head-stat-value">${backups.length}</strong>
                    </div>
                </div>
            </div>
            <div class="custom-text-backup-body">
                <div class="custom-text-backup-callout">
                    <div class="custom-text-backup-callout-mark">覆盖提示</div>
                    <div class="custom-text-backup-callout-text">
                        还原会覆盖当前 lang/aimerWT 中的自定义文本文件，建议先执行一次备份。
                    </div>
                </div>
                <div class="custom-text-backup-primary-panel">
                    <div class="custom-text-backup-primary-copy">
                        <div class="custom-text-backup-primary-label">手动创建快照</div>
                        <div class="custom-text-backup-primary-text">建议在导入、批量修改或还原之前先备份一次，方便快速回退。</div>
                    </div>
                    <button class="btn primary custom-text-backup-create-btn" id="btn-backup-create">
                        <i class="ri-save-3-line"></i>
                        <span>立即备份当前数据</span>
                    </button>
                </div>
                <div class="custom-text-backup-section">
                    <div class="custom-text-backup-section-head">
                        <div>
                            <div class="custom-text-backup-section-label">历史备份</div>
                            <div class="custom-text-backup-section-desc">按时间倒序显示最近保留的备份压缩包。</div>
                        </div>
                        <span class="custom-text-backup-count">${backups.length}</span>
                    </div>
                    ${backupListHtml}
                </div>
            </div>
            <div class="custom-text-backup-footer">
                <button class="btn secondary" id="btn-backup-dialog-done">关闭</button>
            </div>
        `;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // 绑定关闭
        modal.querySelector('#backup-dialog-close').onclick = () => this.closeBackupRestoreDialog(overlay);
        modal.querySelector('#btn-backup-dialog-done').onclick = () => this.closeBackupRestoreDialog(overlay);

        // 绑定"立即备份"
        modal.querySelector('#btn-backup-create').onclick = async () => {
            const success = await this.backupData();
            if (!success) return;
            this.closeBackupRestoreDialog(overlay);
            this.showBackupRestoreDialog();
        };

        // 绑定所有"还原"按钮
        modal.querySelectorAll('.custom-text-backup-restore-btn').forEach(btn => {
            btn.onclick = async () => {
                const zipName = btn.dataset.name;
                const ok = await app.showConfirmDialog(
                    '确认还原备份',
                    `将要还原备份：<strong style="color: var(--primary);">${this.escapeHtml(zipName)}</strong><br><br>还原后当前的自定义文本将被覆盖，是否继续？`
                );
                if (!ok) return;
                const success = await this.restoreData(zipName);
                if (!success) return;
                this.closeBackupRestoreDialog(overlay);
            };
        });
    },

    closeBackupRestoreDialog(overlay) {
        if (!overlay || overlay.dataset.closing === '1') return;
        overlay.dataset.closing = '1';
        overlay.classList.add('closing');

        const removeOverlay = () => {
            if (overlay && overlay.parentNode) {
                overlay.remove();
            }
        };

        const onAnimationEnd = (event) => {
            if (event.target !== overlay) return;
            overlay.removeEventListener('animationend', onAnimationEnd);
            removeOverlay();
        };

        overlay.addEventListener('animationend', onAnimationEnd);
        setTimeout(removeOverlay, 260);
    },

    async backupData() {
        if (this._busy) return false;
        if (!window.pywebview?.api?.backup_custom_text) {
            app.showAlert('错误', '后端备份接口不可用', 'error');
            return false;
        }
        this.setBusy(true);
        try {
            const res = await pywebview.api.backup_custom_text();
            if (res && res.success) {
                app.showAlert('成功', res.msg || '备份成功', 'success');
                return true;
            } else {
                app.showAlert('错误', (res && res.msg) ? res.msg : '备份失败', 'error');
                return false;
            }
        } catch (e) {
            app.showAlert('错误', `备份失败: ${e.message || e}`, 'error');
            return false;
        } finally {
            this.setBusy(false);
        }
    },

    async restoreData(zipName) {
        if (this._busy) return false;
        if (!window.pywebview?.api?.restore_custom_text) {
            app.showAlert('错误', '后端还原接口不可用', 'error');
            return false;
        }
        this.setBusy(true);
        try {
            const res = await pywebview.api.restore_custom_text({ zip_name: zipName });
            if (res && res.success) {
                this.dirtyEntries.clear();
                app.showAlert('成功', res.msg || '还原成功', 'success');
                await this.loadData();
                return true;
            } else {
                app.showAlert('错误', (res && res.msg) ? res.msg : '还原失败', 'error');
                return false;
            }
        } catch (e) {
            app.showAlert('错误', `还原失败: ${e.message || e}`, 'error');
            return false;
        } finally {
            this.setBusy(false);
        }
    },

    showImportResult(result, originalFilePath) {
        // 解析导入结果
        const success = result.success || false;
        const mappingInfo = result.mapping_info || result.details || [];
        const importedCount = (result.imported_files || []).length;
        const skippedCount = (result.skipped_files || []).length;
        const skippedFiles = result.skipped_files || [];
        const tempDir = result.temp_dir || null;  // 临时目录路径

        // 分类处理映射信息
        const successItems = [];
        const warningItems = [];
        const errorItems = [];

        mappingInfo.forEach(info => {
            const infoStr = String(info);
            if (infoStr.startsWith('✓')) {
                successItems.push(infoStr.substring(1).trim());
            } else if (infoStr.startsWith('⚠')) {
                warningItems.push(infoStr.substring(1).trim());
            } else if (infoStr.startsWith('✗')) {
                errorItems.push(infoStr.substring(1).trim());
            } else {
                // 默认归类
                if (infoStr.includes('跳过') || infoStr.includes('无法识别')) {
                    warningItems.push(infoStr);
                } else if (infoStr.includes('失败')) {
                    errorItems.push(infoStr);
                } else {
                    successItems.push(infoStr);
                }
            }
        });

        // 创建模态框
        const overlay = document.createElement('div');
        overlay.className = 'import-result-overlay';
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                this.closeImportResult(overlay, tempDir);
            }
        };

        const modal = document.createElement('div');
        modal.className = 'import-result-modal';
        modal.onclick = (e) => e.stopPropagation();

        // 确定图标类型
        let iconClass = 'success';
        let iconSymbol = '✓';
        let titleText = '导入成功';

        if (!success) {
            iconClass = 'error';
            iconSymbol = '✗';
            titleText = '导入失败';
        } else if (skippedCount > 0) {
            iconClass = 'warning';
            iconSymbol = '⚠';
            titleText = '部分导入成功';
        }

        // 构建HTML
        modal.innerHTML = `
            <div class="import-result-header">
                <div class="import-result-title">
                    <div class="import-result-icon ${iconClass}">${iconSymbol}</div>
                    <span>${titleText}</span>
                </div>
                <button class="import-result-close" type="button" data-import-result-close>×</button>
            </div>
            <div class="import-result-body">
                ${this.renderImportSummary(result, importedCount, skippedCount)}
                ${this.renderImportSection('成功导入', successItems, 'success')}
                ${this.renderImportSection('跳过文件', warningItems, 'warning')}
                ${this.renderImportSection('导入失败', errorItems, 'error')}
                ${skippedCount > 0 && tempDir ? this.renderSkippedFilesSection(skippedFiles, tempDir) : ''}
            </div>
            <div class="import-result-footer">
                <button class="import-result-btn import-result-btn-primary" type="button" data-import-result-close>
                    ${skippedCount > 0 && tempDir ? '稍后处理' : '确定'}
                </button>
            </div>
        `;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        modal.querySelectorAll('[data-import-result-close]').forEach((button) => {
            button.onclick = () => this.closeImportResult(overlay, tempDir);
        });

        const manualImportBtn = modal.querySelector('.manual-import-confirm-btn');
        if (manualImportBtn) {
            manualImportBtn.onclick = () => this.confirmManualImportInline(manualImportBtn, tempDir);
        }
    },

    renderSkippedFilesSection(skippedFiles, tempDir) {
        const fileListHtml = skippedFiles.map((fileName) => `
            <div class="manual-import-file-item">
                <label class="manual-import-file-label">
                    <input type="checkbox" class="manual-import-checkbox" value="${this.escapeHtml(fileName)}" checked>
                    <span class="manual-import-file-name">${this.escapeHtml(fileName)}</span>
                </label>
            </div>
        `).join('');

        return `
            <div class="import-result-section" style="margin-top: 24px;">
                <div class="manual-import-warning">
                    <div class="manual-import-warning-icon">!</div>
                    <div class="manual-import-warning-text">
                        <strong>是否导入这些文件？</strong><br>
                        以下文件无法自动识别，但可能是有效的自定义文本模组。<br>
                        确认后，这些文件将以<strong>原文件名</strong>直接导入到 <code>lang/aimerWT/</code> 目录，<br>
                        并在 <code>localization.blk</code> 中添加对应的引用路径。
                    </div>
                </div>
                <div class="import-result-section-title">
                    选择要导入的文件
                    <span class="import-result-section-badge warning">${skippedFiles.length}</span>
                </div>
                <div class="manual-import-files-list">
                    ${fileListHtml}
                </div>
                <div style="margin-top: 16px; display: flex; gap: 12px; justify-content: flex-end;">
                    <button class="import-result-btn import-result-btn-primary manual-import-confirm-btn" type="button">
                        <i class="ri-check-line"></i> 确认导入选中的文件
                    </button>
                </div>
            </div>
        `;
    },

    async closeImportResult(overlay, tempDir) {
        if (overlay && overlay.parentNode) {
            overlay.remove();
        }
        if (tempDir) {
            await this.cleanupTempDir(tempDir);
        }
    },

    async cleanupTempDir(tempDir) {
        try {
            if (window.pywebview?.api?.cleanup_import_temp) {
                await pywebview.api.cleanup_import_temp({ temp_dir: tempDir });
            }
        } catch (e) {
            console.error('清理临时目录失败:', e);
        }
    },

    confirmManualImportInline(buttonElement, tempDir) {
        const modal = buttonElement.closest('.import-result-modal');
        const checkboxes = modal.querySelectorAll('.manual-import-checkbox:checked');
        const selectedFiles = Array.from(checkboxes).map(cb => cb.value);

        if (selectedFiles.length === 0) {
            app.showAlert('提示', '未选择任何文件', 'warn');
            return;
        }

        // 关闭当前对话框
        const overlay = buttonElement.closest('.import-result-overlay');
        overlay.remove();

        // 执行导入
        this.executeManualImport(tempDir, selectedFiles);
    },

    async handleSkippedFiles(skippedFiles, originalFilePath) {
        // 这个方法已经不需要了，因为跳过的文件直接在结果对话框中处理
    },

    showManualImportDialog(skippedFiles, originalFilePath) {
        // 这个方法已经不需要了
    },

    async executeManualImport(tempDir, selectedFiles) {
        if (!selectedFiles || selectedFiles.length === 0) {
            app.showAlert('提示', '未选择任何文件', 'warn');
            return;
        }

        try {
            app.showAlert('提示', '正在导入，请稍候...', 'info');

            const res = await pywebview.api.import_custom_text_manual({
                selected_files: selectedFiles,
                temp_dir: tempDir
            });

            if (res && res.success) {
                this.showImportResult(res, null);
                this.loadData();
            } else {
                this.showImportResult(res, null);
            }
        } catch (e) {
            app.showAlert('错误', `导入失败: ${e.message || e}`, 'error');
        }
    },

    renderImportSummary(result, importedCount, skippedCount) {
        const msg = result.msg || '';
        const mode = result.mode || 'standard';
        const modeText = mode === 'custom_blk' ? '智能合并模式' : '标准模式';

        return `
            <div class="import-result-summary">
                <p class="import-result-summary-text">
                    ${this.escapeHtml(msg)}<br>
                    <span style="font-size: 13px; opacity: 0.8;">导入模式：${modeText}</span>
                </p>
            </div>
        `;
    },

    renderImportSection(title, items, type) {
        if (!items || items.length === 0) return '';

        const iconMap = {
            success: '✓',
            warning: '⚠',
            error: '✗'
        };

        const itemsHtml = items.map(item => {
            // 解析统计信息（如果有）
            const statsMatch = item.match(/\(新增 (\d+) 条, 修改 (\d+) 条\)/);
            let mainText = item;
            let statsHtml = '';

            if (statsMatch) {
                mainText = item.replace(statsMatch[0], '').trim();
                const added = statsMatch[1];
                const modified = statsMatch[2];
                statsHtml = `
                    <div class="import-result-item-stats">
                        <span class="import-result-item-stat">
                            <span class="import-result-item-stat-value">+${added}</span> 新增
                        </span>
                        <span class="import-result-item-stat">
                            <span class="import-result-item-stat-value">${modified}</span> 修改
                        </span>
                    </div>
                `;
            }

            return `
                <div class="import-result-item">
                    <div class="import-result-item-icon ${type}">${iconMap[type]}</div>
                    <div class="import-result-item-content">
                        <div class="import-result-item-text">${this.escapeHtml(mainText)}</div>
                        ${statsHtml}
                    </div>
                </div>
            `;
        }).join('');

        return `
            <div class="import-result-section">
                <div class="import-result-section-title">
                    ${title}
                    <span class="import-result-section-badge ${type}">${items.length}</span>
                </div>
                <div class="import-result-items">
                    ${itemsHtml}
                </div>
            </div>
        `;
    },

    show() {
        const view = document.getElementById(this.viewId);
        if (view) view.classList.add('active');
    },

    hide() {
        const view = document.getElementById(this.viewId);
        if (view) view.classList.remove('active');
    },

    destroy() {
        const view = document.getElementById(this.viewId);
        if (view) view.remove();
    },

    escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
};

(function registerWhenReady() {
    if (typeof window !== 'undefined' && window.app && typeof window.app.registerResourcePage === 'function') {
        window.app.registerResourcePage('custom_text', CustomText);
        return;
    }
    setTimeout(registerWhenReady, 60);
})();
