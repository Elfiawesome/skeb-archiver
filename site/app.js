const App = {
	meta: null,
	pages: {},
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

	async getAlbum(urlPath, name) {
		let currentIndex = 1;
		let currentSize = 0;
		let totalSize = null;
		const batchSize = 10;
		const chunks = [];
		const fullUrl = `${urlPath}/${name}.album/${name}.`;

		while (totalSize === null || currentSize < totalSize) {
			const fetches = [];
			for (let i = 0; i < batchSize; i++) {
				fetches.push(
					this.fetch(`${fullUrl}${currentIndex + i}`)
				);
			}

			const responses = await Promise.all(fetches);

			for (const [idx, resp] of responses.entries()) {
				if (!resp.ok) { continue; }

				const buffer = await resp.arrayBuffer();

				if (totalSize === null) {
					const view = new DataView(buffer);
					totalSize = view.getUint32(0, false) + 4;
				}

				chunks.push(buffer);
				currentSize += buffer.byteLength;
			}
			currentIndex += batchSize;

			console.log(`Fetched up to chunk ${currentIndex - 1}, downloaded ${currentSize} / ${totalSize} bytes`);
		}

		const finalBuffer = new Uint8Array(totalSize);
		let offset = 0;
		for (const chunk of chunks) {
			finalBuffer.set(new Uint8Array(chunk), offset);
			offset += chunk.byteLength;
		}

		const compressedData = finalBuffer.slice(4);
		const decompressedStream = new Response(compressedData)
			.body
			.pipeThrough(new DecompressionStream('gzip'));
		const decompressedBuffer = await new Response(decompressedStream).arrayBuffer();
		const textDecoder = new TextDecoder('utf-8');
		const jsonString = textDecoder.decode(decompressedBuffer);
		const data = JSON.parse(jsonString);
		
		data.name
		data.timestamp
		
		console.log(data);
		return data;
	},


	async init() {
		try {
			this.getAlbum('albums', 'main_index')
			// this.timeNow = new Date();

			// const r = await this.fetch("api/index.json");
			// if (!r.ok) throw new Error("HTTP " + r.status);
			// this.meta = await r.json();

			// document.querySelector('#statsBadge span').textContent =
			// 	`${this.meta.user_count?.toLocaleString() || '?'} users · ${this.meta.total_pages} pages` +
			// 	(this.meta.generated_at ? ` · ${this.fmtDate(this.meta.generated_at)}` : '');

			// this.readURLParams();
			// this.bindEvents();
			// this.renderSortStates();

			// const totalPages = this.meta.total_pages || 0;
			// document.getElementById('progressContainer').classList.remove('hidden');
			// for (let i = 0; i < totalPages; i++) {
			// 	await this.loadPage(i);
			// 	const progress = ((i + 1) / totalPages) * 100;
			// 	document.getElementById('progressFill').style.width = progress + '%';
			// 	if (this.pages[i]) this.allUsers.push(...this.pages[i]);
			// }
			// document.getElementById('progressContainer').classList.add('hidden');
			// this.loadingComplete = true;

			// this.extractGenres();
			// this.applyFilters();
		} catch (e) {
			console.error("Init failed:", e);
		}
	},

	async loadAlbum() {

	},

	async loadPage(num) {
		try {
			const r = await this.fetch(`api/pages/${num}.json.gz`);
			if (!r.ok) throw new Error("HTTP " + r.status);
			const resp = this.decompressRequest(r);
			const data = await resp.json();
			this.pages[num] = data.users || [];
		} catch (e) {
			console.warn(`Page ${num} failed:`, e);
			this.pages[num] = [];
		}
	},

	decompressRequest(resp) {
		const ds = new DecompressionStream("gzip");
		return new Response(resp.body.pipeThrough(ds));
	},

	async fetch(url) {
		var data = await fetch(url);
		if (!data.ok) {
			data = await fetch("https://raw.githubusercontent.com/Elfiawesome/skeb-archiver/refs/heads/archive/" + url);
		}
		return data;
	},

	fmtDate(iso) {
		if (!iso) return "\u2014";

		const date = new Date(iso * 1000);
		const now = new Date();

		const dateStr = date.toLocaleDateString('en-GB', {
			day: '2-digit',
			month: 'short',
			year: 'numeric'
		});

		const diff = Math.floor((now - date) / 1000);
		let agoString = "just now";

		const units = [
			{ label: "year", sec: 31536000 },
			{ label: "month", sec: 2592000 },
			{ label: "day", sec: 86400 },
			{ label: "hour", sec: 3600 },
			{ label: "minute", sec: 60 }
		];

		for (const unit of units) {
			const amount = Math.floor(diff / unit.sec);
			if (amount >= 1) {
				agoString = `${amount} ${unit.label}${amount > 1 ? 's' : ''} ago`;
				break;
			}
		}

		return `${dateStr} (${agoString})`;
	},

	extractGenres() {
		const genres = new Set();
		this.allUsers.forEach(u => {
			if (u.current_prices) Object.keys(u.current_prices).forEach(g => genres.add(g));
		});
		this.genreList = Array.from(genres).sort();
		const sel = document.getElementById('genreFilter');
		sel.innerHTML = '<option value="">All genres</option>';
		this.genreList.forEach(g => {
			const opt = document.createElement('option');
			opt.value = g; opt.textContent = g;
			sel.appendChild(opt);
		});
		sel.value = this.filterGenre;
	},

	readURLParams() {
		const params = new URLSearchParams(window.location.search);
		this.searchTerm = params.get('search') || '';
		document.getElementById('searchInput').value = this.searchTerm;

		const acc = params.get('acceptable');
		this.filterAcceptable = acc === 'true' ? true : (acc === 'false' ? false : null);
		const nsfw = params.get('nsfw');
		this.filterNsfw = nsfw === 'true' ? true : (nsfw === 'false' ? false : null);
		this.filterGenre = params.get('genre') || '';
		this.filterPriceMin = params.get('minPrice') ? Number(params.get('minPrice')) : null;
		this.filterPriceMax = params.get('maxPrice') ? Number(params.get('maxPrice')) : null;
		this.filterWorksMin = params.get('worksMin') ? Number(params.get('worksMin')) : null;
		this.filterWorksMax = params.get('worksMax') ? Number(params.get('worksMax')) : null;
		this.filterSeenOlderDays = params.get('seenOlderDays') ? Number(params.get('seenOlderDays')) : null;
		this.filterUpdatedWithinDays = params.get('updatedWithin') ? Number(params.get('updatedWithin')) : null;
		this.currentPage = parseInt(params.get('page')) || 1;

		const sortStr = params.get('sort') || '';
		this.sortChain = sortStr ? sortStr.split(',').map(s => {
			const dir = s.split('_').at(-1);
			const key = s.replace("_" + dir, "");
			console.log(key);
			return { key, dir: dir === 'desc' ? 'desc' : 'asc' };
		}).filter(s => s.key) : [];

		this.updateFilterButtonsUI();
	},

	updateURL() {
		const params = new URLSearchParams();
		if (this.searchTerm) params.set('search', this.searchTerm);
		if (this.filterAcceptable !== null) params.set('acceptable', this.filterAcceptable);
		if (this.filterNsfw !== null) params.set('nsfw', this.filterNsfw);
		if (this.filterGenre) params.set('genre', this.filterGenre);
		if (this.filterPriceMin !== null) params.set('minPrice', this.filterPriceMin);
		if (this.filterPriceMax !== null) params.set('maxPrice', this.filterPriceMax);
		if (this.filterWorksMin !== null) params.set('worksMin', this.filterWorksMin);
		if (this.filterWorksMax !== null) params.set('worksMax', this.filterWorksMax);
		if (this.filterSeenOlderDays !== null) params.set('seenOlderDays', this.filterSeenOlderDays);
		if (this.filterUpdatedWithinDays !== null) params.set('updatedWithin', this.filterUpdatedWithinDays);
		if (this.sortChain.length) params.set('sort', this.sortChain.map(s => s.key + '_' + s.dir).join(','));
		if (this.currentPage > 1) params.set('page', this.currentPage);
		const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
		history.replaceState(null, '', newUrl);
	},

	updateFilterButtonsUI() {
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

	bindEvents() {
		document.getElementById('searchInput').addEventListener('input', this.debounce(() => {
			this.searchTerm = document.getElementById('searchInput').value.trim().toLowerCase();
			this.currentPage = 1;
			this.applyFilters();
		}, 300));

		document.getElementById('filterAcceptable').addEventListener('click', () => {
			this.filterAcceptable = this.filterAcceptable === null ? true : (this.filterAcceptable ? false : null);
			this.currentPage = 1;
			this.applyFilters();
		});

		document.getElementById('filterNsfw').addEventListener('click', () => {
			this.filterNsfw = this.filterNsfw === null ? true : (this.filterNsfw ? false : null);
			this.currentPage = 1;
			this.applyFilters();
		});

		document.getElementById('genreFilter').addEventListener('change', (e) => {
			this.filterGenre = e.target.value;
			this.currentPage = 1;
			this.applyFilters();
		});

		const applyPrice = this.debounce(() => {
			this.filterPriceMin = document.getElementById('priceMin').value ? Number(document.getElementById('priceMin').value) : null;
			this.filterPriceMax = document.getElementById('priceMax').value ? Number(document.getElementById('priceMax').value) : null;
			this.currentPage = 1;
			this.applyFilters();
		}, 500);
		document.getElementById('priceMin').addEventListener('input', applyPrice);
		document.getElementById('priceMax').addEventListener('input', applyPrice);

		const applyWorks = this.debounce(() => {
			this.filterWorksMin = document.getElementById('worksMin').value ? Number(document.getElementById('worksMin').value) : null;
			this.filterWorksMax = document.getElementById('worksMax').value ? Number(document.getElementById('worksMax').value) : null;
			this.currentPage = 1;
			this.applyFilters();
		}, 500);
		document.getElementById('worksMin').addEventListener('input', applyWorks);
		document.getElementById('worksMax').addEventListener('input', applyWorks);

		document.getElementById('seenOlderDays').addEventListener('input', this.debounce(() => {
			this.filterSeenOlderDays = document.getElementById('seenOlderDays').value ? Number(document.getElementById('seenOlderDays').value) : null;
			this.currentPage = 1;
			this.applyFilters();
		}, 500));

		document.getElementById('updatedWithinDays').addEventListener('input', this.debounce(() => {
			this.filterUpdatedWithinDays = document.getElementById('updatedWithinDays').value ? Number(document.getElementById('updatedWithinDays').value) : null;
			this.currentPage = 1;
			this.applyFilters();
		}, 500));

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
			this.currentPage = 1;
			document.getElementById('searchInput').value = '';
			this.updateFilterButtonsUI();
			this.renderSortStates();
			this.applyFilters();
		});

		document.querySelectorAll('.sort-chip').forEach(chip => {
			chip.addEventListener('click', () => {
				const key = chip.dataset.key;
				this.toggleSortKey(key);
			});
		});

		document.addEventListener('click', (e) => {
			if (!e.target.closest('.user-card')) {
				this.closeAllDetails();
			}
		});

		window.addEventListener('popstate', () => {
			this.readURLParams();
			if (this.loadingComplete) {
				this.renderSortStates();
				this.applyFilters();
			}
		});
	},

	toggleSortKey(key) {
		const existing = this.sortChain.find(s => s.key === key);
		if (!existing) {
			this.sortChain.push({ key, dir: 'asc' });
		} else if (existing.dir === 'asc') {
			existing.dir = 'desc';
		} else {
			this.sortChain = this.sortChain.filter(s => s.key !== key);
		}
		this.renderSortStates();
		this.currentPage = 1;
		this.applyFilters();
	},

	renderSortStates() {
		document.querySelectorAll('.sort-chip').forEach(chip => {
			const key = chip.dataset.key;
			const active = this.sortChain.find(s => s.key === key);
			chip.classList.toggle('active', !!active);
			const dirSpan = chip.querySelector('.toggle-dir');
			if (dirSpan) dirSpan.textContent = active ? (active.dir === 'asc' ? '↑' : '↓') : '';
		});

		const container = document.getElementById('activeSorts');
		container.innerHTML = this.sortChain.map(s => {
			const label = s.key === 'first_seen' ? 'First seen' : s.key.charAt(0).toUpperCase() + s.key.slice(1);
			return `<span class="active-sort-tag">${label} ${s.dir === 'asc' ? '↑' : '↓'} <span class="remove-sort" data-key="${s.key}">✕</span></span>`;
		}).join('');
		container.querySelectorAll('.remove-sort').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				const key = btn.dataset.key;
				this.sortChain = this.sortChain.filter(s => s.key !== key);
				this.renderSortStates();
				this.currentPage = 1;
				this.applyFilters();
			});
		});
	},

	closeAllDetails() {
		document.querySelectorAll('.detail-expand.open').forEach(d => d.classList.remove('open'));
		document.querySelectorAll('.user-card.expanded').forEach(c => c.classList.remove('expanded'));
	},

	debounce(fn, delay) {
		let timer;
		return (...args) => {
			clearTimeout(timer);
			timer = setTimeout(() => fn.apply(this, args), delay);
		};
	},

	applyFilters() {
		let filtered = [...this.allUsers];
		const now = Date.now() / 1000;

		if (this.searchTerm) {
			const term = this.searchTerm;
			filtered = filtered.filter(u => u.screen_name && u.screen_name.toLowerCase().includes(term));
		}
		if (this.filterAcceptable !== null) filtered = filtered.filter(u => u.acceptable === this.filterAcceptable);
		if (this.filterNsfw !== null) filtered = filtered.filter(u => u.nsfw === this.filterNsfw);
		if (this.filterGenre) filtered = filtered.filter(u => u.current_prices && u.current_prices.hasOwnProperty(this.filterGenre));

		if (this.filterPriceMin !== null || this.filterPriceMax !== null) {
			filtered = filtered.filter(u => {
				const currentPrices = this.getUserPricesByGenre(u, this.filterGenre)
				if (!currentPrices) return false;
				const minP = Math.min(...currentPrices);
				const maxP = Math.max(...currentPrices);
				if (this.filterPriceMin !== null && maxP < this.filterPriceMin) return false;
				if (this.filterPriceMax !== null && minP > this.filterPriceMax) return false;
				return true;
			});
		}
		if (this.filterWorksMin !== null) filtered = filtered.filter(u => (u.total_works || 0) >= this.filterWorksMin);
		if (this.filterWorksMax !== null) filtered = filtered.filter(u => (u.total_works || 0) <= this.filterWorksMax);
		if (this.filterSeenOlderDays !== null) {
			const threshold = now - (this.filterSeenOlderDays * 86400);
			filtered = filtered.filter(u => u.first_seen && u.first_seen < threshold);
		}
		if (this.filterUpdatedWithinDays !== null) {
			const threshold = now - (this.filterUpdatedWithinDays * 86400);
			filtered = filtered.filter(u => u.last_updated && u.last_updated > threshold);
		}

		if (this.sortChain.length) {
			filtered.sort((a, b) => {
				for (let s of this.sortChain) {
					const cmp = this.compareBy(a, b, s);
					if (cmp !== 0) return cmp;
				}
				return 0;
			});
		}

		this.filteredUsers = filtered;
		this.updateFilterButtonsUI();
		this.updateURL();
		this.renderUsers();
		this.renderPagination();
	},

	getUserPricesByGenre(u, genre) {
		if (!u.current_prices || Object.keys(u.current_prices).length === 0) return null;
		if (genre) {
			if (genre in u.current_prices) {
				return [u.current_prices[genre]]
			} else {
				return null;
			}
		} else {
			return Object.values(u.current_prices);
		}
	},

	compareBy(a, b, sort) {
		const getPrice = (u) => {
			const currentPrices = this.getUserPricesByGenre(u, this.filterGenre);
			if (!currentPrices) { return Infinity; }
			else { return Math.min(...currentPrices); } // TODO: Issue here because how to compare and sort if there is a range of prices?
		};
		const getWorks = (u) => u.total_works || 0;
		const getUpdated = (u) => u.last_updated || 0;
		const getFirstSeen = (u) => u.first_seen || 0;

		let valA, valB;
		switch (sort.key) {
			case 'price': valA = getPrice(a); valB = getPrice(b); break;
			case 'works': valA = getWorks(a); valB = getWorks(b); break;
			case 'updated': valA = getUpdated(a); valB = getUpdated(b); break;
			case 'first_seen': valA = getFirstSeen(a); valB = getFirstSeen(b); break;
			default: return 0;
		}
		return sort.dir === 'asc' ? valA - valB : valB - valA;
	},

	createCardHTML(user) {
		const avatar = user.avatar_url || '';
		const screenName = user.screen_name;
		const prices = user.current_prices || {};
		const priceChips = Object.entries(prices).map(([genre, price]) =>
			`<span class="price-chip">${genre}: ¥${price.toLocaleString()}</span>`
		).join('');

		let badges = '';
		if (user.acceptable) badges += '<span class="badge badge-open">Open</span>';
		else badges += '<span class="badge badge-closed">Closed</span>';
		if (user.nsfw) badges += '<span class="badge badge-nsfw">NSFW</span>';

		const thumbs = user.latest_thumbnails || [];
		const thumbHtml = thumbs.length ?
			`<div class="thumb-strip">${thumbs.slice(0, 4).map(src =>
				`<img src="${src}" loading="lazy" onerror="this.style.display='none'" alt="work">`
			).join('')}</div>` :
			'<div style="height:100px;background:var(--surface3);display:flex;align-items:center;justify-content:center;color:var(--text-secondary);">No previews</div>';

		const totalWorks = user.total_works || 0;
		const lastUpdate = this.fmtDate(user.last_updated);
		const firstSeen = this.fmtDate(user.first_seen);

		return `
                <div class="user-card" data-screenname="${screenName}" data-file="${user.file || ''}">
                    <div class="card-main">
                        <div class="card-header">
                            <img class="card-avatar" src="${avatar}" alt="${screenName}" onerror="this.style.background='#333'">
                            <div class="card-identity">
                                <a class="card-name-link" href="https://skeb.jp/@${screenName}" target="_blank" onclick="event.stopPropagation()">@${screenName}</a>
                            </div>
                            <div class="prices-summary">${priceChips || '<span style="color:var(--text-secondary)">No prices</span>'}</div>
                        </div>
                        <div class="badges">${badges}</div>
                        ${thumbHtml}
                        <div class="card-footer">
                            <span><iconify-icon icon="mdi:image-multiple" width="14"></iconify-icon> ${totalWorks}</span>
                            <span><iconify-icon icon="mdi:clock-outline" width="14"></iconify-icon> ${lastUpdate}</span>
                            <span><iconify-icon icon="mdi:calendar-plus" width="14"></iconify-icon> ${firstSeen}</span>
                        </div>
                    </div>
                    <div class="detail-expand" id="detail-${screenName}"></div>
                </div>`;
	},

	renderUsers() {
		const grid = document.getElementById('userGrid');
		const start = (this.currentPage - 1) * this.perPage;
		const pageUsers = this.filteredUsers.slice(start, start + this.perPage);

		if (pageUsers.length === 0) {
			grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary);">No creators match your filters.</div>';
			return;
		}

		grid.innerHTML = pageUsers.map(u => this.createCardHTML(u)).join('');

		grid.querySelectorAll('.user-card').forEach(card => {
			const screenName = card.dataset.screenname;
			const file = card.dataset.file;
			const detailDiv = card.querySelector('.detail-expand');
			const mainArea = card.querySelector('.card-main');

			// Toggle detail on main click
			mainArea.addEventListener('click', (e) => {
				// Prevent closing if clicking on the name link
				if (e.target.closest('a')) return;
				const isOpen = detailDiv.classList.contains('open');

				if (isOpen) {
					detailDiv.classList.remove('open');
					card.classList.remove('expanded');
				} else {
					detailDiv.classList.add('open');
					card.classList.add('expanded');
					if (!detailDiv.dataset.loaded) {
						this.loadAndRenderDetail(screenName, file, detailDiv);
					}
				}
			});

			detailDiv.addEventListener('click', (e) => {
				if (e.target.closest('a, button, input, select, textarea, [role="button"]')) return;
				e.stopPropagation();
				detailDiv.classList.remove('open');
				card.classList.remove('expanded');
			});
		});
	},

	async loadAndRenderDetail(screenName, filePath, container) {
		container.innerHTML = '<div class="loader"><div class="spinner"></div></div>';
		try {
			if (this.detailCache[screenName]) {
				this.renderDetailContent(this.detailCache[screenName], container);
				container.dataset.loaded = 'true';
				return;
			}
			const r = await this.fetch(`skeb/${filePath}.json`);
			if (!r.ok) throw new Error("Not found");
			const data = await r.json();
			this.detailCache[screenName] = data;
			this.renderDetailContent(data, container);
			container.dataset.loaded = 'true';
		} catch (e) {
			container.innerHTML = `<div style="padding:1rem;color:var(--red)">Failed to load details: ${e.message}</div>`;
		}
	},

	renderDetailContent(data, container) {
		const p = data.profile || {};
		const headerImg = p.header_url ? `<img src="${p.header_url}" style="width:100%;height:120px;object-fit:cover;margin-bottom:0.8rem;border:1px solid var(--border);" alt="header">` : '';

		const socialLinks = [];
		if (p.pixiv_id) socialLinks.push(`<a href="https://pixiv.me/${p.pixiv_id}" target="_blank">Pixiv</a>`);
		if (p.url) socialLinks.push(`<a href="${p.url}" target="_blank">Website</a>`);
		(p.user_service_links || []).forEach(link => {
			if (!link.url) { return; }
			if (link.provider == 'twitter') {
				socialLinks.unshift(`<a href="${link.url}" target="_blank">𝕏 Twitter</a>`);
			} else {
				socialLinks.push(`<a href="${link.url}" target="_blank">${link.provider}</a>`);
			}
		});

		const skills = p.skills || data.skills || [];
		const priceHistory = data.price_history || {};
		const works = p.received_works || [];
		const worksHtml = works.length ? works.map(w => {
			// Priority: thumbnail > private > censored
			const thumbSrc = w.thumbnail_image_urls?.src || w.private_thumbnail_image_urls?.src || w.censored_thumbnail_image_urls?.src || '';
			const workUrl = w.path ? `https://skeb.jp${w.path}` : '#';
			return thumbSrc ? `<a href="${workUrl}" target="_blank"><img class="work-thumb" src="${thumbSrc}" alt="work" loading="lazy"></a>` : '';
		}).join('') : '<span style="color:var(--text-secondary)">No visible works</span>';

		container.innerHTML = `
                    ${headerImg}
                    <div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:0.8rem;font-size:0.85rem;">
                        <span>Accepting: <strong>${p.acceptable ? 'Yes' : 'No'}</strong></span>
                        <span>NSFW: <strong>${p.nsfw_acceptable ? 'Yes' : 'No'}</strong></span>
                        <span>Creator: <strong>${p.creator ? 'Yes' : 'No'}</strong></span>
                        <span>Language: ${p.language || '?'}</span>
                        <span>Works: ${p.received_works_count || 0}</span>
                    </div>
                    <div class="social-links">${socialLinks.join(' ') || 'No links'}</div>
                    <div class="detail-section">
                        <h3>Skills & Prices</h3>
                        <ul>${skills.map(s => `<li>${s.genre}: ¥${s.default_amount?.toLocaleString()}</li>`).join('')}</ul>
                    </div>
                    <div class="detail-section">
                        <h3>Price History</h3>
                        ${Object.keys(priceHistory).length ? Object.entries(priceHistory).map(([genre, entries]) => `
                            <div style="margin-bottom:0.8rem;">
                                <strong style="color:var(--accent)">${genre}</strong>
                                <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
                                    ${entries.map(e => `<tr><td style="padding:0.25rem;">${this.fmtDate(e.recorded_at)}</td><td>¥${e.amount.toLocaleString()}</td></tr>`).join('')}
                                </table>
                            </div>
                        `).join('') : '<p>No history</p>'}
                    </div>
                    <div class="detail-section">
                        <h3>Received Works</h3>
                        <div class="works-grid">${worksHtml}</div>
                    </div>
                `;
	},

	renderPagination() {
		const totalPages = Math.ceil(this.filteredUsers.length / this.perPage);
		const container = document.getElementById('pagination');
		if (totalPages <= 1) { container.innerHTML = ''; return; }
		container.innerHTML = `
                    <button class="page-btn" ${this.currentPage === 1 ? 'disabled' : ''} data-page="prev">◀</button>
                    <span class="page-info">Page ${this.currentPage} of ${totalPages}</span>
                    <button class="page-btn" ${this.currentPage === totalPages ? 'disabled' : ''} data-page="next">▶</button>
                `;
		container.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
			if (this.currentPage > 1) { this.currentPage--; this.renderUsers(); this.renderPagination(); this.updateURL(); window.scrollTo(0, 0); }
		});
		container.querySelector('[data-page="next"]')?.addEventListener('click', () => {
			if (this.currentPage < totalPages) { this.currentPage++; this.renderUsers(); this.renderPagination(); this.updateURL(); window.scrollTo(0, 0); }
		});
	}
};

document.addEventListener("DOMContentLoaded", () => App.init());