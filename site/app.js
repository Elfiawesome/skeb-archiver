/* ================================================================
   Skeb Tracker — app.js
   ================================================================ */

const App = {

// ================================================================
// STATE
// ================================================================

	mainData: [],
	allUsers: [],
	filteredUsers: [],
	currentPage: 1,
	perPage: 60,
	searchTerm: '',
	filterAcceptable: null,
	filterNsfw: null,
	filterGenre: '',
	filterPriceMin: null,
	filterPriceMax: null,
	filterWorksMin: null,
	filterWorksMax: null,
	filterSeenOlderDays: null,
	filterUpdatedWithinDays: null,
	sortChain: [],
	genreList: [],
	loadingComplete: false,
	detailCache: {},
	timeNow: new Date(),

	albumIndex: {},
	currentAlbum: null,
	albumEntries: [],
	albumTags: [],
	filterAlbumTags: [],
	albumModalTypeFilter: 'all',

// ================================================================
// INIT
// ================================================================

	async init() {
		try {
			this.timeNow = new Date();
			this._readURLParams();

			await this._loadAlbumIndex();

			const mainAlbum = await this._getAlbum('albums', 'main_index');
			this.mainData = mainAlbum.data || [];

			const extUrl = this.currentAlbum._externalUrl || null;
			if (extUrl) {
				await this._tryLoadExternal(extUrl);
			} else if (this.currentAlbum && this.currentAlbum.name !== 'main_index') {
				await this._tryLoadAlbum(this.currentAlbum.name);
			} else {
				this.currentAlbum = { name: 'main_index', label: 'All Artists', type: 'full' };
			}

			this._mergeWithMain();
			this._collectAlbumTags();

			document.querySelector('#statsBadge span').textContent =
				`${this.allUsers.length?.toLocaleString() || '?'} users` +
				(mainAlbum.timestamp ? ` · ${this._fmtDate(mainAlbum.timestamp)}` : '');

			this._extractGenres();
			this._bindEvents();
			this._renderSortStates();
			this._applyFilters();
			this._renderAlbumButton();

			this.loadingComplete = true;
		} catch (e) {
			console.error("Init failed:", e);
		}
	},

// ================================================================
// DATA — fetching & parsing
// ================================================================

	async _fetch(url) {
		let res = await fetch(url);
		if (!res.ok) {
			res = await fetch(
				"https://raw.githubusercontent.com/Elfiawesome/skeb-archiver/refs/heads/archive/" + url
			);
		}
		return res;
	},

	_parseAlbumHeader(buffer) {
		const view = new DataView(buffer);
		const metaSize = view.getUint32(0, false);
		const metaBytes = new Uint8Array(buffer.slice(4, 4 + metaSize));
		const meta = JSON.parse(new TextDecoder('utf-8').decode(metaBytes));
		const dataSize = new DataView(
			buffer.slice(4 + metaSize, 8 + metaSize)
		).getUint32(0, false);
		return { meta, metaSize, dataSize, headerSize: 8 + metaSize };
	},

	async _decompressAndParse(compressed) {
		const stream = new Response(compressed).body.pipeThrough(
			new DecompressionStream('gzip')
		);
		const buf = await new Response(stream).arrayBuffer();
		return JSON.parse(new TextDecoder('utf-8').decode(buf));
	},

	async _getAlbum(urlPath, name) {
		const base = `${urlPath}/${name}.album/${name}.`;
		let idx = 1;
		let downloaded = 0;
		let meta = null;
		let dataSize = null;
		let headerSize = 0;
		const chunks = [];

		while (meta === null || downloaded < headerSize + dataSize) {
			const jobs = [];
			for (let i = 0; i < 10; i++) jobs.push(this._fetch(`${base}${idx + i}`));
			const responses = await Promise.all(jobs);
			for (const r of responses) {
				if (!r.ok) continue;
				const buf = await r.arrayBuffer();
				if (meta === null) {
					const h = this._parseAlbumHeader(buf);
					meta = h.meta;
					dataSize = h.dataSize;
					headerSize = h.headerSize;
				}
				chunks.push(buf);
				downloaded += buf.byteLength;
			}
			idx += 10;
		}

		const total = headerSize + dataSize;
		const merged = new Uint8Array(total);
		let off = 0;
		for (const c of chunks) {
			merged.set(new Uint8Array(c), off);
			off += c.byteLength;
		}

		const data = await this._decompressAndParse(merged.slice(headerSize));
		return { ...meta, data: Array.isArray(data) ? data : [] };
	},

	async _getAlbumFromUrl(url) {
		const r = await fetch(url);
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		const buf = await r.arrayBuffer();
		const h = this._parseAlbumHeader(buf);
		const data = await this._decompressAndParse(buf.slice(h.headerSize));
		return { ...h.meta, data: Array.isArray(data) ? data : [] };
	},

	async _loadAlbumIndex() {
		try {
			const r = await this._fetch('albums/index.json');
			if (r.ok) this.albumIndex = await r.json();
		} catch (e) {
			console.warn('Could not load album index:', e);
			this.albumIndex = { main_index: { label: 'All Artists', type: 'full' } };
		}
	},

// ================================================================
// ALBUM — switching, external loading, merging
// ================================================================

	async _tryLoadAlbum(name) {
		try {
			const d = await this._getAlbum('albums', name);
			this.albumEntries = d.data || [];
			const info = this.albumIndex[name] || {};
			this.currentAlbum = {
				name,
				label: info.label || d.label || name,
				type: info.type || d.type || 'curated'
			};
		} catch (e) {
			console.error('Failed to load album:', e);
			this.albumEntries = [];
			this.currentAlbum = { name: 'main_index', label: 'All Artists', type: 'full' };
		}
	},

	async _tryLoadExternal(url) {
		try {
			const d = await this._getAlbumFromUrl(url);
			this.albumEntries = d.data || [];
			this.currentAlbum = {
				name: d.name || '_external',
				label: d.label || d.name || 'External',
				type: d.type || 'curated',
				_externalUrl: url
			};
		} catch (e) {
			console.error('Failed to load external album:', e);
			this.albumEntries = [];
			this.currentAlbum = { name: 'main_index', label: 'All Artists', type: 'full' };
		}
	},

	async _switchAlbum(name) {
		this.currentPage = 1;
		this.filterAlbumTags = [];

		if (name === 'main_index') {
			this.currentAlbum = { name: 'main_index', label: 'All Artists', type: 'full' };
			this.albumEntries = [];
		} else {
			await this._tryLoadAlbum(name);
		}

		this._onAlbumChanged();
	},

	async _loadExternalAlbum(url) {
		this.currentPage = 1;
		this.filterAlbumTags = [];
		await this._tryLoadExternal(url);
		this._onAlbumChanged();
	},

	_onAlbumChanged() {
		this._mergeWithMain();
		this._collectAlbumTags();
		this._renderSortStates();
		this._updateURL();
		this._applyFilters();
		this._renderAlbumButton();
	},

	_mergeWithMain() {
		if (!this.currentAlbum || this.currentAlbum.type === 'full' || !this.albumEntries.length) {
			this.allUsers = [...this.mainData];
			return;
		}

		const map = {};
		for (const u of this.mainData) map[u.screen_name] = u;

		const merged = [];
		for (const e of this.albumEntries) {
			const sn = e.screen_name;
			if (!sn) continue;
			const full = map[sn];
			if (full) {
				const copy = { ...full };
				if (e.tags) copy._tags = e.tags;
				if (e.notes) copy._notes = e.notes;
				merged.push(copy);
			} else {
				merged.push({ screen_name: sn, _tags: e.tags || [], _notes: e.notes || '' });
			}
		}
		this.allUsers = merged;
	},

	_collectAlbumTags() {
		const set = new Set();
		for (const u of this.allUsers) {
			if (u._tags) u._tags.forEach(t => set.add(t));
		}
		this.albumTags = [...set].sort();
	},

	_toggleAlbumTag(tag) {
		const i = this.filterAlbumTags.indexOf(tag);
		i === -1 ? this.filterAlbumTags.push(tag) : this.filterAlbumTags.splice(i, 1);
		this.currentPage = 1;
		this._applyFilters();
	},

// ================================================================
// UI — album modal
// ================================================================

	_openAlbumModal() {
		this.albumModalTypeFilter = 'all';
		document.getElementById('albumModal').classList.remove('hidden');
		document.getElementById('albumModalSearch').value = '';
		this._renderAlbumModalTypeChips();
		this._renderAlbumModalList();
		document.getElementById('albumModalSearch').focus();
	},

	_closeAlbumModal() {
		document.getElementById('albumModal').classList.add('hidden');
	},

	_renderAlbumModalTypeChips() {
		const bar = document.getElementById('albumModalTypeFilters');
		bar.querySelectorAll('.album-type-chip').forEach(c => {
			c.classList.toggle('active', c.dataset.type === this.albumModalTypeFilter);
		});
	},

	_renderAlbumModalList(filterText) {
		const listEl = document.getElementById('albumModalList');
		const search = (filterText || '').toLowerCase();
		const filterType = this.albumModalTypeFilter;

		const items = [];

		const addIfMatch = (name, info) => {
			if (name === 'main_index' && items.find(x => x.name === 'main_index')) return;
			if (filterType !== 'all' && info.type !== filterType) return;
			if (search) {
				const matchName = name.toLowerCase().includes(search);
				const matchLabel = (info.label || '').toLowerCase().includes(search);
				if (name === 'main_index' && 'all artists'.includes(search)) { /* allow */ }
				else if (!matchName && !matchLabel) return;
			}
			items.push({ name, ...info });
		};

		addIfMatch('main_index', { label: 'All Artists', type: 'full' });
		for (const [name, info] of Object.entries(this.albumIndex)) {
			if (name === 'main_index') continue;
			addIfMatch(name, info);
		}

		if (!items.length) {
			listEl.innerHTML = '<div class="album-modal-item" style="color:var(--text-secondary);cursor:default;">No albums found</div>';
			return;
		}

		const active = this.currentAlbum;
		listEl.innerHTML = items.map(item => {
			const cls = (active && active.name === item.name) ? ' active' : '';
			const badge = item.type === 'full'
				? '<span class="album-type-badge badge-full">full</span>'
				: '<span class="album-type-badge badge-curated">curated</span>';
			return `<div class="album-modal-item${cls}" data-album="${item.name}">
				<div class="album-modal-item-label">${item.label} ${badge}</div>
				<div class="album-modal-item-name">${item.name}</div>
			</div>`;
		}).join('');

		listEl.querySelectorAll('.album-modal-item').forEach(el => {
			el.addEventListener('click', () => {
				const name = el.dataset.album;
				this._closeAlbumModal();
				if (name && (!active || active.name !== name)) this._switchAlbum(name);
			});
		});
	},

	_handleExternalAlbumPrompt() {
		const url = prompt('Enter album URL:');
		if (url) {
			this._closeAlbumModal();
			this._loadExternalAlbum(url.trim());
		}
	},

// ================================================================
// UI — album button & tag bar
// ================================================================

	_renderAlbumButton() {
		const btn = document.getElementById('albumSelectBtn');
		if (this.currentAlbum) {
			btn.innerHTML = `<iconify-icon icon="mdi:book-open-page-variant-outline"></iconify-icon> ${this.currentAlbum.label} <span class="album-arrow">▾</span>`;
		} else {
			btn.innerHTML = `<iconify-icon icon="mdi:book-open-page-variant-outline"></iconify-icon> Albums <span class="album-arrow">▾</span>`;
		}

		const bar = document.getElementById('albumTagBar');
		if (this.currentAlbum && this.currentAlbum.type !== 'full' && this.albumTags.length) {
			bar.classList.remove('hidden');
			bar.innerHTML = '<span style="font-size:0.75rem;color:var(--text-secondary);margin-right:0.3rem;">Tags:</span>' +
				this.albumTags.map(t => {
					const cls = this.filterAlbumTags.includes(t) ? ' active' : '';
					return `<span class="album-tag-chip${cls}" data-tag="${t}">${t}</span>`;
				}).join('');
			bar.querySelectorAll('.album-tag-chip').forEach(c => {
				c.addEventListener('click', () => this._toggleAlbumTag(c.dataset.tag));
			});
		} else {
			bar.classList.add('hidden');
			bar.innerHTML = '';
		}
	},

// ================================================================
// UI — filters, sorting, URL params
// ================================================================

	_readURLParams() {
		const p = new URLSearchParams(window.location.search);
		this.searchTerm = p.get('search') || '';
		document.getElementById('searchInput').value = this.searchTerm;

		const a = p.get('acceptable');
		this.filterAcceptable = a === 'true' ? true : (a === 'false' ? false : null);
		const n = p.get('nsfw');
		this.filterNsfw = n === 'true' ? true : (n === 'false' ? false : null);
		this.filterGenre = p.get('genre') || '';
		this.filterPriceMin = p.get('minPrice') ? +p.get('minPrice') : null;
		this.filterPriceMax = p.get('maxPrice') ? +p.get('maxPrice') : null;
		this.filterWorksMin = p.get('worksMin') ? +p.get('worksMin') : null;
		this.filterWorksMax = p.get('worksMax') ? +p.get('worksMax') : null;
		this.filterSeenOlderDays = p.get('seenOlderDays') ? +p.get('seenOlderDays') : null;
		this.filterUpdatedWithinDays = p.get('updatedWithin') ? +p.get('updatedWithin') : null;
		this.currentPage = parseInt(p.get('page')) || 1;

		const sort = p.get('sort') || '';
		this.sortChain = sort ? sort.split(',').map(s => {
			const dir = s.split('_').at(-1);
			return { key: s.replace('_' + dir, ''), dir: dir === 'desc' ? 'desc' : 'asc' };
		}).filter(s => s.key) : [];

		this.filterAlbumTags = p.get('album_tag') ? p.get('album_tag').split(',').filter(Boolean) : [];

		const album = p.get('album') || '';
		const albumUrl = p.get('album_url') || '';
		if (albumUrl) {
			this.currentAlbum = { name: '_external', label: 'External', type: 'curated', _externalUrl: albumUrl };
		} else if (album && album !== 'main_index') {
			this.currentAlbum = { name: album, label: album, type: 'curated' };
		} else {
			this.currentAlbum = { name: 'main_index', label: 'All Artists', type: 'full' };
		}

		this._updateFilterButtonsUI();
	},

	_updateURL() {
		const p = new URLSearchParams();
		if (this.searchTerm) p.set('search', this.searchTerm);
		if (this.filterAcceptable !== null) p.set('acceptable', this.filterAcceptable);
		if (this.filterNsfw !== null) p.set('nsfw', this.filterNsfw);
		if (this.filterGenre) p.set('genre', this.filterGenre);
		if (this.filterPriceMin !== null) p.set('minPrice', this.filterPriceMin);
		if (this.filterPriceMax !== null) p.set('maxPrice', this.filterPriceMax);
		if (this.filterWorksMin !== null) p.set('worksMin', this.filterWorksMin);
		if (this.filterWorksMax !== null) p.set('worksMax', this.filterWorksMax);
		if (this.filterSeenOlderDays !== null) p.set('seenOlderDays', this.filterSeenOlderDays);
		if (this.filterUpdatedWithinDays !== null) p.set('updatedWithin', this.filterUpdatedWithinDays);
		if (this.sortChain.length) p.set('sort', this.sortChain.map(s => s.key + '_' + s.dir).join(','));
		if (this.currentPage > 1) p.set('page', this.currentPage);
		if (this.filterAlbumTags.length) p.set('album_tag', this.filterAlbumTags.join(','));
		if (this.currentAlbum) {
			if (this.currentAlbum._externalUrl) {
				p.set('album_url', this.currentAlbum._externalUrl);
			} else if (this.currentAlbum.name !== 'main_index') {
				p.set('album', this.currentAlbum.name);
			}
		}
		history.replaceState(null, '', window.location.pathname + (p.toString() ? '?' + p.toString() : ''));
	},

	_updateFilterButtonsUI() {
		const btnAcc = document.getElementById('filterAcceptable');
		btnAcc.classList.toggle('active', this.filterAcceptable !== null);
		btnAcc.innerHTML = `<iconify-icon icon="mdi:check-circle-outline"></iconify-icon> ` +
			(this.filterAcceptable === null ? 'Accepting' : (this.filterAcceptable ? 'Accepting ✓' : 'Not accepting ✗'));

		const btnNsfw = document.getElementById('filterNsfw');
		btnNsfw.classList.toggle('active', this.filterNsfw !== null);
		btnNsfw.innerHTML = `<iconify-icon icon="mdi:alert-octagon-outline"></iconify-icon> ` +
			(this.filterNsfw === null ? 'NSFW' : (this.filterNsfw ? 'NSFW ✓' : 'No NSFW ✗'));

		document.getElementById('genreFilter').value = this.filterGenre;
		document.getElementById('priceMin').value = this.filterPriceMin ?? '';
		document.getElementById('priceMax').value = this.filterPriceMax ?? '';
		document.getElementById('worksMin').value = this.filterWorksMin ?? '';
		document.getElementById('worksMax').value = this.filterWorksMax ?? '';
		document.getElementById('seenOlderDays').value = this.filterSeenOlderDays ?? '';
		document.getElementById('updatedWithinDays').value = this.filterUpdatedWithinDays ?? '';
	},

	_applyFilters() {
		let filtered = [...this.allUsers];
		const now = Date.now() / 1000;

		if (this.filterAlbumTags.length) {
			filtered = filtered.filter(u =>
				this.filterAlbumTags.some(t => (u._tags || []).includes(t))
			);
		}

		if (this.searchTerm) {
			const t = this.searchTerm;
			filtered = filtered.filter(u => u.screen_name && u.screen_name.toLowerCase().includes(t));
		}
		if (this.filterAcceptable !== null) filtered = filtered.filter(u => u.acceptable === this.filterAcceptable);
		if (this.filterNsfw !== null) filtered = filtered.filter(u => u.nsfw === this.filterNsfw);
		if (this.filterGenre) filtered = filtered.filter(u => u.current_prices && u.current_prices.hasOwnProperty(this.filterGenre));

		if (this.filterPriceMin !== null || this.filterPriceMax !== null) {
			filtered = filtered.filter(u => {
				const prices = this._getUserPrices(u, this.filterGenre);
				if (!prices) return false;
				const min = Math.min(...prices);
				const max = Math.max(...prices);
				if (this.filterPriceMin !== null && max < this.filterPriceMin) return false;
				if (this.filterPriceMax !== null && min > this.filterPriceMax) return false;
				return true;
			});
		}
		if (this.filterWorksMin !== null) filtered = filtered.filter(u => (u.total_works || 0) >= this.filterWorksMin);
		if (this.filterWorksMax !== null) filtered = filtered.filter(u => (u.total_works || 0) <= this.filterWorksMax);
		if (this.filterSeenOlderDays !== null) {
			const t = now - this.filterSeenOlderDays * 86400;
			filtered = filtered.filter(u => u.first_seen && u.first_seen < t);
		}
		if (this.filterUpdatedWithinDays !== null) {
			const t = now - this.filterUpdatedWithinDays * 86400;
			filtered = filtered.filter(u => u.last_updated && u.last_updated > t);
		}

		if (this.sortChain.length) {
			filtered.sort((a, b) => {
				for (const s of this.sortChain) {
					const cmp = this._compare(a, b, s);
					if (cmp !== 0) return cmp;
				}
				return 0;
			});
		}

		this.filteredUsers = filtered;
		this._updateFilterButtonsUI();
		this._updateURL();
		this._renderUsers();
		this._renderPagination();
		this._renderAlbumButton();
	},

	_getUserPrices(u, genre) {
		if (!u.current_prices || !Object.keys(u.current_prices).length) return null;
		return genre ? (
			genre in u.current_prices ? [u.current_prices[genre]] : null
		) : Object.values(u.current_prices);
	},

	_compare(a, b, sort) {
		const price = u => {
			const p = this._getUserPrices(u, this.filterGenre);
			return p ? Math.min(...p) : Infinity;
		};
		let va, vb;
		switch (sort.key) {
			case 'price':      va = price(a);            vb = price(b);            break;
			case 'works':      va = a.total_works || 0;  vb = b.total_works || 0;  break;
			case 'updated':    va = a.last_updated || 0; vb = b.last_updated || 0; break;
			case 'first_seen': va = a.first_seen || 0;   vb = b.first_seen || 0;   break;
			default: return 0;
		}
		return sort.dir === 'asc' ? va - vb : vb - va;
	},

	_toggleSortKey(key) {
		const ex = this.sortChain.find(s => s.key === key);
		if (!ex) this.sortChain.push({ key, dir: 'asc' });
		else if (ex.dir === 'asc') ex.dir = 'desc';
		else this.sortChain = this.sortChain.filter(s => s.key !== key);
		this._renderSortStates();
		this.currentPage = 1;
		this._applyFilters();
	},

	_renderSortStates() {
		document.querySelectorAll('.sort-chip').forEach(chip => {
			const key = chip.dataset.key;
			const act = this.sortChain.find(s => s.key === key);
			chip.classList.toggle('active', !!act);
			const dir = chip.querySelector('.toggle-dir');
			if (dir) dir.textContent = act ? (act.dir === 'asc' ? '↑' : '↓') : '';
		});

		const container = document.getElementById('activeSorts');
		container.innerHTML = this.sortChain.map(s => {
			const label = s.key === 'first_seen' ? 'First seen' : s.key.charAt(0).toUpperCase() + s.key.slice(1);
			return `<span class="active-sort-tag">${label} ${s.dir === 'asc' ? '↑' : '↓'} <span class="remove-sort" data-key="${s.key}">✕</span></span>`;
		}).join('');
		container.querySelectorAll('.remove-sort').forEach(btn => {
			btn.addEventListener('click', e => {
				e.stopPropagation();
				this.sortChain = this.sortChain.filter(s => s.key !== btn.dataset.key);
				this._renderSortStates();
				this.currentPage = 1;
				this._applyFilters();
			});
		});
	},

	_extractGenres() {
		const set = new Set();
		this.allUsers.forEach(u => {
			if (u.current_prices) Object.keys(u.current_prices).forEach(g => set.add(g));
		});
		this.genreList = [...set].sort();
		const sel = document.getElementById('genreFilter');
		sel.innerHTML = '<option value="">All genres</option>';
		this.genreList.forEach(g => {
			const o = document.createElement('option');
			o.value = g; o.textContent = g;
			sel.appendChild(o);
		});
		sel.value = this.filterGenre;
	},

// ================================================================
// UI — user cards, detail expansion, pagination
// ================================================================

	_createCardHTML(user) {
		const avatar = user.avatar_url || '';
		const sn = user.screen_name;
		const prices = user.current_prices || {};
		const chips = Object.entries(prices).map(([g, v]) =>
			`<span class="price-chip">${g}: ¥${v.toLocaleString()}</span>`
		).join('');

		let badges = '';
		if (user.acceptable) badges += '<span class="badge badge-open">Open</span>';
		else if (user.acceptable !== undefined) badges += '<span class="badge badge-closed">Closed</span>';
		if (user.nsfw) badges += '<span class="badge badge-nsfw">NSFW</span>';
		if (user._tags && user._tags.length) {
			badges += user._tags.map(t => `<span class="badge badge-tag">${t}</span>`).join('');
		}

		const thumbs = user.latest_thumbnails || [];
		const thumbHtml = thumbs.length
			? `<div class="thumb-strip">${thumbs.slice(0, 4).map(src =>
				`<img src="${src}" loading="lazy" onerror="this.style.display='none'" alt="work">`
			).join('')}</div>`
			: '<div style="height:100px;background:var(--surface3);display:flex;align-items:center;justify-content:center;color:var(--text-secondary);">No previews</div>';

		return `<div class="user-card" data-screenname="${sn}" data-file="${user.file || ''}">
			<div class="card-main">
				<div class="card-header">
					<img class="card-avatar" src="${avatar}" alt="${sn}" onerror="this.style.background='#333'">
					<div class="card-identity">
						<a class="card-name-link" href="https://skeb.jp/@${sn}" target="_blank" onclick="event.stopPropagation()">@${sn}</a>
					</div>
					<div class="prices-summary">${chips || '<span style="color:var(--text-secondary)">No prices</span>'}</div>
				</div>
				<div class="badges">${badges}</div>
				${thumbHtml}
				<div class="card-footer">
					<span><iconify-icon icon="mdi:image-multiple" width="14"></iconify-icon> ${user.total_works || 0}</span>
					<span><iconify-icon icon="mdi:clock-outline" width="14"></iconify-icon> ${this._fmtDate(user.last_updated)}</span>
					<span><iconify-icon icon="mdi:calendar-plus" width="14"></iconify-icon> ${this._fmtDate(user.first_seen)}</span>
				</div>
			</div>
			<div class="detail-expand" id="detail-${sn}"></div>
		</div>`;
	},

	_renderUsers() {
		const grid = document.getElementById('userGrid');
		const start = (this.currentPage - 1) * this.perPage;
		const page = this.filteredUsers.slice(start, start + this.perPage);

		if (!page.length) {
			grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary);">No creators match your filters.</div>';
			return;
		}

		grid.innerHTML = page.map(u => this._createCardHTML(u)).join('');

		grid.querySelectorAll('.user-card').forEach(card => {
			const sn = card.dataset.screenname;
			const file = card.dataset.file;
			const detail = card.querySelector('.detail-expand');
			const main = card.querySelector('.card-main');

			main.addEventListener('click', e => {
				if (e.target.closest('a')) return;
				if (detail.classList.contains('open')) {
					detail.classList.remove('open');
					card.classList.remove('expanded');
				} else {
					detail.classList.add('open');
					card.classList.add('expanded');
					if (!detail.dataset.loaded) this._loadDetail(sn, file, detail);
				}
			});

			detail.addEventListener('click', e => {
				if (e.target.closest('a, button, input, select, textarea, [role="button"]')) return;
				e.stopPropagation();
				detail.classList.remove('open');
				card.classList.remove('expanded');
			});
		});
	},

	async _loadDetail(sn, filePath, container) {
		if (!filePath) {
			container.innerHTML = '<div style="padding:1rem;color:var(--text-secondary);">No detailed data available for this entry.</div>';
			return;
		}
		container.innerHTML = '<div class="loader"><div class="spinner"></div></div>';
		try {
			if (this.detailCache[sn]) {
				this._renderDetail(this.detailCache[sn], container);
				container.dataset.loaded = 'true';
				return;
			}
			const r = await this._fetch(`skeb/${filePath}.json`);
			if (!r.ok) throw new Error('Not found');
			const data = await r.json();
			this.detailCache[sn] = data;
			this._renderDetail(data, container);
			container.dataset.loaded = 'true';
		} catch (e) {
			container.innerHTML = `<div style="padding:1rem;color:var(--red)">Failed to load details: ${e.message}</div>`;
		}
	},

	_renderDetail(data, container) {
		const p = data.profile || {};
		const header = p.header_url
			? `<img src="${p.header_url}" style="width:100%;height:120px;object-fit:cover;margin-bottom:0.8rem;border:1px solid var(--border);" alt="header">`
			: '';

		const links = [];
		if (p.pixiv_id) links.push(`<a href="https://www.pixiv.net/en/users/${p.pixiv_id}" target="_blank">Pixiv</a>`);
		if (p.url) links.push(`<a href="${p.url}" target="_blank">Website</a>`);
		(p.user_service_links || []).forEach(l => {
			if (!l.url) return;
			if (l.provider === 'twitter') links.unshift(`<a href="${l.url}" target="_blank">𝕏 Twitter</a>`);
			else links.push(`<a href="${l.url}" target="_blank">${l.provider}</a>`);
		});

		const skills = p.skills || data.skills || [];
		const priceHist = data.price_history || {};
		const works = p.received_works || [];
		const worksHtml = works.length
			? works.map(w => {
				const src = w.thumbnail_image_urls?.src || w.private_thumbnail_image_urls?.src || w.censored_thumbnail_image_urls?.src || '';
				const url = w.path ? `https://skeb.jp${w.path}` : '#';
				return src ? `<a href="${url}" target="_blank"><img class="work-thumb" src="${src}" alt="work" loading="lazy"></a>` : '';
			}).join('')
			: '<span style="color:var(--text-secondary)">No visible works</span>';

		container.innerHTML = `${header}
			<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:0.8rem;font-size:0.85rem;">
				<span>Accepting: <strong>${p.acceptable ? 'Yes' : 'No'}</strong></span>
				<span>NSFW: <strong>${p.nsfw_acceptable ? 'Yes' : 'No'}</strong></span>
				<span>Creator: <strong>${p.creator ? 'Yes' : 'No'}</strong></span>
				<span>Language: ${p.language || '?'}</span>
				<span>Works: ${p.received_works_count || 0}</span>
			</div>
			<div class="social-links">${links.join(' ') || 'No links'}</div>
			<div class="detail-section">
				<h3>Skills & Prices</h3>
				<ul>${skills.map(s => `<li>${s.genre}: ¥${s.default_amount?.toLocaleString()}</li>`).join('')}</ul>
			</div>
			<div class="detail-section">
				<h3>Price History</h3>
				${Object.keys(priceHist).length
					? Object.entries(priceHist).map(([g, entries]) => `
						<div style="margin-bottom:0.8rem;">
							<strong style="color:var(--accent)">${g}</strong>
							<table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
								${entries.map(e => `<tr><td style="padding:0.25rem;">${this._fmtDate(e.recorded_at)}</td><td>¥${e.amount.toLocaleString()}</td></tr>`).join('')}
							</table>
						</div>`).join('')
					: '<p>No history</p>'}
			</div>
			<div class="detail-section">
				<h3>Received Works</h3>
				<div class="works-grid">${worksHtml}</div>
			</div>`;
	},

	_renderPagination() {
		const total = Math.ceil(this.filteredUsers.length / this.perPage);
		const c = document.getElementById('pagination');
		if (total <= 1) { c.innerHTML = ''; return; }
		c.innerHTML = `
			<button class="page-btn" ${this.currentPage === 1 ? 'disabled' : ''} data-page="prev">◀</button>
			<span class="page-info">Page ${this.currentPage} of ${total}</span>
			<button class="page-btn" ${this.currentPage === total ? 'disabled' : ''} data-page="next">▶</button>`;
		c.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
			if (this.currentPage > 1) { this.currentPage--; this._renderUsers(); this._renderPagination(); this._updateURL(); window.scrollTo(0, 0); }
		});
		c.querySelector('[data-page="next"]')?.addEventListener('click', () => {
			if (this.currentPage < total) { this.currentPage++; this._renderUsers(); this._renderPagination(); this._updateURL(); window.scrollTo(0, 0); }
		});
	},

	_closeAllDetails() {
		document.querySelectorAll('.detail-expand.open').forEach(d => d.classList.remove('open'));
		document.querySelectorAll('.user-card.expanded').forEach(c => c.classList.remove('expanded'));
	},

