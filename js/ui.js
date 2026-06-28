/* ================================================================
   Skeb Tracker — ui.js
   User cards, detail expansion, pagination, album modal, tag bar
   ================================================================ */

App._createCardHTML = function(user) {
	var avatar = user.avatar_url || '';
	var sn = user.screen_name;
	var prices = user.current_prices || {};
	var chips = Object.entries(prices).map(function(p) {
		return '<span class="price-chip">' + p[0] + ': \u00A5' + p[1].toLocaleString() + '</span>';
	}).join('');

	var badges = '';
	if (user.acceptable) badges += '<span class="badge badge-open">Open</span>';
	else if (user.acceptable !== undefined) badges += '<span class="badge badge-closed">Closed</span>';
	if (user.nsfw) badges += '<span class="badge badge-nsfw">NSFW</span>';
	if (user._tags && user._tags.length) {
		badges += user._tags.map(function(t) { return '<span class="badge badge-tag">' + t + '</span>'; }).join('');
	}

	var notesHtml = '';
	if (user._notes) {
		notesHtml = '<div class="card-notes">' + user._notes.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
	}

	var thumbs = user.latest_thumbnails || [];
	var thumbHtml = thumbs.length
		? '<div class="thumb-strip">' + thumbs.slice(0, 4).map(function(src) {
			return '<img src="' + src + '" loading="lazy" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');" alt="work">';
		}).join('') + '</div>'
		: '<div style="height:100px;background:var(--surface3);display:flex;align-items:center;justify-content:center;color:var(--text-secondary);">No previews</div>';

		return '<div class="user-card" data-screenname="' + sn + '" data-file="' + (user.file || '') + '">'
		+ '<div class="card-main">'
			+ '<div class="card-header">'
				+ '<img class="card-avatar" src="' + avatar + '" alt="' + sn + '" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">'
				+ '<div class="card-identity">'
					+ '<a class="card-name-link" href="https://skeb.jp/@' + sn + '" target="_blank" onclick="event.stopPropagation()">@' + sn + '</a>'
				+ '</div>'
				+ '<div class="prices-summary">' + (chips || '<span style="color:var(--text-secondary)">No prices</span>') + '</div>'
			+ '</div>'
			+ '<div class="badges">' + badges + '</div>'
			+ notesHtml
			+ thumbHtml
			+ '<div class="card-footer">'
				+ '<span><iconify-icon icon="mdi:image-multiple" width="14"></iconify-icon> ' + (user.total_works || 0) + '</span>'
				+ '<span><iconify-icon icon="mdi:clock-outline" width="14"></iconify-icon> ' + App._fmtDate(user.last_updated) + '</span>'
				+ '<span><iconify-icon icon="mdi:calendar-plus" width="14"></iconify-icon> ' + App._fmtDate(user.first_seen) + '</span>'
			+ '</div>'
		+ '</div>'
		+ '<div class="detail-expand" id="detail-' + sn + '"></div>'
	+ '</div>';
};

App._renderUsers = function() {
	var grid = document.getElementById('userGrid');
	var start = (App.currentPage - 1) * App.perPage;
	var page = App.filteredUsers.slice(start, start + App.perPage);

	if (!page.length) {
		grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary);">No creators match your filters.</div>';
		return;
	}

	grid.innerHTML = page.map(function(u) { return App._createCardHTML(u); }).join('');

	grid.querySelectorAll('.user-card').forEach(function(card) {
		var sn = card.dataset.screenname;
		var file = card.dataset.file;
		var detail = card.querySelector('.detail-expand');
		var main = card.querySelector('.card-main');

		main.addEventListener('click', function(e) {
			if (e.target.closest('a')) return;
			if (detail.classList.contains('open')) {
				detail.classList.remove('open');
				card.classList.remove('expanded');
			} else {
				detail.classList.add('open');
				card.classList.add('expanded');
				if (!detail.dataset.loaded) App._loadDetail(sn, file, detail);
			}
		});

		detail.addEventListener('click', function(e) {
			if (e.target.closest('a, button, input, select, textarea, [role="button"]')) return;
			e.stopPropagation();
			detail.classList.remove('open');
			card.classList.remove('expanded');
		});
	});
};

