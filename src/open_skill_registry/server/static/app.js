/**
 * Open Skill Registry - Frontend Web UI Logic
 * Handles catalog discovery, live search, skill inspection, and drag-and-drop uploads.
 */

(function () {
  'use strict';

  // --- State ---
  let allSkills = [];
  let currentSkill = null;
  let selectedFile = null;
  let searchDebounceTimer = null;

  // --- DOM Elements ---
  const elements = {
    // Header & Search
    searchInput: document.getElementById('search-input'),
    searchClearBtn: document.getElementById('search-clear-btn'),
    openUploadBtn: document.getElementById('open-upload-btn'),

    // Main & Catalog
    catalogTitle: document.getElementById('catalog-title'),
    skillsCount: document.getElementById('skills-count'),
    catalogGrid: document.getElementById('catalog-grid'),
    loadingSpinner: document.getElementById('loading-spinner'),
    errorState: document.getElementById('error-state'),
    errorMessage: document.getElementById('error-message'),
    retryBtn: document.getElementById('retry-btn'),
    emptyState: document.getElementById('empty-state'),
    emptyTitle: document.getElementById('empty-title'),
    emptyMessage: document.getElementById('empty-message'),
    emptyPublishBtn: document.getElementById('empty-publish-btn'),

    // Detail Modal
    detailModal: document.getElementById('detail-modal'),
    closeDetailModal: document.getElementById('close-detail-modal'),
    detailCloseFooterBtn: document.getElementById('detail-close-footer-btn'),
    modalSkillName: document.getElementById('modal-skill-name'),
    modalNamespace: document.getElementById('modal-namespace'),
    modalVisibility: document.getElementById('modal-visibility'),
    modalVersionBadge: document.getElementById('modal-version-badge'),
    modalSlug: document.getElementById('modal-slug'),
    modalDescription: document.getElementById('modal-description'),
    modalVersionSelect: document.getElementById('modal-version-select'),
    modalDownloads: document.getElementById('modal-downloads'),
    modalContentHash: document.getElementById('modal-content-hash'),
    copyHashBtn: document.getElementById('copy-hash-btn'),
    modalTags: document.getElementById('modal-tags'),
    modalInstructions: document.getElementById('modal-instructions'),
    modalFilesList: document.getElementById('modal-files-list'),
    cliPullCommand: document.getElementById('cli-pull-command'),
    copyCliBtn: document.getElementById('copy-cli-btn'),

    // Upload Modal
    uploadModal: document.getElementById('upload-modal'),
    closeUploadModal: document.getElementById('close-upload-modal'),
    cancelUploadBtn: document.getElementById('cancel-upload-btn'),
    uploadForm: document.getElementById('upload-form'),
    uploadDropzone: document.getElementById('upload-dropzone'),
    fileInput: document.getElementById('file-input'),
    dropzonePrompt: document.getElementById('dropzone-prompt'),
    dropzoneFileInfo: document.getElementById('dropzone-file-info'),
    selectedFileName: document.getElementById('selected-file-name'),
    selectedFileSize: document.getElementById('selected-file-size'),
    removeFileBtn: document.getElementById('remove-file-btn'),
    uploadNamespace: document.getElementById('upload-namespace'),
    uploadSlug: document.getElementById('upload-slug'),
    uploadVersion: document.getElementById('upload-version'),
    uploadVisibility: document.getElementById('upload-visibility'),
    publishBtn: document.getElementById('publish-btn'),
    uploadStatus: document.getElementById('upload-status'),
    uploadStatusText: document.getElementById('upload-status-text'),
    uploadSuccess: document.getElementById('upload-success'),
    uploadSuccessDetails: document.getElementById('upload-success-details'),
    uploadError: document.getElementById('upload-error'),
    uploadErrorText: document.getElementById('upload-error-text'),

    // Toast
    toastContainer: document.getElementById('toast-container'),
  };

  // --- Markdown Renderer ---
  function renderMarkdown(md) {
    if (!md) return '<p class="placeholder-text">No instructions provided.</p>';

    // Escape HTML
    let text = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Code blocks ```code```
    text = text.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, function (_, lang, code) {
      return '<pre><code class="language-' + lang + '">' + code.trim() + '</code></pre>';
    });

    // Inline code `code`
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headers
    text = text.replace(/^###### (.*$)/gim, '<h6>$1</h6>');
    text = text.replace(/^##### (.*$)/gim, '<h5>$1</h5>');
    text = text.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
    text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Blockquotes
    text = text.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

    // Horizontal rules
    text = text.replace(/^---$/gim, '<hr>');

    // Bold & Italic
    text = text.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/___(.*?)___/g, '<strong><em>$1</em></strong>');
    text = text.replace(/__(.*?)__/g, '<strong>$1</strong>');
    text = text.replace(/_(.*?)_/g, '<em>$1</em>');

    // Links: [text](url) - only http/https/relative to avoid javascript:
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // Unordered lists
    text = text.replace(/^\s*[-*]\s+(.*)$/gim, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>(\n|.)*?)(?=(<h|<p|<pre|<blockquote|<hr|$))/g, function (match) {
      if (!match.includes('<ul>')) {
        return '<ul>' + match + '</ul>';
      }
      return match;
    });

    // Paragraphs
    const blocks = text.split(/\n{2,}/);
    return blocks
      .map(function (block) {
        block = block.trim();
        if (!block) return '';
        if (
          block.startsWith('<h') ||
          block.startsWith('<pre') ||
          block.startsWith('<ul') ||
          block.startsWith('<ol') ||
          block.startsWith('<blockquote') ||
          block.startsWith('<hr')
        ) {
          return block;
        }
        return '<p>' + block.replace(/\n/g, '<br>') + '</p>';
      })
      .join('\n');
  }

  // --- Helpers ---
  function formatBytes(bytes) {
    if (bytes === 0 || !bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = '<span>' + (type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ️') + '</span><span>' + message + '</span>';
    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function setElementVisibility(elem, isVisible) {
    if (!elem) return;
    if (isVisible) {
      elem.classList.remove('hidden');
    } else {
      elem.classList.add('hidden');
    }
  }

  // --- API Calls ---

  async function loadCatalog() {
    setElementVisibility(elements.loadingSpinner, true);
    setElementVisibility(elements.errorState, false);
    setElementVisibility(elements.emptyState, false);
    elements.catalogGrid.innerHTML = '';
    elements.catalogTitle.textContent = 'Skill Catalog';

    try {
      const resp = await fetch('/api/v1/skills');
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: Failed to fetch skills`);
      }
      const json = await resp.json();
      const pageData = json.data || {};
      const skills = pageData.items || [];
      allSkills = skills;

      setElementVisibility(elements.loadingSpinner, false);
      renderCatalog(skills);
    } catch (err) {
      console.error('Error loading catalog:', err);
      setElementVisibility(elements.loadingSpinner, false);
      setElementVisibility(elements.errorState, true);
      elements.errorMessage.textContent = err.message || 'Could not connect to the registry server.';
    }
  }

  async function searchSkills(query) {
    if (!query || !query.trim()) {
      elements.searchClearBtn.classList.add('hidden');
      loadCatalog();
      return;
    }

    elements.searchClearBtn.classList.remove('hidden');
    setElementVisibility(elements.loadingSpinner, true);
    setElementVisibility(elements.errorState, false);
    setElementVisibility(elements.emptyState, false);
    elements.catalogGrid.innerHTML = '';
    elements.catalogTitle.textContent = `Results for "${query.trim()}"`;

    try {
      const resp = await fetch(`/api/v1/skills/search?q=${encodeURIComponent(query.trim())}`);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: Search request failed`);
      }
      const json = await resp.json();
      const data = json.data || {};
      const items = data.items || [];

      setElementVisibility(elements.loadingSpinner, false);
      renderCatalog(items, true, query.trim());
    } catch (err) {
      console.error('Error searching skills:', err);
      setElementVisibility(elements.loadingSpinner, false);
      setElementVisibility(elements.errorState, true);
      elements.errorMessage.textContent = err.message || 'Search failed.';
    }
  }

  function renderCatalog(skills, isSearch = false, query = '') {
    elements.skillsCount.textContent = `${skills.length} ${skills.length === 1 ? 'skill' : 'skills'}`;

    if (!skills || skills.length === 0) {
      setElementVisibility(elements.emptyState, true);
      if (isSearch) {
        elements.emptyTitle.textContent = 'No matching skills found';
        elements.emptyMessage.textContent = `We couldn't find any skills matching "${query}". Try different keywords.`;
        setElementVisibility(elements.emptyPublishBtn, false);
      } else {
        elements.emptyTitle.textContent = 'No skills published yet';
        elements.emptyMessage.textContent = 'Be the first to publish an agent skill to this registry.';
        setElementVisibility(elements.emptyPublishBtn, true);
      }
      return;
    }

    setElementVisibility(elements.emptyState, false);

    skills.forEach(skill => {
      const card = document.createElement('div');
      card.className = 'skill-card';
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
      card.setAttribute('aria-label', `View details for skill ${skill.name}`);

      const version = skill.version || skill.latest_version || '1.0.0';
      const visibility = skill.visibility || 'PUBLIC';
      const tags = Array.isArray(skill.tags) ? skill.tags : [];

      card.innerHTML = `
        <div class="card-header">
          <div class="card-title-group">
            <h3 class="card-title" title="${escapeHtml(skill.name)}">${escapeHtml(skill.name)}</h3>
            <span class="card-slug">${escapeHtml(skill.namespace)}/${escapeHtml(skill.slug)}</span>
          </div>
          <span class="pill pill-visibility" data-vis="${escapeHtml(visibility)}">${escapeHtml(visibility)}</span>
        </div>
        <p class="card-description">${escapeHtml(skill.description || 'No description provided.')}</p>
        <div class="card-tags">
          ${tags.slice(0, 4).map(t => `<span class="pill tag-pill">${escapeHtml(t)}</span>`).join('')}
          ${tags.length > 4 ? `<span class="pill tag-pill">+${tags.length - 4}</span>` : ''}
        </div>
        <div class="card-footer">
          <div class="card-stats">
            <span class="stat-item" title="Downloads">📥 ${skill.download_count || 0}</span>
            <span class="pill pill-version">v${escapeHtml(version)}</span>
          </div>
          <span class="pill pill-namespace">${escapeHtml(skill.namespace)}</span>
        </div>
      `;

      card.addEventListener('click', () => openSkillDetail(skill.namespace, skill.slug));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openSkillDetail(skill.namespace, skill.slug);
        }
      });

      elements.catalogGrid.appendChild(card);
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- Skill Detail Modal ---

  async function openSkillDetail(namespace, slug) {
    setElementVisibility(elements.detailModal, true);
    document.body.style.overflow = 'hidden';

    // Reset fields to loading state
    elements.modalSkillName.textContent = 'Loading...';
    elements.modalNamespace.textContent = namespace;
    elements.modalSlug.textContent = `${namespace}/${slug}`;
    elements.modalDescription.textContent = '';
    elements.modalVersionBadge.textContent = '...';
    elements.modalDownloads.textContent = '...';
    elements.modalContentHash.textContent = 'Loading hash...';
    elements.modalTags.innerHTML = '';
    elements.modalVersionSelect.innerHTML = '<option>Loading...</option>';
    elements.modalInstructions.innerHTML = '<p class="placeholder-text">Loading instructions...</p>';
    elements.modalFilesList.innerHTML = '<li class="file-item">Loading package files...</li>';
    elements.cliPullCommand.textContent = `open-skill-registry pull ${namespace}/${slug}`;

    try {
      const resp = await fetch(`/api/v1/skills/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}`);
      if (!resp.ok) {
        throw new Error(`Failed to load skill details (HTTP ${resp.status})`);
      }
      const json = await resp.json();
      const skill = json.data;
      currentSkill = skill;

      elements.modalSkillName.textContent = skill.name;
      elements.modalNamespace.textContent = skill.namespace;
      elements.modalVisibility.textContent = skill.visibility || 'PUBLIC';
      elements.modalVisibility.setAttribute('data-vis', skill.visibility || 'PUBLIC');
      elements.modalSlug.textContent = `${skill.namespace}/${skill.slug}`;
      elements.modalDescription.textContent = skill.description || 'No description provided.';
      elements.modalDownloads.textContent = skill.download_count || 0;

      // Versions dropdown
      const versions = skill.versions || [skill.latest_version || skill.version || '1.0.0'];
      elements.modalVersionSelect.innerHTML = versions
        .map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}${v === skill.latest_version ? ' (latest)' : ''}</option>`)
        .join('');

      const activeVersion = skill.latest_version || versions[0];
      elements.modalVersionBadge.textContent = `v${activeVersion}`;

      // Populate tags
      elements.modalTags.innerHTML = '';
      const tags = Array.isArray(skill.tags) ? skill.tags : Object.keys(skill.tags || {});
      if (tags.length === 0) {
        elements.modalTags.innerHTML = '<span class="state-text">No tags specified</span>';
      } else {
        tags.forEach(tag => {
          const pill = document.createElement('span');
          pill.className = 'pill tag-pill';
          pill.textContent = tag;
          elements.modalTags.appendChild(pill);
        });
      }

      // Load active version details (instructions & files)
      await loadVersionDetails(namespace, slug, activeVersion);

    } catch (err) {
      console.error('Error loading skill detail:', err);
      elements.modalSkillName.textContent = 'Error Loading Skill';
      elements.modalDescription.textContent = err.message || 'Could not load details.';
      elements.modalInstructions.innerHTML = '<p class="state-text">Failed to load instructions.</p>';
    }
  }

  async function loadVersionDetails(namespace, slug, version) {
    elements.modalVersionBadge.textContent = `v${version}`;
    elements.modalInstructions.innerHTML = '<p class="placeholder-text">Loading instructions...</p>';
    elements.modalFilesList.innerHTML = '<li class="file-item">Loading files...</li>';

    // 1. Fetch instructions
    try {
      const instResp = await fetch(`/api/v1/skills/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}/instructions?version=${encodeURIComponent(version)}`);
      if (instResp.ok) {
        const markdown = await instResp.text();
        elements.modalInstructions.innerHTML = renderMarkdown(markdown);
      } else {
        elements.modalInstructions.innerHTML = '<p class="placeholder-text">No instructions found for this version.</p>';
      }
    } catch (err) {
      elements.modalInstructions.innerHTML = '<p class="placeholder-text">Error loading instructions.</p>';
    }

    // 2. Fetch version metadata (manifest + hash)
    try {
      const verResp = await fetch(`/api/v1/skills/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}`);
      if (verResp.ok) {
        const verJson = await verResp.json();
        const verData = verJson.data || {};

        const hash = verData.content_hash || '';
        elements.modalContentHash.textContent = hash ? `sha256:${hash}` : 'N/A';
        elements.modalContentHash.setAttribute('data-hash', hash);

        // Populate files list from manifest
        const manifest = verData.manifest || {};
        let files = [];
        if (Array.isArray(manifest.files)) {
          files = manifest.files.map(f => ({
            name: typeof f === 'string' ? f : (f.path || ''),
            size: f.size_bytes || f.size || 0,
          }));
        } else if (typeof manifest === 'object') {
          files = Object.keys(manifest)
            .filter(k => k !== 'version' && k !== 'total_size_bytes' && k !== 'content_hash')
            .map(k => ({
              name: k,
              size: (manifest[k] && (manifest[k].size_bytes || manifest[k].size)) || 0,
            }));
        }

        if (files.length === 0) {
          elements.modalFilesList.innerHTML = '<li class="file-item"><span class="file-name-inline">📄 SKILL.md</span></li>';
        } else {
          elements.modalFilesList.innerHTML = files
            .map(f => {
              const size = f.size ? formatBytes(f.size) : '';
              return `
                <li class="file-item">
                  <span class="file-name-inline">${f.name.endsWith('.md') ? '📝' : f.name.endsWith('.py') ? '🐍' : '📄'} ${escapeHtml(f.name)}</span>
                  ${size ? `<span class="file-size-badge">${escapeHtml(size)}</span>` : ''}
                </li>
              `;
            })
            .join('');
        }
      }
    } catch (err) {
      console.error('Error fetching version details:', err);
    }
  }

  function closeDetailModal() {
    setElementVisibility(elements.detailModal, false);
    document.body.style.overflow = '';
    currentSkill = null;
  }

  // --- Upload Modal & Drag-and-Drop ---

  function openUploadModal() {
    resetUploadForm();
    setElementVisibility(elements.uploadModal, true);
    document.body.style.overflow = 'hidden';
    elements.uploadNamespace.focus();
  }

  function closeUploadModal() {
    setElementVisibility(elements.uploadModal, false);
    document.body.style.overflow = '';
    resetUploadForm();
  }

  function resetUploadForm() {
    selectedFile = null;
    elements.fileInput.value = '';
    setElementVisibility(elements.dropzonePrompt, true);
    setElementVisibility(elements.dropzoneFileInfo, false);
    elements.uploadDropzone.classList.remove('drag-over');
    elements.publishBtn.disabled = true;

    setElementVisibility(elements.uploadStatus, false);
    setElementVisibility(elements.uploadSuccess, false);
    setElementVisibility(elements.uploadError, false);

    elements.uploadSlug.value = '';
    elements.uploadVersion.value = '';
    elements.uploadVisibility.value = 'PUBLIC';
  }

  function handleFileSelected(file) {
    if (!file) return;

    selectedFile = file;
    elements.selectedFileName.textContent = file.name;
    elements.selectedFileSize.textContent = formatBytes(file.size);

    setElementVisibility(elements.dropzonePrompt, false);
    setElementVisibility(elements.dropzoneFileInfo, true);
    elements.publishBtn.disabled = false;

    // Suggest slug if empty
    if (!elements.uploadSlug.value.trim()) {
      if (file.name.endsWith('.zip')) {
        const baseName = file.name.slice(0, -4).toLowerCase().replace(/[^a-z0-9-_]/g, '-');
        elements.uploadSlug.value = baseName;
      }
    }
  }

  function removeSelectedFile(e) {
    if (e) e.stopPropagation();
    selectedFile = null;
    elements.fileInput.value = '';
    setElementVisibility(elements.dropzonePrompt, true);
    setElementVisibility(elements.dropzoneFileInfo, false);
    elements.publishBtn.disabled = true;
  }

  async function handlePublishSubmit(e) {
    e.preventDefault();
    if (!selectedFile) {
      showToast('Please select a skill package or SKILL.md file to upload', 'error');
      return;
    }

    const namespace = elements.uploadNamespace.value.trim() || 'public';
    const slug = elements.uploadSlug.value.trim() || null;
    const version = elements.uploadVersion.value.trim() || null;
    const visibility = elements.uploadVisibility.value;

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('namespace', namespace);
    if (slug) formData.append('slug', slug);
    if (version) formData.append('version', version);
    if (visibility) formData.append('visibility', visibility);

    // Update UI for publishing progress
    setElementVisibility(elements.uploadStatus, true);
    setElementVisibility(elements.uploadSuccess, false);
    setElementVisibility(elements.uploadError, false);
    elements.publishBtn.disabled = true;
    elements.cancelUploadBtn.disabled = true;

    try {
      const resp = await fetch('/api/v1/skills/publish', {
        method: 'POST',
        body: formData,
      });

      const json = await resp.json().catch(() => null);

      if (!resp.ok) {
        let msg = 'Failed to publish skill';
        if (json && json.error) msg = json.error;
        else if (json && json.detail) msg = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
        throw new Error(msg);
      }

      // Success!
      setElementVisibility(elements.uploadStatus, false);
      setElementVisibility(elements.uploadSuccess, true);

      const pubData = (json && json.data) || {};
      const assignedSlug = pubData.slug || slug || 'skill';
      const assignedVer = pubData.version || version || '1.0.0';
      const hash = pubData.content_hash || '';

      elements.uploadSuccessDetails.innerHTML = `
        <p>Published: <strong>${escapeHtml(namespace)}/${escapeHtml(assignedSlug)}</strong> (v${escapeHtml(assignedVer)})</p>
        ${hash ? `<p class="meta-hash">Hash: ${escapeHtml(hash)}</p>` : ''}
      `;

      showToast(`Skill ${namespace}/${assignedSlug}@${assignedVer} published!`, 'success');

      // Refresh catalog in background
      loadCatalog();

      // Reset file selection so user can publish another if desired
      setTimeout(() => {
        elements.publishBtn.disabled = false;
        elements.cancelUploadBtn.disabled = false;
      }, 1000);

    } catch (err) {
      console.error('Publish error:', err);
      setElementVisibility(elements.uploadStatus, false);
      setElementVisibility(elements.uploadError, true);
      elements.uploadErrorText.textContent = err.message || 'An unexpected error occurred while publishing.';
      elements.publishBtn.disabled = false;
      elements.cancelUploadBtn.disabled = false;
    }
  }

  // --- Setup Event Listeners ---

  function setupEventListeners() {
    // Live Search with Debounce
    elements.searchInput.addEventListener('input', (e) => {
      clearTimeout(searchDebounceTimer);
      const query = e.target.value;
      if (!query.trim()) {
        elements.searchClearBtn.classList.add('hidden');
      } else {
        elements.searchClearBtn.classList.remove('hidden');
      }
      searchDebounceTimer = setTimeout(() => {
        searchSkills(query);
      }, 300);
    });

    elements.searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        clearTimeout(searchDebounceTimer);
        searchSkills(elements.searchInput.value);
      }
    });

    elements.searchClearBtn.addEventListener('click', () => {
      elements.searchInput.value = '';
      elements.searchClearBtn.classList.add('hidden');
      loadCatalog();
      elements.searchInput.focus();
    });

    // Upload Modal Triggers
    elements.openUploadBtn.addEventListener('click', openUploadModal);
    elements.emptyPublishBtn.addEventListener('click', openUploadModal);
    elements.closeUploadModal.addEventListener('click', closeUploadModal);
    elements.cancelUploadBtn.addEventListener('click', closeUploadModal);

    // Detail Modal Triggers
    elements.closeDetailModal.addEventListener('click', closeDetailModal);
    elements.detailCloseFooterBtn.addEventListener('click', closeDetailModal);

    // Version dropdown change
    elements.modalVersionSelect.addEventListener('change', (e) => {
      if (currentSkill) {
        loadVersionDetails(currentSkill.namespace, currentSkill.slug, e.target.value);
      }
    });

    // Copy Content Hash
    elements.copyHashBtn.addEventListener('click', () => {
      const hash = elements.modalContentHash.getAttribute('data-hash') || elements.modalContentHash.textContent;
      if (hash && hash !== 'N/A') {
        navigator.clipboard.writeText(hash).then(() => {
          showToast('Content hash copied to clipboard!', 'success');
        });
      }
    });

    // Copy CLI Command
    elements.copyCliBtn.addEventListener('click', () => {
      const cmd = elements.cliPullCommand.textContent;
      navigator.clipboard.writeText(cmd).then(() => {
        showToast('CLI pull command copied to clipboard!', 'success');
      });
    });

    // Backdrop clicks
    elements.detailModal.addEventListener('click', (e) => {
      if (e.target === elements.detailModal) closeDetailModal();
    });
    elements.uploadModal.addEventListener('click', (e) => {
      if (e.target === elements.uploadModal) closeUploadModal();
    });

    // ESC key closes modals
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (!elements.detailModal.classList.contains('hidden')) closeDetailModal();
        if (!elements.uploadModal.classList.contains('hidden')) closeUploadModal();
      }
    });

    // Retry button
    elements.retryBtn.addEventListener('click', loadCatalog);

    // Dropzone Events
    const dropzone = elements.uploadDropzone;

    dropzone.addEventListener('click', () => {
      elements.fileInput.click();
    });

    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        elements.fileInput.click();
      }
    });

    elements.fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileSelected(e.target.files[0]);
      }
    });

    elements.removeFileBtn.addEventListener('click', removeSelectedFile);

    // Drag-over styling
    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('drag-over');
      });
    });

    ['dragleave', 'dragend'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('drag-over');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-over');

      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    // Form submit
    elements.uploadForm.addEventListener('submit', handlePublishSubmit);
  }

  // --- Initialize ---
  document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadCatalog();
  });
})();
