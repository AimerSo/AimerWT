/**
 * 模型库模块
 * 功能定位: 管理模型库的可视化卡片展示、编辑（重命名 / 封面）
 *
 * 输入输出:
 *   - 输入: 用户操作、后端 pywebview.api 数据
 *   - 输出: 渲染模型卡片列表、编辑弹窗交互
 *
 * 实现逻辑:
 *   - 通过 pywebview.api.get_models_list 拉取列表
 *   - 卡片悬浮时显示编辑按钮，复用裁切器修改封面
 *   - 编辑弹窗通过 JS 动态创建，不污染 index.html
 *
 * 业务关联:
 *   - 上游: resource_nav 导航切换（app.switchResourceView）
 *   - 下游: pywebview.api (get_models_list / rename_model / update_model_cover_data)
 */

const ModelLibrary = {
    name: '模型库',
    icon: 'ri-box-3-line',
    view_id: 'view-models',
    _loaded: false,
    _items: [],
    _search_query: '',
    _sort_key: 'update_time',
    _filter_status: 'all',
    _sort_asc: false,
    _render_seq: 0,
    _refreshing: false,
    _current_edit_name: null,

    init() {
        console.log('[ModelLibrary] 初始化');
        this._ensure_edit_modal();
        this._bind_card_events();
    },

    _t(key, params) {
        if (window.app && typeof app.t === 'function') return app.t(key, params);
        if (window.I18N && typeof I18N.t === 'function') return I18N.t(key, params);
        return key;
    },

    show() {
        const view = document.getElementById(this.view_id);
        if (view) view.classList.add('active');
        if (window.app && typeof app.updateResourceStorage === 'function') app.updateResourceStorage('models');
        if (!this._loaded) this.refresh_list();
    },

    hide() {
        const view = document.getElementById(this.view_id);
        if (view) view.classList.remove('active');
    },

    // ==================== 列表刷新 ====================

    async refresh_list(options = {}) {
        if (this._refreshing) return;
        this._refreshing = true;
        const list_el = document.getElementById('models-list');
        const count_el = document.getElementById('models-count');
        if (!list_el || !count_el) {
            this._refreshing = false;
            return;
        }

        const refresh_btn = document.getElementById('btn-refresh-models');
        if (refresh_btn) {
            refresh_btn.disabled = true;
            refresh_btn.classList.add('is-loading');
        }
        count_el.textContent = this._t('tools.count_refreshing');
        ResourceLibraryLoading.start('models', { message: '正在读取模型列表...', processed: 0, total: null, show_content: false });

        try {
            if (!window.pywebview?.api?.get_models_list) {
                this._render_empty_state(list_el, count_el);
                return;
            }

            const res = await pywebview.api.get_models_list({ force_refresh: !!options.manual });
            if (!res || !res.valid) {
                this._render_empty_state(list_el, count_el);
                return;
            }

            this._items = Array.isArray(res.items) ? res.items : [];
            const search_input = document.getElementById('models-search-input');
            const sort_select = document.getElementById('models-sort-select');
            if (search_input) this._search_query = search_input.value || '';
            if (sort_select) this._sort_key = sort_select.value || 'update_time';
            this._render_filtered_list({ replay: true, reason: options?.manual ? 'refresh' : 'initial' });
            if (window.app && typeof app.updateResourceStorage === 'function') app.updateResourceStorage('models');
            this._loaded = true;
        } catch (error) {
            console.error('[ModelLibrary] 刷新列表失败:', error);
            this._render_empty_state(list_el, count_el);
        } finally {
            this._refreshing = false;
            if (refresh_btn) {
                refresh_btn.disabled = false;
                refresh_btn.classList.remove('is-loading');
            }
        }
    },

    // ==================== 卡片渲染 ====================

    _render_card_list(container, items, reveal_options = {}) {
        const placeholder = 'assets/card_image_small.png';
        const CHUNK_SIZE = 24;
        let current_index = 0;
        const reveal_started_at = window.performance?.now?.() || Date.now();
        this._render_seq = (this._render_seq || 0) + 1;
        const render_seq = this._render_seq;
        ResourceLibraryLoading.start('models', {
            message: '正在载入模型卡片...',
            processed: 0,
            total: items.length,
            show_content: false,
        });
        container.innerHTML = '';

        const render_chunk = () => {
            if (render_seq !== this._render_seq) return;
            const chunk = items.slice(current_index, current_index + CHUNK_SIZE);
            const html = chunk.map(it => {
                const folder_name = String(it.name || '');
                const is_disabled = !!it.disabled || folder_name.endsWith(".AimerWT_BAN");
                const enabled_name = String(it.enabled_name || (is_disabled ? folder_name.replace(/\.AimerWT_BAN$/, "") : folder_name));
                const display_name = String(it.display_name || enabled_name);
                const cover = it.cover_url || placeholder;
                const is_default = !!it.cover_is_default;
                const size_text = this._format_bytes(it.size_bytes || 0);
                const safe_name = this._escape_html(folder_name);
                const safe_display_name = this._escape_html(display_name);
                const disabled_label = this._escape_html(this._t('resource.status_disabled'));
                const title_text = display_name === folder_name
                    ? String(it.path || '')
                    : `${display_name}\n${this._t('resource.original_folder_title', { name: folder_name })}\n${it.path || ''}`;

                return `
                    <div class="small-card animate-in${is_disabled ? ' is-disabled-resource' : ''}" title="${this._escape_html(title_text)}" data-item-name="${safe_name}" data-resource-name-encoded="${encodeURIComponent(folder_name)}" data-disabled="${is_disabled ? '1' : '0'}">
                        <div class="small-card-img-wrapper" style="position:relative;">
                             <img class="small-card-img${is_default ? ' is-default-cover' : ''} item-img-node"
                                  src="${cover}" loading="lazy" alt="">
                             ${is_disabled ? `<div class="resource-status-badge is-disabled">${disabled_label}</div>` : ''}
                             <div class="skin-edit-overlay">
                                 <button class="btn-v2 icon-only small secondary skin-edit-btn" type="button">
                                     <i class="ri-edit-line"></i>
                                 </button>
                             </div>
                        </div>
                        <div class="small-card-body">
                            <div class="skin-card-footer">
                                <div class="skin-card-name" title="${safe_display_name}">${safe_display_name}</div>
                                <div class="skin-card-size">${size_text}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            container.insertAdjacentHTML('beforeend', html);
            const new_items = Array.from(container.querySelectorAll('.small-card')).slice(current_index, current_index + chunk.length);
            if (window.app && typeof app.applyResourceReveal === 'function') {
                app.applyResourceReveal(container, {
                    items: new_items,
                    order_offset: current_index,
                    reveal_started_at,
                    max_animated: 32,
                    stagger_ms: 62.5,
                    reveal_window_ms: 2000,
                    duration_ms: 180,
                    defer_remaining: true,
                    once_key: 'models-list',
                    ...reveal_options,
                });
            }
            current_index += CHUNK_SIZE;
            const rendered_count = Math.min(current_index, items.length);
            ResourceLibraryLoading.update('models', {
                message: '正在载入模型卡片...',
                processed: rendered_count,
                total: items.length,
                show_content: rendered_count > 0,
            });

            if (current_index < items.length) {
                requestAnimationFrame(render_chunk);
            } else {
                if (window.app && typeof app.updateResourceSelectionSummary === 'function') {
                    app.updateResourceSelectionSummary('models', items.length);
                }
                ResourceLibraryLoading.finish('models');
            }
        };

        render_chunk();
    },

    filter_list(query) {
        this._search_query = String(query || '');
        this._render_filtered_list({ replay: true, reason: 'filter' });
    },

    sort_list(sort_key) {
        this._sort_key = sort_key || 'update_time';
        this._render_filtered_list({ replay: true, reason: 'sort' });
    },

    filter_status(value) {
        this._filter_status = value || 'all';
        this._render_filtered_list({ replay: true, reason: 'filter' });
    },

    toggle_sort_order() {
        this._sort_asc = !this._sort_asc;
        const btn = document.getElementById('models-sort-order-btn');
        if (btn) btn.classList.toggle('is-asc', this._sort_asc);
        this._render_filtered_list({ replay: true, reason: 'sort' });
    },

    _get_visible_items() {
        const query = String(this._search_query || '').trim().toLowerCase();
        let items = Array.isArray(this._items) ? this._items.slice() : [];

        /* 状态筛选 */
        const filter_status = this._filter_status || 'all';
        if (filter_status !== 'all') {
            items = items.filter(it => {
                const name = String(it.name || '');
                const is_disabled = !!it.disabled || name.endsWith('.AimerWT_BAN');
                return filter_status === 'disabled' ? is_disabled : !is_disabled;
            });
        }

        if (query) {
            items = items.filter(it => {
                const search_text = [
                    it.display_name,
                    it.folder_name || it.name,
                    it.name,
                    it.path,
                    it.preview_path,
                    it.file_count,
                    it.size_bytes
                ].filter(v => v !== null && v !== undefined).join(' ').toLowerCase();
                return search_text.includes(query);
            });
        }

        const sort_key = this._sort_key || 'update_time';
        const asc = !!this._sort_asc;
        items.sort((a, b) => {
            let cmp = 0;
            if (sort_key === 'name') {
                const a_name = String(a.display_name || a.name || '');
                const b_name = String(b.display_name || b.name || '');
                cmp = a_name.localeCompare(b_name, 'zh-CN', { numeric: true });
            } else if (sort_key === 'size') {
                cmp = Number(b.size_bytes || 0) - Number(a.size_bytes || 0);
            } else {
                const b_time = Number(b.mtime || 0) || (b.date ? new Date(b.date).getTime() : 0);
                const a_time = Number(a.mtime || 0) || (a.date ? new Date(a.date).getTime() : 0);
                cmp = b_time - a_time;
            }
            return asc ? -cmp : cmp;
        });

        return items;
    },

    _render_filtered_list(reveal_options = {}) {
        const list_el = document.getElementById('models-list');
        const count_el = document.getElementById('models-count');
        if (!list_el || !count_el) return;

        const items = this._get_visible_items();
        if (window.app && typeof app.updateResourceSelectionSummary === 'function') {
            app.updateResourceSelectionSummary('models', items.length);
        } else {
            count_el.textContent = this._t('resource.count_items', { count: items.length });
        }

        const select_all = document.getElementById('models-select-all');
        if (select_all) {
            select_all.checked = false;
            select_all.indeterminate = false;
        }

        if (items.length === 0) {
            ResourceLibraryLoading.finish('models');
            if (String(this._search_query || '').trim()) {
                list_el.innerHTML = `
                    <div class="res-empty-state">
                        <i class="${this.icon}"></i>
                        <h3>${this._t('resource.no_matching_models')}</h3>
                        <p>${this._t('resource.try_another_keyword')}</p>
                    </div>
                `;
                if (window.app && typeof app.applyResourceReveal === 'function') {
                    app.applyResourceReveal(list_el, {
                        item_selector: '.res-empty-state',
                        max_animated: 1,
                        once_key: 'models-list',
                        ...reveal_options,
                    });
                }
                return;
            }
            this._render_empty_state(list_el, count_el);
            return;
        }

        this._render_card_list(list_el, items, reveal_options);
    },

    _bind_card_events() {
        const container = document.getElementById('models-list');
        if (!container || container.dataset.editBound === '1') return;
        container.dataset.editBound = '1';
        container.addEventListener('click', (event) => {
            const button = event.target.closest('.skin-edit-btn');
            if (!button || !container.contains(button)) return;
            const card = button.closest('.small-card');
            const cover = card?.querySelector('.item-img-node')?.src || '';
            const item_name = card?.dataset.itemName || '';
            if (!item_name) return;
            this.open_edit_modal(item_name, cover);
        });
    },

    _render_empty_state(container, count_el) {
        if (container) {
            container.innerHTML = `
                <div class="res-empty-state">
                    <i class="ri-box-3-line"></i>
                    <h3>${this._t('tools.empty_models')}</h3>
                    <p>${this._t('tools.empty_models_desc')}</p>
                </div>
            `;
            if (window.app && typeof app.applyResourceReveal === 'function') {
                app.applyResourceReveal(container, {
                    item_selector: '.res-empty-state',
                    max_animated: 1,
                });
            }
        }
        if (window.app && typeof app.updateResourceSelectionSummary === 'function') {
            app.updateResourceSelectionSummary('models', 0);
        } else if (count_el) {
            count_el.textContent = this._t('resource.count_items', { count: 0 });
        }
        ResourceLibraryLoading.finish('models');
    },

    // ==================== 编辑弹窗 ====================

    _ensure_edit_modal() {
        if (document.getElementById('modal-edit-model')) return;
        const modal_html = `
            <div class="modal-overlay resource-edit-modal" id="modal-edit-model">
                <div class="modal-content skin-edit-dialog">
                    <div class="skin-edit-layout">
                        <div class="skin-edit-preview-panel">
                            <div class="skin-cover-edit skin-edit-cover" onclick="ModelLibrary.request_update_cover()">
                                <img id="edit-model-cover" src="" alt="${this._t('resource.cover_preview_alt')}">
                                <div class="cover-overlay skin-edit-cover-action">
                                    <span><i class="ri-upload-2-line"></i> ${this._t('resource.upload_cover')}</span>
                                </div>
                            </div>
                            <p class="skin-edit-cover-tip">${this._t('resource.cover_tip')}</p>
                            <div class="skin-rename-rule">
                                <strong><i class="ri-information-line"></i> ${this._t('resource.rename_rule_title')}</strong>
                                <span>${this._escape_html(this._t('resource.rename_rule_invalid_chars'))}</span>
                                <span>${this._t('resource.rename_rule_sync')}</span>
                            </div>
                        </div>
                        <div class="skin-edit-info-panel">
                            <h2>${this._t('resource.edit_model_title')}</h2>
                            <p class="subtitle">${this._t('resource.edit_model_subtitle')}</p>
                            <div class="skin-edit-tags" aria-label="${this._t('resource.category_model')}">
                                <span class="tag-local"><i class="ri-archive-line"></i> ${this._t('resource.local_resource')}</span>
                                <span class="tag-import"><i class="ri-upload-cloud-2-line"></i> ${this._t('resource.user_imported')}</span>
                            </div>
                            <div class="edit-skin-form">
                                <div class="form-group skin-edit-field">
                                    <label>${this._t('resource.display_name')}</label>
                                    <div class="skin-edit-input-wrap">
                                        <input type="text" id="edit-model-display-name" maxlength="32" placeholder="${this._t('resource.display_name_placeholder')}">
                                        <span id="edit-model-display-count">0/32</span>
                                    </div>
                                </div>
                                <div class="form-group skin-edit-field">
                                    <label>${this._t('resource.original_folder_name')}</label>
                                    <input type="text" id="edit-model-name" placeholder="${this._t('resource.folder_name_placeholder')}">
                                </div>
                            </div>
                            <div class="modal-actions">
                                <button class="btn secondary" onclick="app.closeModal('modal-edit-model')">${this._t('common.cancel')}</button>
                                <button class="btn primary" onclick="ModelLibrary.save_edit()">
                                    <i class="ri-save-line"></i> ${this._t('resource.save_changes')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modal_html);
    },

    open_edit_modal(item_name, cover_url) {
        this._ensure_edit_modal();
        this._current_edit_name = item_name;
        app._cropCoverTarget = 'model';
        const modal = document.getElementById('modal-edit-model');
        const display_input = document.getElementById('edit-model-display-name');
        const name_input = document.getElementById('edit-model-name');
        const cover_img = document.getElementById('edit-model-cover');
        if (!modal || !display_input || !name_input || !cover_img) return;

        const item = (this._items || []).find(it => it && it.name === item_name);
        display_input.value = item?.display_name || item_name;
        name_input.value = item?.folder_name || item_name;
        cover_img.src = cover_url || 'assets/coming_soon_img.png';
        this._update_display_name_count();
        if (display_input.dataset.countBound !== '1') {
            display_input.dataset.countBound = '1';
            display_input.addEventListener('input', () => this._update_display_name_count());
        }
        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    _update_display_name_count() {
        const input = document.getElementById('edit-model-display-name');
        const counter = document.getElementById('edit-model-display-count');
        if (!input || !counter) return;
        counter.textContent = `${String(input.value || '').length}/32`;
    },

    async save_edit() {
        if (!this._current_edit_name) return;
        const display_name = String(document.getElementById('edit-model-display-name')?.value || '').trim();
        const new_name = document.getElementById('edit-model-name').value.trim();
        if (!display_name) {
            app.showAlert(this._t('common.error'), this._t('resource.display_name_required'), 'error');
            return;
        }
        if (display_name.length > 32) {
            app.showAlert(this._t('common.error'), this._t('resource.display_name_too_long'), 'error');
            return;
        }
        if (!new_name) {
            app.showAlert(this._t('common.error'), this._t('resource.folder_name_required'), 'error');
            return;
        }

        if (new_name !== this._current_edit_name) {
            try {
                const res = await pywebview.api.rename_model(this._current_edit_name, new_name);
                if (res.success) {
                    this._current_edit_name = new_name;
                } else {
                    app.showAlert(this._t('common.failure'), this._t('tools.rename_failed', { message: res.msg }), 'error');
                    return;
                }
            } catch (e) {
                app.showAlert(this._t('common.error'), this._t('common.call_failed', { message: e }), 'error');
                return;
            }
        }

        try {
            const display_res = await pywebview.api.set_resource_display_name('models', this._current_edit_name, display_name);
            if (!display_res || !display_res.success) {
                app.showAlert(this._t('common.failure'), (display_res && display_res.msg) ? display_res.msg : this._t('resource.display_name_save_failed'), 'error');
                return;
            }
        } catch (e) {
            app.showAlert(this._t('common.error'), this._t('common.call_failed', { message: e }), 'error');
            return;
        }

        app.showAlert(this._t('common.success'), this._t('resource.model_info_saved'), 'success');
        app.closeModal('modal-edit-model');
        this.refresh_list();
    },

    request_update_cover() {
        if (!this._current_edit_name) return;
        app._cropCoverTarget = 'model';
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async () => {
            const file = input.files && input.files[0];
            if (!file) return;
            try {
                const data_url = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onerror = () => reject(new Error(this._t('common.read_image_failed')));
                    reader.onload = () => resolve(String(reader.result || ''));
                    reader.readAsDataURL(file);
                });
                app.openCropCoverModal(data_url);
            } catch (e) {
                console.error(e);
                app.showAlert(this._t('common.error'), this._t('common.read_image_failed'), 'error');
            }
        };
        input.click();
    },

    // ==================== 工具方法 ====================

    _escape_html(str) {
        if (app && typeof app._escapeHtml === 'function') return app._escapeHtml(str);
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    _format_bytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    },

    destroy() { }
};

// 绑定到全局 app 的刷新按钮入口
if (typeof app !== 'undefined') {
    app.refreshModels = function (opts) { ModelLibrary.refresh_list(opts); };
}

(function registerWhenReady() {
    if (typeof window !== 'undefined' && window.app && typeof window.app.registerResourcePage === 'function') {
        window.app.registerResourcePage('models', ModelLibrary);
        return;
    }
    setTimeout(registerWhenReady, 60);
})();