App._loadDetail = async function(sn, filePath, container) {
	if (!filePath) {
		filePath = App._computeFileKey(sn);
	}
	container.innerHTML = '<div class="loader"><div class="spinner"></div></div>';
	try {
		if (App.detailCache[sn]) {
			App._renderDetail(App.detailCache[sn], container);
			container.dataset.loaded = 'true';
			return;
		}
		var r = await App._fetch('skeb/' + filePath + '.json');
		if (!r.ok) throw new Error('Not found');
		var data = await r.json();
		App.detailCache[sn] = data;
		App._renderDetail(data, container);
		container.dataset.loaded = 'true';
	} catch (e) {
		container.innerHTML = '<div style="padding:1rem;color:var(--text-secondary);">No detailed data available for this entry.</div>';
	}
};

App._renderDetail = function(data, container) {
	var p = data.profile || {};
	var header = p.header_url
		? '<img src="' + p.header_url + '" style="width:100%;height:120px;object-fit:cover;margin-bottom:0.8rem;border:1px solid var(--border);" alt="header" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">'
		: '';

	var links = [];
	if (p.pixiv_id) links.push('<a href="https://www.pixiv.net/en/users/' + p.pixiv_id + '" target="_blank">Pixiv</a>');
	if (p.url) links.push('<a href="' + p.url + '" target="_blank">Website</a>');
	(p.user_service_links || []).forEach(function(l) {
		if (!l.url) return;
		if (l.provider === 'twitter') links.unshift('<a href="' + l.url + '" target="_blank">\uD835\uDD4F Twitter</a>');
		else links.push('<a href="' + l.url + '" target="_blank">' + l.provider + '</a>');
	});

	var skills = p.skills || data.skills || [];
	var priceHist = data.price_history || {};
	var works = p.received_works || [];
	var worksHtml = works.length
		? works.map(function(w) {
			var src = w.thumbnail_image_urls ? w.thumbnail_image_urls.src : (w.private_thumbnail_image_urls ? w.private_thumbnail_image_urls.src : (w.censored_thumbnail_image_urls ? w.censored_thumbnail_image_urls.src : ''));
			var url = w.path ? 'https://skeb.jp' + w.path : '#';
			return src ? '<a href="' + url + '" target="_blank"><img class="work-thumb" src="' + src + '" alt="work" loading="lazy" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');"></a>' : '';
		}).join('')
		: '<span style="color:var(--text-secondary)">No visible works</span>';

	container.innerHTML = header
		+ '<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:0.8rem;font-size:0.85rem;">'
			+ '<span>Accepting: <strong>' + (p.acceptable ? 'Yes' : 'No') + '</strong></span>'
			+ '<span>NSFW: <strong>' + (p.nsfw_acceptable ? 'Yes' : 'No') + '</strong></span>'
			+ '<span>Creator: <strong>' + (p.creator ? 'Yes' : 'No') + '</strong></span>'
			+ '<span>Language: ' + (p.language || '?') + '</span>'
			+ '<span>Works: ' + (p.received_works_count || 0) + '</span>'
		+ '</div>'
		+ '<div class="social-links">' + (links.join(' ') || 'No links') + '</div>'
		+ '<div class="detail-section">'
			+ '<h3>Skills &amp; Prices</h3>'
			+ '<ul>' + skills.map(function(s) { return '<li>' + s.genre + ': \u00A5' + (s.default_amount || 0).toLocaleString() + '</li>'; }).join('') + '</ul>'
		+ '</div>'
		+ '<div class="detail-section">'
			+ '<h3>Price History</h3>'
			+ (Object.keys(priceHist).length
				? Object.entries(priceHist).map(function(e) {
					return '<div style="margin-bottom:0.8rem;">'
						+ '<strong style="color:var(--accent)">' + e[0] + '</strong>'
						+ '<table style="width:100%;border-collapse:collapse;font-size:0.8rem;">'
						+ e[1].map(function(pe) { return '<tr><td style="padding:0.25rem;">' + App._fmtDate(pe.recorded_at) + '</td><td>\u00A5' + pe.amount.toLocaleString() + '</td></tr>'; }).join('')
						+ '</table></div>';
				}).join('')
				: '<p>No history</p>')
		+ '</div>'
		+ '<div class="detail-section">'
			+ '<h3>Received Works</h3>'
			+ '<div class="works-grid">' + worksHtml + '</div>'
		+ '</div>';
};

