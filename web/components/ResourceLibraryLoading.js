/**
 * 卡片资源库公共加载状态。
 *
 * 调用方只负责提供库名称、提示文字和已处理数量；组件负责创建加载条、
 * 保持同一加载阶段的总数不回退，并同步列表的可见性与无障碍状态。
 */
const ResourceLibraryLoading = (() => {
    const states = new Map();

    const normalize_resource_type = (resource_type) => String(resource_type || '').trim();

    const get_list = (resource_type, options = {}) => {
        const list_id = String(options.list_id || `${resource_type}-list`).trim();
        return list_id ? document.getElementById(list_id) : null;
    };

    const ensure = (resource_type, options = {}) => {
        const type = normalize_resource_type(resource_type);
        if (!type) return null;
        const list = get_list(type, options);
        if (!list || !list.parentElement) return null;

        let loader = list.parentElement.querySelector(
            `.resource-inline-loading[data-resource-loading-for="${type}"]`
        );
        if (!loader) {
            loader = document.createElement('div');
            loader.className = 'resource-inline-loading';
            loader.dataset.resourceLoadingFor = type;
            loader.setAttribute('role', 'status');
            loader.setAttribute('aria-live', 'polite');
            loader.hidden = true;
            loader.innerHTML = `
                <div class="resource-inline-loading-copy">
                    <i class="ri-loader-4-line" aria-hidden="true"></i>
                    <span data-resource-loading-text></span>
                </div>
                <div class="resource-inline-loading-track" aria-hidden="true"><span></span></div>
                <div class="resource-inline-loading-count" data-resource-loading-count hidden></div>
            `;
            list.insertAdjacentElement('beforebegin', loader);
        }
        return { loader, list };
    };

    const render = (resource_type, options = {}) => {
        const type = normalize_resource_type(resource_type);
        const state = states.get(type);
        const elements = ensure(type, { list_id: state?.list_id || options.list_id });
        if (!state || !elements) return false;

        const { loader, list } = elements;
        const text = loader.querySelector('[data-resource-loading-text]');
        const count = loader.querySelector('[data-resource-loading-count]');
        const track = loader.querySelector('.resource-inline-loading-track');
        const show_content = options.show_content ?? state.show_content;
        state.show_content = show_content === true;
        const has_content = Array.from(list.children).some(
            child => !child.classList.contains('res-empty-state')
        );

        if (text) text.textContent = state.message;
        if (count) {
            count.hidden = state.processed === null;
            if (state.processed !== null) {
                count.textContent = state.total > 0
                    ? `${Math.min(state.processed, state.total)}/${state.total}`
                    : `已处理 ${state.processed} 项`;
            }
        }
        if (track) {
            const determinate = state.total > 0;
            const percent = determinate
                ? Math.max(0, Math.min(100, (state.processed || 0) / state.total * 100))
                : 0;
            track.classList.toggle('is-determinate', determinate);
            track.style.setProperty('--resource-loading-progress', `${percent}%`);
        }

        const show_list = state.show_content && has_content;
        loader.hidden = show_list;
        if (show_list) loader.style.setProperty('display', 'none', 'important');
        else loader.style.removeProperty('display');
        const block_content = !show_list;
        list.setAttribute('aria-busy', 'true');
        list.classList.toggle('is-resource-loading', block_content);
        list.hidden = block_content;
        if (block_content) {
            list.style.setProperty('display', 'none', 'important');
            list.setAttribute('aria-hidden', 'true');
        } else {
            list.style.removeProperty('display');
            list.removeAttribute('aria-hidden');
        }
        return true;
    };

    return {
        start(resource_type, options = {}) {
            const type = normalize_resource_type(resource_type);
            if (!type) return false;
            const incoming_total = Number(options.total);
            const incoming_processed = Number(options.processed);
            states.set(type, {
                list_id: String(options.list_id || `${type}-list`),
                message: String(options.message || '正在读取列表...'),
                processed: Number.isFinite(incoming_processed) && incoming_processed >= 0
                    ? Math.floor(incoming_processed)
                    : null,
                total: Number.isFinite(incoming_total) && incoming_total > 0
                    ? Math.floor(incoming_total)
                    : 0,
                show_content: options.show_content === true,
            });
            return render(type, options);
        },

        update(resource_type, options = {}) {
            const type = normalize_resource_type(resource_type);
            const state = states.get(type);
            if (!state) return this.start(type, options);

            if (options.message !== undefined) state.message = String(options.message || '');
            const incoming_processed = Number(options.processed);
            if (options.processed === null) state.processed = null;
            else if (Number.isFinite(incoming_processed) && incoming_processed >= 0) {
                state.processed = Math.floor(incoming_processed);
            }
            const incoming_total = Number(options.total);
            if (Number.isFinite(incoming_total) && incoming_total > 0) {
                state.total = Math.max(state.total, incoming_total);
            }
            return render(type, options);
        },

        finish(resource_type, options = {}) {
            const type = normalize_resource_type(resource_type);
            const state = states.get(type);
            const elements = ensure(type, { list_id: state?.list_id || options.list_id });
            if (!elements) return false;
            elements.loader.hidden = true;
            elements.loader.style.setProperty('display', 'none', 'important');
            elements.list.setAttribute('aria-busy', 'false');
            elements.list.classList.remove('is-resource-loading');
            elements.list.hidden = false;
            elements.list.style.removeProperty('display');
            elements.list.removeAttribute('aria-hidden');
            states.delete(type);
            return true;
        },
    };
})();

window.ResourceLibraryLoading = ResourceLibraryLoading;
