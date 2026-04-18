/**
 * app.js - Main state machine and UI logic
 */

const VIEWS = {
    LIBRARY: 'library-view',
    NOVEL: 'novel-view',
    READER: 'reader-view'
};

const DEFAULT_SETTINGS = {
    theme: 'light',
    customBg: '',
    customText: '',
    fontFamily: 'Georgia, serif',
    fontSize: 18,
    lineHeight: 1.6,
    paragraphSpacing: 1.0,
    columnWidth: '70ch'
};

let currentState = {
    view: VIEWS.LIBRARY,
    novel: null,
    chapter: null,
    settings: { ...DEFAULT_SETTINGS },
    filter: {
        includeTags: [],
        excludeTags: [],
        sortBy: 'title'
    }
};

// --- API Module ---
const api = {
    async fetch(url, options = {}) {
        const resp = await fetch(url, options);
        if (!resp.ok) throw new Error(`API Error: ${resp.status}`);
        return resp.json();
    },
    getNovels: (params = {}) => {
        const query = new URLSearchParams();
        if (params.include_tags) params.include_tags.forEach(t => query.append('include_tags', t));
        if (params.exclude_tags) params.exclude_tags.forEach(t => query.append('exclude_tags', t));
        if (params.sort_by) query.append('sort_by', params.sort_by);
        return api.fetch(`/api/novels?${query.toString()}`);
    },
    getTags: () => api.fetch('/api/tags'),
    getNovel: (id) => api.fetch(`/api/novels/${id}`),
    getChapter: (id) => api.fetch(`/api/chapters/${id}`),
    search: (q) => api.fetch(`/api/search?q=${encodeURIComponent(q)}`),
    getProgress: () => api.fetch('/api/progress'),
    updateProgress: (data) => api.fetch('/api/progress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    getBookmarks: () => api.fetch('/api/bookmarks'),
    createBookmark: (data) => api.fetch('/api/bookmarks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    deleteBookmark: (id) => api.fetch(`/api/bookmarks/${id}`, { method: 'DELETE' }),
    getNote: (chapterId) => api.fetch(`/api/notes/${chapterId}`),
    updateNote: (data) => api.fetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    fetchChapters: (id) => api.fetch(`/api/novels/${id}/fetch-chapters`, { method: 'POST' }),
    updateChapters: (id) => api.fetch(`/api/novels/${id}/update-chapters`, { method: 'POST' }),
    getFetchStatus: (id) => api.fetch(`/api/novels/${id}/fetch-status`)
};

// --- Utils ---
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove('hidden');
const hide = (el) => el.classList.add('hidden');

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// --- Settings & Theme ---
function loadSettings() {
    const saved = localStorage.getItem('reader_settings');
    if (saved) {
        currentState.settings = { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
    }
    applySettings();
}

function saveSettings() {
    localStorage.setItem('reader_settings', JSON.stringify(currentState.settings));
    applySettings();
}

function applySettings() {
    const s = currentState.settings;
    const root = document.documentElement;

    root.setAttribute('data-theme', s.theme);
    root.style.setProperty('--font-size', s.fontSize + 'px');
    root.style.setProperty('--line-height', s.lineHeight);
    root.style.setProperty('--paragraph-spacing', s.paragraphSpacing + 'em');
    root.style.setProperty('--font-family', s.fontFamily);
    root.style.setProperty('--content-width', s.columnWidth);

    // Update labels
    if ($('font-size-label')) $('font-size-label').textContent = s.fontSize + 'px';
    if ($('line-height-label')) $('line-height-label').textContent = s.lineHeight;
    if ($('para-spacing-label')) $('para-spacing-label').textContent = s.paragraphSpacing + 'em';
    if ($('column-width-label')) $('column-width-label').textContent = s.columnWidth;

    if (s.customBg) root.style.setProperty('--bg-primary', s.customBg);
    else root.style.removeProperty('--bg-primary');

    if (s.customText) root.style.setProperty('--text-primary', s.customText);
    else root.style.removeProperty('--text-primary');

    root.style.setProperty('--font-family', s.fontFamily);
    root.style.setProperty('--font-size', `${s.fontSize}px`);
    root.style.setProperty('--line-height', s.lineHeight);
    root.style.setProperty('--paragraph-spacing', `${s.paragraphSpacing}em`);
    root.style.setProperty('--content-width', s.columnWidth);

    // Update UI controls
    $('font-size-label').textContent = `${s.fontSize}px`;
    $('line-height-label').textContent = s.lineHeight;
    $('para-spacing-label').textContent = `${s.paragraphSpacing}em`;
    $('column-width-label').textContent = s.columnWidth;

    $('font-size-range').value = s.fontSize;
    $('line-height-range').value = s.lineHeight;
    $('para-spacing-range').value = s.paragraphSpacing;
    $('font-family-select').value = s.fontFamily;
    $('column-width-range').value = parseInt(s.columnWidth);
    $('bg-color-picker').value = getComputedStyle(root).getPropertyValue('--bg-primary').trim();
    $('text-color-picker').value = getComputedStyle(root).getPropertyValue('--text-primary').trim();
}

// --- Navigation ---
async function navigateTo(view, params = {}) {
    // Hide all views
    Object.values(VIEWS).forEach(v => hide($(v)));
    show($(view));
    currentState.view = view;

    if (view === VIEWS.LIBRARY) {
        await renderLibrary();
    } else if (view === VIEWS.NOVEL) {
        await renderNovel(params.id);
    } else if (view === VIEWS.READER) {
        await renderReader(params.id);
    }
    window.scrollTo(0, 0);
}

// --- View Rendering ---
let allTags = [];

async function renderLibrary() {
    if (allTags.length === 0) {
        allTags = await api.getTags();
        renderTagFilters();
    }

    const novels = await api.getNovels({
        include_tags: currentState.filter.includeTags,
        exclude_tags: currentState.filter.excludeTags,
        sort_by: currentState.filter.sortBy
    });

    const grid = $('novel-grid');
    grid.innerHTML = '';

    novels.forEach(n => {
        const card = document.createElement('div');
        card.className = 'novel-card';
        const progress = n.chapter_count > 0 ? (n.chapters_read / n.chapter_count) * 100 : 0;

        const initials = n.title.split(' ').map(w => w[0]).join('').substring(0, 3).toUpperCase();

        card.innerHTML = `
            ${n.cover_path ? `<img src="/api/covers/${n.id}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">` : ''}
            <div class="placeholder-cover" style="${n.cover_path ? 'display:none' : 'display:flex'}">${initials}</div>
            <div class="novel-card-info">
                <h3>${n.title}</h3>
                <p>${n.author || 'Unknown Author'}</p>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: ${progress}%"></div>
                </div>
                <p style="font-size: 0.75rem; margin-top: 5px">${n.chapters_read} / ${n.chapter_count} read</p>
            </div>
        `;
        card.onclick = () => navigateTo(VIEWS.NOVEL, { id: n.id });
        grid.appendChild(card);
    });
}

function renderTagFilters() {
    const section = $('tag-filter-section');

    // Remove everything inside the section and rebuild from scratch.
    // This avoids the conflict with the hardcoded <h4> in index.html
    // and prevents duplicate headers on subsequent calls.
    section.innerHTML = '';

    // --- Collapsible header ---
    const header = document.createElement('div');
    header.className = 'tag-panel-header';
    header.style.cursor = 'pointer';
    header.style.marginBottom = '8px';
    header.style.fontWeight = 'bold';
    header.style.display = 'flex';
    header.style.alignItems = 'center';

    const title = document.createElement('h4');
    title.id = 'tag-panel-title';
    title.style.margin = '0';
    header.appendChild(title);
    section.appendChild(header);

    // --- Tag container ---
    const container = document.createElement('div');
    container.id = 'tag-filter-container';
    container.className = 'tag-filter-container';
    section.appendChild(container);

    // --- Collapse toggle ---
    const setTagPanelState = (open) => {
        container.style.display = open ? 'flex' : 'none';
        title.textContent = open ? 'Filter by Tags ▼' : 'Filter by Tags ▶';
        localStorage.setItem('tagPanelOpen', String(open));
    };

    header.onclick = () => {
        const isOpen = container.style.display !== 'none';
        setTagPanelState(!isOpen);
    };

    // Default state: collapsed unless active filters or user previously opened it
    const hasActiveFilters = currentState.filter.includeTags.length > 0 || currentState.filter.excludeTags.length > 0;
    const savedState = localStorage.getItem('tagPanelOpen');
    setTagPanelState(hasActiveFilters || savedState === 'true');

    // --- Render tag chips ---
    // allTags items are objects: { name: string, count: number }
    allTags.forEach(tagObj => {
        const tag = tagObj.name;       // always a plain string from here on
        const count = tagObj.count;

        const el = document.createElement('span');
        el.className = 'filter-tag';
        if (currentState.filter.includeTags.includes(tag)) el.classList.add('include');
        if (currentState.filter.excludeTags.includes(tag)) el.classList.add('exclude');

        el.textContent = `${tag} (${count})`;

        el.onclick = (e) => {
            e.stopPropagation();
            if (el.classList.contains('include')) {
                el.classList.remove('include');
                el.classList.add('exclude');
                currentState.filter.includeTags = currentState.filter.includeTags.filter(t => t !== tag);
                currentState.filter.excludeTags.push(tag);
            } else if (el.classList.contains('exclude')) {
                el.classList.remove('exclude');
                currentState.filter.excludeTags = currentState.filter.excludeTags.filter(t => t !== tag);
            } else {
                el.classList.add('include');
                currentState.filter.includeTags.push(tag);
            }
            renderLibrary();
        };

        container.appendChild(el);
    });
}

async function renderNovel(id) {
    const novel = await api.getNovel(id);
    currentState.novel = novel;

    const details = $('novel-details');
    const initials = (novel.title || '').split(' ').map(w => w[0]).join('').substring(0, 3).toUpperCase();

    // novel.tags comes from /api/novels/{id} which returns plain strings — safe to use directly
    const tagsHtml = (novel.tags || []).map(t => {
        const name = typeof t === 'object' ? t.name : t;
        return `<span class="tag">${name}</span>`;
    }).join('');

    details.innerHTML = `
        <div class="novel-cover-wrapper">
            ${novel.cover_path ? `<img src="/api/covers/${novel.id}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">` : ''}
            <div class="placeholder-cover" style="${novel.cover_path ? 'display:none' : 'display:flex'}; width:250px">${initials}</div>
        </div>
        <div class="novel-info-text">
            <h2>${novel.title}</h2>
            <p><strong>Author:</strong> ${novel.author || 'Unknown'}</p>
            <p><strong>Status:</strong> ${novel.status}</p>
            <p><strong>Content:</strong> ${novel.content_status || 'metadata'}</p>
            <div class="novel-actions" style="margin: 15px 0">
                <button id="continue-reading-btn" class="primary-btn">Continue Reading</button>
            </div>
            <div class="tags">${tagsHtml}</div>
            <div class="synopsis">${novel.synopsis || 'No synopsis available.'}</div>
            
            <div id="chapter-actions" class="chapter-actions" style="margin: 20px 0; padding: 15px; background: var(--bg-secondary); border-radius: 8px;">
                <!-- Button injected here -->
            </div>
        </div>
    `;

    renderChapterActionButton(novel);

    const list = $('chapter-list');
    list.innerHTML = '';
    (novel.chapters || []).forEach(ch => {
        const li = document.createElement('li');
        li.className = 'chapter-item';
        li.innerHTML = `
            <span class="read-dot ${ch.is_read ? 'visible' : ''}"></span>
            <span>${ch.chapter_title}</span>
        `;
        li.onclick = () => navigateTo(VIEWS.READER, { id: ch.id });
        list.appendChild(li);
    });

    $('continue-reading-btn').onclick = async () => {
        const allProgress = await api.getProgress();
        const novelProgress = allProgress
            .filter(p => p.novel_id === novel.id)
            .sort((a, b) => new Date(b.read_at) - new Date(a.read_at));

        if (novelProgress.length > 0) {
            navigateTo(VIEWS.READER, { id: novelProgress[0].chapter_id });
        } else if (novel.chapters && novel.chapters.length > 0) {
            navigateTo(VIEWS.READER, { id: novel.chapters[0].id });
        }
    };
}

let fetchStatusInterval = null;

function renderChapterActionButton(novel) {
    const container = $('chapter-actions');
    if (!container) return;

    if (fetchStatusInterval) {
        clearInterval(fetchStatusInterval);
        fetchStatusInterval = null;
    }

    const status = novel.content_status || 'metadata';

    if (status === 'discovered' || status === 'metadata') {
        container.innerHTML = `<button id="fetch-chapters-btn" class="primary-btn">Download Chapters</button>`;
        $('fetch-chapters-btn').onclick = async () => {
            await api.fetchChapters(novel.id);
            startPollingFetchStatus(novel.id);
        };
    } else if (status === 'full') {
        container.innerHTML = `<button id="update-chapters-btn" class="primary-btn">Update Chapters</button>`;
        $('update-chapters-btn').onclick = async () => {
            await api.updateChapters(novel.id);
            startPollingFetchStatus(novel.id);
        };
    }
}

function startPollingFetchStatus(novelId) {
    const container = $('chapter-actions');
    container.innerHTML = `
        <div class="fetch-progress">
            <p id="fetch-status-text">Refreshing metadata...</p>
            <div class="progress-bar-container" style="margin-top: 10px">
                <div id="fetch-progress-fill" class="progress-bar-fill" style="width: 0%"></div>
            </div>
        </div>
    `;

    const startTime = Date.now();
    fetchStatusInterval = setInterval(async () => {
        try {
            const data = await api.getFetchStatus(novelId);
            const text = $('fetch-status-text');
            const fill = $('fetch-progress-fill');

            if (text && fill) {
                const elapsed = (Date.now() - startTime) / 1000;
                const progress = data.total_chapters > 0 ? (data.downloaded_chapters / data.total_chapters) * 100 : 0;

                if (data.downloaded_chapters > 0 || elapsed > 10) {
                    text.textContent = `Downloading... ${data.downloaded_chapters} / ${data.total_chapters} chapters`;
                } else {
                    text.textContent = 'Refreshing metadata...';
                }

                fill.style.width = `${progress}%`;

                if (data.downloaded_chapters >= data.total_chapters && data.content_status === 'full') {
                    clearInterval(fetchStatusInterval);
                    fetchStatusInterval = null;
                    text.textContent = '✓ Download complete';
                    setTimeout(() => {
                        navigateTo(VIEWS.NOVEL, { id: novelId });
                    }, 3000);
                }
            }
        } catch (e) {
            console.error("Polling error:", e);
            clearInterval(fetchStatusInterval);
        }
    }, 3000);
}

let scrollSaveTimeout = null;
let lastScrollY = 0;

async function renderReader(id) {
    const chapter = await api.getChapter(id);
    currentState.chapter = chapter;

    // Update UI
    $('reader-title').textContent = `${currentState.novel ? currentState.novel.title + ' > ' : ''}${chapter.chapter_title}`;

    const contentEl = $('chapter-content');
    if (chapter.content_type === 'plain') {
        const html = chapter.content.split(/\n\n+/).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
        contentEl.innerHTML = html;
    } else {
        contentEl.innerHTML = chapter.content;
    }

    // Meta info
    const readingTime = Math.ceil(chapter.word_count / 250);
    const timeEl = document.createElement('p');
    timeEl.style.textAlign = 'center';
    timeEl.style.fontStyle = 'italic';
    timeEl.style.color = 'var(--text-secondary)';
    timeEl.textContent = `${chapter.word_count} words • ~${readingTime} min read`;
    contentEl.prepend(timeEl);

    // Navigation buttons
    const updateNav = (btn, targetId) => {
        btn.onclick = () => targetId ? navigateTo(VIEWS.READER, { id: targetId }) : null;
        btn.disabled = !targetId;
        btn.style.opacity = targetId ? 1 : 0.3;
    };

    updateNav($('prev-ch-btn-top'), chapter.prev_chapter_id);
    updateNav($('next-ch-btn-top'), chapter.next_chapter_id);
    updateNav($('prev-ch-btn-bottom'), chapter.prev_chapter_id);
    updateNav($('next-ch-btn-bottom'), chapter.next_chapter_id);

    // Progress info
    if (currentState.novel) {
        const idx = currentState.novel.chapters.findIndex(c => c.id === chapter.id);
        $('chapter-index-info').textContent = `Chapter ${idx + 1} of ${currentState.novel.chapters.length}`;
    }

    // Restore scroll
    const allProgress = await api.getProgress();
    const prog = allProgress.find(p => p.chapter_id === id);
    if (prog && prog.scroll_position < 0.99) {
        setTimeout(() => {
            window.scrollTo(0, prog.scroll_position * document.body.scrollHeight);
        }, 100);
    }

    // Bookmark status
    updateBookmarkIcon();
    // Note status
    updateNoteIcon();
}

// --- Feature Logic ---

async function updateBookmarkIcon() {
    const bookmarks = await api.getBookmarks();
    const existing = bookmarks.find(b => b.chapter_id === currentState.chapter.id);
    $('bookmark-btn').style.color = existing ? 'var(--accent)' : 'inherit';
}

async function updateNoteIcon() {
    const note = await api.getNote(currentState.chapter.id);
    $('notes-btn').textContent = note.content ? '📝✅' : '📝';
}

function handleScroll() {
    if (currentState.view !== VIEWS.READER || !currentState.chapter) return;

    const scrollPos = window.scrollY / (document.body.scrollHeight - window.innerHeight || 1);

    if (Math.abs(window.scrollY - lastScrollY) > 50) {
        lastScrollY = window.scrollY;

        clearTimeout(scrollSaveTimeout);
        scrollSaveTimeout = setTimeout(() => {
            api.updateProgress({
                novel_id: currentState.chapter.novel_id,
                chapter_id: currentState.chapter.id,
                scroll_position: scrollPos >= 0.9 ? 1.0 : scrollPos
            });
            $('reader-progress-bar').style.width = `${scrollPos * 100}%`;
        }, 2000);
    }
}

// --- Event Listeners ---

window.addEventListener('scroll', handleScroll);

document.querySelectorAll('.back-btn').forEach(btn => {
    btn.onclick = () => navigateTo(VIEWS[btn.dataset.target]);
});

// Settings Panel
$('settings-btn').onclick = () => {
    $('settings-panel').classList.toggle('hidden');
    hide($('notes-panel'));
};

$('close-settings-btn').onclick = () => hide($('settings-panel'));

document.querySelectorAll('.theme-presets button').forEach(btn => {
    btn.onclick = () => {
        currentState.settings.theme = btn.dataset.theme;
        currentState.settings.customBg = '';
        currentState.settings.customText = '';
        saveSettings();
    };
});

$('bg-color-picker').oninput = (e) => {
    currentState.settings.customBg = e.target.value;
    saveSettings();
};
$('text-color-picker').oninput = (e) => {
    currentState.settings.customText = e.target.value;
    saveSettings();
};
$('font-family-select').onchange = (e) => {
    currentState.settings.fontFamily = e.target.value;
    saveSettings();
};
$('font-size-range').oninput = (e) => {
    currentState.settings.fontSize = parseInt(e.target.value);
    saveSettings();
};
$('line-height-range').oninput = (e) => {
    currentState.settings.lineHeight = parseFloat(e.target.value);
    saveSettings();
};
$('para-spacing-range').oninput = (e) => {
    currentState.settings.paragraphSpacing = parseFloat(e.target.value);
    saveSettings();
};
$('column-width-range').oninput = (e) => {
    currentState.settings.columnWidth = `${e.target.value}ch`;
    saveSettings();
};
$('reset-settings-btn').onclick = () => {
    currentState.settings = { ...DEFAULT_SETTINGS };
    saveSettings();
};

// Sort
$('sort-select').onchange = (e) => {
    currentState.filter.sortBy = e.target.value;
    renderLibrary();
};

// Bookmarks
$('bookmark-btn').onclick = async () => {
    const bookmarks = await api.getBookmarks();
    const existing = bookmarks.find(b => b.chapter_id === currentState.chapter.id);

    if (existing) {
        await api.deleteBookmark(existing.id);
    } else {
        await api.createBookmark({
            novel_id: currentState.chapter.novel_id,
            chapter_id: currentState.chapter.id,
            label: currentState.chapter.chapter_title,
            scroll_position: window.scrollY / document.body.scrollHeight
        });
    }
    updateBookmarkIcon();
};

// Notes
$('notes-btn').onclick = async () => {
    const panel = $('notes-panel');
    panel.classList.toggle('hidden');
    hide($('settings-panel'));

    if (!panel.classList.contains('hidden')) {
        const note = await api.getNote(currentState.chapter.id);
        $('note-textarea').value = note.content;
    }
};

$('note-textarea').oninput = debounce(async (e) => {
    await api.updateNote({
        chapter_id: currentState.chapter.id,
        content: e.target.value
    });
    updateNoteIcon();
}, 500);

// Search
const toggleSearch = () => {
    const modal = $('search-modal');
    modal.classList.toggle('hidden');
    if (!modal.classList.contains('hidden')) {
        $('global-search-input').focus();
    }
};

$('search-toggle-btn').onclick = toggleSearch;

$('global-search-input').oninput = debounce(async (e) => {
    const q = e.target.value;
    if (q.length < 2) return;
    const results = await api.search(q);

    const nResults = $('novel-results');
    nResults.innerHTML = results.novels.map(n => `
        <div class="search-result-item" onclick="app.navToNovel(${n.id})">${n.title}</div>
    `).join('');

    const cResults = $('chapter-results');
    cResults.innerHTML = results.chapters.map(c => `
        <div class="search-result-item" onclick="app.navToChapter(${c.id})">${c.chapter_title}</div>
    `).join('');
}, 300);

// Global shortcut exposure for search results
window.app = {
    navToNovel: (id) => { hide($('search-modal')); navigateTo(VIEWS.NOVEL, { id }); },
    navToChapter: (id) => { hide($('search-modal')); navigateTo(VIEWS.READER, { id }); }
};

// Keyboard Shortcuts
window.onkeydown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        toggleSearch();
    }

    if (currentState.view === VIEWS.READER) {
        if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

        if (e.key === 'ArrowRight' || e.key === 'l') $('next-ch-btn-top').click();
        if (e.key === 'ArrowLeft' || e.key === 'h') $('prev-ch-btn-top').click();
        if (e.key === 'b') $('bookmark-btn').click();
        if (e.key === 'n') $('notes-btn').click();
        if (e.key === 's') $('settings-btn').click();
        if (e.key === 'f') {
            if (!document.fullscreenElement) document.documentElement.requestFullscreen();
            else document.exitFullscreen();
        }
        if (e.key === 'Escape') {
            hide($('settings-panel'));
            hide($('notes-panel'));
            hide($('search-modal'));
        }
    }
};

// Initialization
loadSettings();
navigateTo(VIEWS.LIBRARY);