App._renderPagination = function() {
	var total = Math.ceil(App.filteredUsers.length / App.perPage);
	var c = document.getElementById('pagination');
	if (total <= 1) { c.innerHTML = ''; return; }
	c.innerHTML = ''
		+ '<button class="page-btn" ' + (App.currentPage === 1 ? 'disabled' : '') + ' data-page="prev">\u25C0</button>'
		+ '<span class="page-info">Page ' + App.currentPage + ' of ' + total + '</span>'
		+ '<button class="page-btn" ' + (App.currentPage === total ? 'disabled' : '') + ' data-page="next">\u25B6</button>';
	var prev = c.querySelector('[data-page="prev"]');
	if (prev) prev.addEventListener('click', function() {
		if (App.currentPage > 1) { App.currentPage--; App._renderUsers(); App._renderPagination(); App._updateURL(); window.scrollTo(0, 0); }
	});
	var next = c.querySelector('[data-page="next"]');
	if (next) next.addEventListener('click', function() {
		if (App.currentPage < total) { App.currentPage++; App._renderUsers(); App._renderPagination(); App._updateURL(); window.scrollTo(0, 0); }
	});
};

App._closeAllDetails = function() {
	document.querySelectorAll('.detail-expand.open').forEach(function(d) { d.classList.remove('open'); });
	document.querySelectorAll('.user-card.expanded').forEach(function(c) { c.classList.remove('expanded'); });
};

App._renderAlbumButton = function() {
	var btn = document.getElementById('albumSelectBtn');
	if (App.currentAlbum) {
		btn.innerHTML = '<iconify-icon icon="mdi:book-open-page-variant-outline"></iconify-icon> ' + App.currentAlbum.label + ' <span class="album-arrow">\u25BE</span>';
	} else {
		btn.innerHTML = '<iconify-icon icon="mdi:book-open-page-variant-outline"></iconify-icon> Albums <span class="album-arrow">\u25BE</span>';
	}

	var bar = document.getElementById('albumTagBar');
	if (App.currentAlbum && App.currentAlbum.type !== 'full' && App.albumTags.length) {
		bar.classList.remove('hidden');
		bar.innerHTML = '<span style="font-size:0.75rem;color:var(--text-secondary);margin-right:0.3rem;">Tags:</span>'
			+ App.albumTags.map(function(t) {
				var cls = App.filterAlbumTags.includes(t) ? ' active' : '';
				return '<span class="album-tag-chip' + cls + '" data-tag="' + t + '">' + t + '</span>';
			}).join('');
		bar.querySelectorAll('.album-tag-chip').forEach(function(c) {
			c.addEventListener('click', function() { App._toggleAlbumTag(c.dataset.tag); });
		});
	} else {
		bar.classList.add('hidden');
		bar.innerHTML = '';
	}
};

App._openAlbumModal = function() {
	App.albumModalTypeFilter = 'all';
	document.getElementById('albumModal').classList.remove('hidden');
	document.getElementById('albumModalSearch').value = '';
	App._renderAlbumModalTypeChips();
	App._renderAlbumModalList();
	document.getElementById('albumModalSearch').focus();
};

App._closeAlbumModal = function() {
	document.getElementById('albumModal').classList.add('hidden');
};