// ================================================================
// UI — event binding
// ================================================================

	_bindEvents() {
		// --- text search ---
		document.getElementById('searchInput').addEventListener('input', this._debounce(() => {
			this.searchTerm = document.getElementById('searchInput').value.trim().toLowerCase();
			this.currentPage = 1;
			this._applyFilters();
		}, 300));

		// --- filter toggles ---
		document.getElementById('filterAcceptable').addEventListener('click', () => {
			this.filterAcceptable = this.filterAcceptable === null ? true : (this.filterAcceptable ? false : null);
			this.currentPage = 1; this._applyFilters();
		});
		document.getElementById('filterNsfw').addEventListener('click', () => {
			this.filterNsfw = this.filterNsfw === null ? true : (this.filterNsfw ? false : null);
			this.currentPage = 1; this._applyFilters();
		});
		document.getElementById('genreFilter').addEventListener('change', e => {
			this.filterGenre = e.target.value;
			this.currentPage = 1; this._applyFilters();
		});

		// --- range inputs ---
		const priceDebounced = this._debounce(() => {
			this.filterPriceMin = document.getElementById('priceMin').value ? +document.getElementById('priceMin').value : null;
			this.filterPriceMax = document.getElementById('priceMax').value ? +document.getElementById('priceMax').value : null;
			this.currentPage = 1; this._applyFilters();
		}, 500);
		document.getElementById('priceMin').addEventListener('input', priceDebounced);
		document.getElementById('priceMax').addEventListener('input', priceDebounced);

		const worksDebounced = this._debounce(() => {
			this.filterWorksMin = document.getElementById('worksMin').value ? +document.getElementById('worksMin').value : null;
			this.filterWorksMax = document.getElementById('worksMax').value ? +document.getElementById('worksMax').value : null;
			this.currentPage = 1; this._applyFilters();
		}, 500);
		document.getElementById('worksMin').addEventListener('input', worksDebounced);
		document.getElementById('worksMax').addEventListener('input', worksDebounced);

		document.getElementById('seenOlderDays').addEventListener('input', this._debounce(() => {
			this.filterSeenOlderDays = document.getElementById('seenOlderDays').value ? +document.getElementById('seenOlderDays').value : null;
			this.currentPage = 1; this._applyFilters();
		}, 500));
		document.getElementById('updatedWithinDays').addEventListener('input', this._debounce(() => {
			this.filterUpdatedWithinDays = document.getElementById('updatedWithinDays').value ? +document.getElementById('updatedWithinDays').value : null;
			this.currentPage = 1; this._applyFilters();
		}, 500));

		// --- reset ---
		document.getElementById('resetFilters').addEventListener('click', () => {
			this.searchTerm = '';
			this.filterAcceptable = null;
			this.filterNsfw = null;
			this.filterGenre = '';
			this.filterPriceMin = this.filterPriceMax = null;
			this.filterWorksMin = this.filterWorksMax = null;
			this.filterSeenOlderDays = null;
			this.filterUpdatedWithinDays = null;
			this.sortChain = [];
			this.filterAlbumTags = [];
			this.currentPage = 1;
			document.getElementById('searchInput').value = '';
			this._updateFilterButtonsUI();
			this._renderSortStates();
			this._applyFilters();
		});

		// --- sort chips ---
		document.querySelectorAll('.sort-chip').forEach(chip => {
			chip.addEventListener('click', () => this._toggleSortKey(chip.dataset.key));
		});

		// --- detail close on outside click ---
		document.addEventListener('click', e => {
			if (!e.target.closest('.user-card')) this._closeAllDetails();
		});

		// --- album modal ---
		document.getElementById('albumSelectBtn').addEventListener('click', () => this._openAlbumModal());
		document.getElementById('albumModalBg').addEventListener('click', () => this._closeAlbumModal());
		document.getElementById('albumModalClose').addEventListener('click', () => this._closeAlbumModal());
		document.getElementById('albumModalSearch').addEventListener('input', this._debounce(() => {
			this._renderAlbumModalList(document.getElementById('albumModalSearch').value);
		}, 200));
		document.getElementById('albumModalExternal').addEventListener('click', () => this._handleExternalAlbumPrompt());

		// --- album type filter chips ---
		document.querySelectorAll('#albumModalTypeFilters .album-type-chip').forEach(chip => {
			chip.addEventListener('click', () => {
				this.albumModalTypeFilter = chip.dataset.type;
				this._renderAlbumModalTypeChips();
				this._renderAlbumModalList(document.getElementById('albumModalSearch').value);
			});
		});

		// --- escape ---
		document.addEventListener('keydown', e => {
			if (e.key === 'Escape') this._closeAlbumModal();
		});

		// --- popstate ---
		window.addEventListener('popstate', () => {
			this._readURLParams();
			if (!this.loadingComplete) return;
			if (this.currentAlbum && this.currentAlbum._externalUrl) {
				this._loadExternalAlbum(this.currentAlbum._externalUrl);
			} else if (this.currentAlbum && this.currentAlbum.name !== 'main_index') {
				this._switchAlbum(this.currentAlbum.name);
			} else {
				this._switchAlbum('main_index');
			}
		});
	},

// ================================================================
// UTILS
// ================================================================

	_fmtDate(iso) {
		if (!iso) return '\u2014';
		const d = new Date(iso * 1000);
		const now = new Date();

		const dateStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

		const diff = Math.floor((now - d) / 1000);
		const units = [
			{ label: 'year',   sec: 31536000 },
			{ label: 'month',  sec: 2592000 },
			{ label: 'day',    sec: 86400 },
			{ label: 'hour',   sec: 3600 },
			{ label: 'minute', sec: 60 },
		];
		let ago = 'just now';
		for (const u of units) {
			const n = Math.floor(diff / u.sec);
			if (n >= 1) { ago = `${n} ${u.label}${n > 1 ? 's' : ''} ago`; break; }
		}
		return `${dateStr} (${ago})`;
	},

	_debounce(fn, delay) {
		let t;
		return (...args) => { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), delay); };
	}

};

document.addEventListener('DOMContentLoaded', () => App.init());