App._renderAlbumModalTypeChips = function() {
	var bar = document.getElementById('albumModalTypeFilters');
	bar.querySelectorAll('.album-type-chip').forEach(function(c) {
		c.classList.toggle('active', c.dataset.type === App.albumModalTypeFilter);
	});
};

App._renderAlbumModalList = function(filterText) {
	var listEl = document.getElementById('albumModalList');
	var search = (filterText || '').toLowerCase();
	var filterType = App.albumModalTypeFilter;

	var items = [];

	function addIfMatch(name, info) {
		if (name.replace(/\/$/, '') === 'albums/main_index' && items.find(function(x) { return x.name.replace(/\/$/, '') === 'albums/main_index'; })) return;
		if (filterType !== 'all' && info.type !== filterType) return;
		if (search) {
			var matchName = name.toLowerCase().includes(search);
			var matchLabel = (info.label || '').toLowerCase().includes(search);
			if (name.replace(/\/$/, '') === 'albums/main_index' && 'all artists'.includes(search)) { /* allow */ }
			else if (!matchName && !matchLabel) return;
		}
		items.push(Object.assign({ name: name }, info));
	}

	addIfMatch('albums/main_index', { label: 'All Artists', type: 'full' });
	Object.entries(App.albumIndex).forEach(function(e) {
		if (e[0].replace(/\/$/, '') === 'albums/main_index') return;
		addIfMatch(e[0], e[1]);
	});

	if (!items.length) {
		listEl.innerHTML = '<div class="album-modal-item" style="color:var(--text-secondary);cursor:default;">No albums found</div>';
		return;
	}

	var active = App.currentAlbum;
	listEl.innerHTML = items.map(function(item) {
		var cls = (active && active.name === item.name) ? ' active' : '';
		var badge = '';
		if (item.type === 'full') badge = '<span class="album-type-badge badge-full">full</span>';
		else if (item.type === 'reports') badge = '<span class="album-type-badge badge-reports">reports</span>';
		else badge = '<span class="album-type-badge badge-curated">curated</span>';
		return '<div class="album-modal-item' + cls + '" data-album="' + item.name + '">'
			+ '<div class="album-modal-item-label">' + item.label + ' ' + badge + '</div>'
			+ '<div class="album-modal-item-name">' + item.name + '</div>'
		+ '</div>';
	}).join('');

	listEl.querySelectorAll('.album-modal-item').forEach(function(el) {
		el.addEventListener('click', function() {
			var name = el.dataset.album;
			App._closeAlbumModal();
			if (name && (!active || active.name !== name)) App._switchAlbum(name);
		});
	});
};

App._handleExternalAlbumPrompt = function() {
	var url = prompt('Enter album URL or relative path:');
	if (url) {
		App._closeAlbumModal();
		App._loadExternalAlbum(url.trim());
	}
};

App._handleFileAlbumPrompt = function() {
	var input = document.createElement('input');
	input.type = 'file';
	input.accept = '.album,.md';
	input.addEventListener('change', async function() {
		var file = input.files[0];
		if (!file) return;
		try {
			if (file.name.endsWith('.md')) {
				var mdText = await file.text();
				var d = App._parseMarkdownAlbum(mdText, file.name);
				App.albumEntries = d.data || [];
				App.currentAlbum = {
					name: d.name || '_file',
					label: d.label || file.name,
					type: d.type || 'reports',
					_fromFile: true
				};
			} else {
				var buf = await file.arrayBuffer();
				var h = App._parseAlbumHeader(buf);
				var data = await App._decompressAndParse(buf.slice(h.headerSize));
				App.albumEntries = Array.isArray(data) ? data : [];
				App.currentAlbum = {
					name: h.meta.name || '_file',
					label: h.meta.label || h.meta.name || file.name,
					type: h.meta.type || 'curated',
					_fromFile: true
				};
			}
			App._closeAlbumModal();
			App._onAlbumChanged();
		} catch (e) {
			console.error('Failed to load album file:', e);
			alert('Failed to load album: ' + e.message);
		}
	});
	input.click();
};
