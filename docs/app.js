// @ts-nocheck
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function esc(s) {
	if (!s) return "";
	const d = document.createElement("div");
	d.textContent = s;
	return d.innerHTML;
}
function fmtDate(iso) {
	if (!iso) return "\u2014";

	const date = new Date(iso * 1000);
	const now = App.currentdate;

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

	return `${dateStr}<br>(${agoString})`;
}
function fmtYen(n) { return n != null ? "\u00a5" + Number(n).toLocaleString() : "\u2014"; }
function fmtRange(r) {
	if (!r) return "";
	return r.min === r.max ? fmtYen(r.min) : fmtYen(r.min) + " \u2013 " + fmtYen(r.max);
}
function truncate(s, n) {
	if (!s) return "";
	return s.length > n ? s.substring(0, n) + "\u2026" : s;
}

const App = {
	meta: null,
	pages: {},
	allUsers: [],
	filtered: [],
	visible: [],
	cache: {},
	loading: new Set(),
	expanded: new Set(),

	sortKey: "last_updated",
	sortAsc: false,
	search: "",
	genre: "art",
	priceMin: null,
	priceMax: null,
	page: 0,
	perPage: 50,
	currentdate: new Date(),

	knownFlags: [],
	flagFilters: {},          // flag -> null | "require" | "exclude"

	acceptableFilter: null,   // null = all, "require" = only acceptable, "exclude" = only not acceptable

	/* ── bootstrap ───────────────────────────────────────── */
	async init() {
		try {
			const r = await this.fetch("api/index.json");
			if (!r.ok) throw new Error("HTTP " + r.status);
			this.meta = await r.json();
			this.knownFlags = this.meta.known_flags || [];

			// Default: exclude "missing"
			if (this.knownFlags.includes("missing")) {
				this.flagFilters["missing"] = "exclude";
			}

			this.renderMeta();
			this.bind();

			const tasks = [];
			for (let i = 0; i < this.meta.total_pages; i++) tasks.push(this.loadPage(i));
			await Promise.all(tasks);

			this.allUsers = [];
			for (let i = 0; i < this.meta.total_pages; i++) {
				if (this.pages[i]) this.allUsers.push(...this.pages[i]);
			}
			this.update();
		} catch (e) {
			$("#tbody").innerHTML =
				'<tr><td colspan="6" class="msg">Failed to load \u2014 ' + esc(e.message) + "</td></tr>";
		}
	},

	decompressRequest(resp) {
		const decompressedStream = resp.body.pipeThrough(new DecompressionStream("gzip"));
		return new Response(decompressedStream)
	},

	async loadPage(num) {
		try {
			const r = await this.fetch("api/pages/" + num + ".json.gz");
			if (!r.ok) throw new Error("HTTP " + r.status);
			const resp = this.decompressRequest(r);
			const data = await resp.json()
			this.pages[num] = data.users || [];
		} catch (e) {
			this.pages[num] = [];
		}
	},

	renderMeta() {
		if (!this.meta) return;
		$("#meta").textContent =
			this.meta.user_count + " users \u00b7 " + fmtDate(this.meta.generated_at);
		$("#stats-bar").innerHTML =
			"<span>Users <strong>" + this.meta.user_count + "</strong></span>" +
			"<span>Generated <strong>" + fmtDate(this.meta.generated_at) + "</strong></span>";
	},

	/* ── events ──────────────────────────────────────────── */
	bind() {
		let t = null;
		$("#search").addEventListener("input", (e) => {
			clearTimeout(t);
			t = setTimeout(() => { this.search = e.target.value.toLowerCase().trim(); this.page = 0; this.update(); }, 200);
		});
		$("#genre-filter").addEventListener("change", (e) => {
			this.genre = e.target.value; this.page = 0; this.update();
		});
		$("#price-min").addEventListener("input", (e) => {
			this.priceMin = e.target.value ? Number(e.target.value) : null; this.page = 0; this.update();
		});
		$("#price-max").addEventListener("input", (e) => {
			this.priceMax = e.target.value ? Number(e.target.value) : null; this.page = 0; this.update();
		});
		$$("th[data-sort]").forEach((th) => {
			th.addEventListener("click", () => {
				const k = th.dataset.sort;
				if (this.sortKey === k) this.sortAsc = !this.sortAsc;
				else { this.sortKey = k; this.sortAsc = k === "screen_name"; }
				this.page = 0; this.update();
			});
		});
		$("#acceptable-filter").addEventListener("click", () => {
			const cur = this.acceptableFilter;
			if (cur === null) this.acceptableFilter = "require";
			else if (cur === "require") this.acceptableFilter = "exclude";
			else this.acceptableFilter = null;
			this.page = 0;
			this.update();
		});
	},

	/* ── price ───────────────────────────────────────────── */
	getPrice(u) {
		const cp = u.current_prices || {};
		if (this.genre !== "all") return cp[this.genre] ?? null;
		for (const g of ["art", "voice", "novel", "comic"]) {
			if (cp[g] != null) return cp[g];
		}
		return null;
	},

	/* ── filter + sort ───────────────────────────────────── */
	filter() {
		let list = this.allUsers;

		if (this.search)
			list = list.filter(u => u.screen_name.toLowerCase().includes(this.search));

		if (this.genre !== "all")
			list = list.filter(u => (u.current_prices || {})[this.genre] != null);

		if (this.priceMin != null || this.priceMax != null) {
			list = list.filter(u => {
				const p = this.getPrice(u);
				if (p == null) return false;
				if (this.priceMin != null && p < this.priceMin) return false;
				if (this.priceMax != null && p > this.priceMax) return false;
				return true;
			});
		}

		// Acceptable filter
		if (this.acceptableFilter === "require") {
			list = list.filter(u => u.acceptable === true);
		} else if (this.acceptableFilter === "exclude") {
			list = list.filter(u => !u.acceptable);
		}

		// Flag filters
		for (const [flag, mode] of Object.entries(this.flagFilters)) {
			if (!mode) continue;
			if (mode === "require") {
				list = list.filter(u => !!(u.flags || {})[flag]);
			} else if (mode === "exclude") {
				list = list.filter(u => !(u.flags || {})[flag]);
			}
		}

		const key = this.sortKey;
		const dir = this.sortAsc ? 1 : -1;
		const self = this;

		list = list.slice().sort((a, b) => {
			let va, vb;
			switch (key) {
				case "screen_name":
					va = a.screen_name.toLowerCase();
					vb = b.screen_name.toLowerCase();
					return va < vb ? -dir : va > vb ? dir : 0;
				case "price":
					va = self.getPrice(a) ?? -1;
					vb = self.getPrice(b) ?? -1;
					return (va - vb) * dir;
				case "total_works":
					return ((a.total_works || 0) - (b.total_works || 0)) * dir;
				case "first_seen":
				case "last_updated":
					va = a[key] || ""; vb = b[key] || "";
					return va < vb ? -dir : va > vb ? dir : 0;
				default: return 0;
			}
		});
		this.filtered = list;
	},

	/* ── render pipeline ─────────────────────────────────── */
	update() {
		this.filter();
		this.renderArrows();
		this.renderAcceptableBtn();

		const totalPages = Math.max(1, Math.ceil(this.filtered.length / this.perPage));
		if (this.page >= totalPages) this.page = totalPages - 1;
		if (this.page < 0) this.page = 0;

		const start = this.page * this.perPage;
		this.visible = this.filtered.slice(start, start + this.perPage);

		this.renderFlagBar();
		this.renderTable();
		this.renderPagination(totalPages);
	},

	renderArrows() {
		$$("th[data-sort]").forEach(th => {
			let a = th.querySelector(".arrow");
			if (!a) { a = document.createElement("span"); a.className = "arrow"; th.appendChild(a); }
			a.textContent = th.dataset.sort === this.sortKey
				? (this.sortAsc ? " \u25b2" : " \u25bc") : "";
		});
	},

	/* ── acceptable button ───────────────────────────────── */
	renderAcceptableBtn() {
		const btn = $("#acceptable-filter");
		if (!btn) return;
		const mode = this.acceptableFilter;
		btn.className = "acceptable-btn";
		if (mode === "require") {
			btn.className += " require";
			btn.textContent = "Accepting \u2713";
		} else if (mode === "exclude") {
			btn.className += " exclude";
			btn.textContent = "Not Accepting \u00d7";
		} else {
			btn.textContent = "Accepting Requests";
		}
	},

	/* ── flag bar ────────────────────────────────────────── */
	renderFlagBar() {
		const el = $("#flag-bar");
		if (!this.knownFlags.length) { el.innerHTML = ""; return; }

		let html = '<span class="flag-bar-label">Flags</span>';
		for (const flag of this.knownFlags) {
			const mode = this.flagFilters[flag] || null;
			let cls = "flag-btn";
			let suffix = "";
			if (mode === "require") { cls += " require"; suffix = " \u2713"; }
			else if (mode === "exclude") { cls += " exclude"; suffix = " \u00d7"; }
			html += '<button class="' + cls + '" data-flag="' + esc(flag) + '">' +
				esc(flag) + suffix + "</button>";
		}

		// count how many are filtered
		const activeCount = Object.values(this.flagFilters).filter(v => v).length;
		if (activeCount) {
			html += '<span style="font-size:10px;color:var(--text-3);margin-left:8px">' +
				this.filtered.length + " shown</span>";
		}

		el.innerHTML = html;

		const self = this;
		el.querySelectorAll(".flag-btn").forEach(btn => {
			btn.addEventListener("click", () => {
				const f = btn.dataset.flag;
				const cur = self.flagFilters[f] || null;
				// cycle: null → require → exclude → null
				if (cur === null) self.flagFilters[f] = "require";
				else if (cur === "require") self.flagFilters[f] = "exclude";
				else delete self.flagFilters[f];
				self.page = 0;
				self.update();
			});
		});
	},

	/* ── preview cell ────────────────────────────────────── */
	renderPreviewCell(thumbs) {
		if (!thumbs || !thumbs.length) {
			return '<div class="preview-grid count-1"><div class="preview-empty">' +
				'<span>\u2014</span></div></div>';
		}
		const n = Math.min(thumbs.length, 4);
		let html = '<div class="preview-grid count-' + n + '">';
		for (let i = 0; i < n; i++) {
			html += '<img src="' + esc(thumbs[i]) + '" loading="lazy" alt=""' +
				' onerror="this.style.visibility=\'hidden\'">';
		}
		return html + "</div>";
	},

	/* ── flag badges for table row ─────────────────────── */
	renderFlagBadges(flags) {
		if (!flags) return "";
		let html = "";
		for (const [k, v] of Object.entries(flags)) {
			if (!v) continue;
			const cls = k === "missing" ? "flag-badge-missing" : "flag-badge-default";
			html += '<span class="flag-badge ' + cls + '">' + esc(k) + "</span>";
		}
		return html;
	},

	/* ── main table ──────────────────────────────────────── */
	renderTable() {
		const tbody = $("#tbody");
		if (!this.visible.length) {
			tbody.innerHTML = '<tr><td colspan="6" class="msg">No users match the filters</td></tr>';
			return;
		}
		const rows = [];
		for (const u of this.visible) {
			const name = u.screen_name;
			const open = this.expanded.has(name);
			const busy = this.loading.has(name);
			const price = this.getPrice(u);

			rows.push(
				'<tr class="row-user' + (open ? " active" : "") +
				'" data-name="' + esc(name) + '" data-file="' + esc(u.file) + '">' +

				'<td class="cell-preview">' + this.renderPreviewCell(u.latest_thumbnails) + "</td>" +

				'<td><div class="cell-user">' +
				(u.avatar_url
					? '<img class="avatar" src="' + esc(u.avatar_url) +
					'" loading="lazy" onerror="this.className=\'avatar-ph\'">'
					: '<div class="avatar-ph"></div>') +
				'<a class="user-link" href="https://skeb.jp/@' + esc(name) +
				'" target="_blank" rel="noopener">@' + esc(name) + "</a>" +
				this.renderFlagBadges(u.flags) +
				(u.acceptable
					? '<span class="acceptable-badge">open</span>'
					: '') +
				"</div></td>" +

				'<td class="cell-price">' + fmtYen(price) + "</td>" +
				'<td class="cell-num">' + (u.total_works || 0) + "</td>" +
				'<td class="cell-date">' + fmtDate(u.first_seen) + "</td>" +
				'<td class="cell-date">' + fmtDate(u.last_updated) + "</td>" +
				"</tr>"
			);

			if (open) {
				if (busy) {
					rows.push('<tr class="row-detail"><td colspan="6" class="msg">Loading \u2026</td></tr>');
				} else if (this.cache[name]) {
					rows.push(this.renderDetail(this.cache[name]));
				}
			}
		}
		tbody.innerHTML = rows.join("");

		const self = this;
		tbody.querySelectorAll(".row-user").forEach(tr => {
			tr.addEventListener("click", ev => {
				if (ev.target.tagName === "A") return;
				self.toggle(tr.dataset.name, tr.dataset.file);
			});
		});
	},

	/* ── pagination ──────────────────────────────────────── */
	renderPagination(totalPages) {
		const el = $("#pagination");
		if (totalPages <= 1) { el.innerHTML = ""; return; }

		let html = '<button class="page-btn' + (this.page === 0 ? " disabled" : "") +
			'" data-p="' + (this.page - 1) + '">\u2190</button>';

		for (const p of this.pageRange(this.page, totalPages, 2)) {
			if (p === "...") { html += '<span class="page-ellipsis">\u2026</span>'; }
			else {
				html += '<button class="page-btn' + (p === this.page ? " active" : "") +
					'" data-p="' + p + '">' + (p + 1) + "</button>";
			}
		}

		html += '<button class="page-btn' + (this.page >= totalPages - 1 ? " disabled" : "") +
			'" data-p="' + (this.page + 1) + '">\u2192</button>';

		const s = this.page * this.perPage + 1;
		const e = Math.min(s + this.perPage - 1, this.filtered.length);
		html += '<span class="page-info">' + s + "\u2013" + e + " of " + this.filtered.length + "</span>";

		el.innerHTML = html;
		const self = this;
		el.querySelectorAll(".page-btn:not(.disabled)").forEach(btn => {
			btn.addEventListener("click", () => {
				self.page = parseInt(btn.dataset.p, 10);
				self.update();
				window.scrollTo({ top: 0, behavior: "smooth" });
			});
		});
	},

	pageRange(cur, total, delta) {
		const r = [];
		const l = Math.max(0, cur - delta);
		const ri = Math.min(total - 1, cur + delta);
		if (l > 0) { r.push(0); if (l > 1) r.push("..."); }
		for (let i = l; i <= ri; i++) r.push(i);
		if (ri < total - 1) { if (ri < total - 2) r.push("..."); r.push(total - 1); }
		return r;
	},

	/* ── expand / collapse ─────────────────────────────── */
	async toggle(name, file) {
		if (this.expanded.has(name)) { this.expanded.delete(name); this.renderTable(); return; }
		this.expanded.add(name);
		if (!this.cache[name]) {
			this.loading.add(name);
			this.renderTable();
			try {
				const resp = await this.fetch("skeb/" + encodeURIComponent(file) + ".json");
				if (!resp.ok) throw new Error("HTTP " + resp.status);
				this.cache[name] = await resp.json();
			} catch (e) {
				this.cache[name] = { screen_name: name, _error: e.message };
			}
			this.loading.delete(name);
		}
		this.renderTable();
	},

	/* ── detail panel ──────────────────────────────────── */
	renderDetail(d) {
		if (d._error) {
			return '<tr class="row-detail"><td colspan="6" class="msg">Error: ' + esc(d._error) + "</td></tr>";
		}
		const total = d.total_works || 0;
		const scraped = d.scraped_works || (d.works || []).length;

		return (
			'<tr class="row-detail"><td colspan="6"><div class="detail-inner">' +
			this.renderDetailHead(d) +
			'<div class="detail-grid">' +
			'<div class="detail-section"><h3>Price History</h3>' + this.renderPrices(d) + "</div>" +
			'<div class="detail-section"><h3>Works \u2014 ' + scraped + " shown" +
			(total > scraped ? " of " + total + " total" : "") + "</h3>" +
			this.renderWorks(d) + "</div>" +
			"</div>" +
			"</div></td></tr>"
		);
	},

	renderDetailHead(d) {
		const desc = d.description ? truncate(d.description, 200) : "";

		// Get Links and format them
		var links = [];
		var seen = new Set();
		for (const sl of d.profile.user_service_links) {
			const url = sl.url || "";
			if (url && !seen.has(url)) {
				links.push({
					label: (sl.provider || "link").toUpperCase(),
					url: url,
					name: sl.screen_name || "",
				});
				seen.add(url);
			}
		}
		var standalone = d.profile.url;
		if (standalone && !seen.has(standalone)) {
			links.push({ label: "Website", url: standalone, name: "" })
			seen.add(standalone)
		}
		const PLATFORM_URLS = {
			"pixiv_id": ["Pixiv", "https://www.pixiv.net/users/{}"],
			"nijie_id": ["Nijie", "https://nijie.info/members.php?id={}"],
			"booth_id": ["BOOTH", "https://{}.booth.pm"],
			"fantia_id": ["Fantia", "https://fantia.jp/fanclubs/{}"],
			"fanbox_id": ["Fanbox", "https://{}.fanbox.cc"],
			"youtube_id": ["YouTube", "https://youtube.com/channel/{}"],
			"patreon_id": ["Patreon", "https://patreon.com/{}"],
			"skima_id": ["SKIMA", "https://skima.jp/profile?id={}"],
			"coconala_id": ["Coconala", "https://coconala.com/users/{}"],
			"dlsite_id": ["DLsite", "https://www.dlsite.com/home/circle/profile/=/maker_id/{}"],
			"fanza_id": ["FANZA", "https://www.dmm.co.jp/dc/doujin/-/detail/=/keyword={}"],
		}
		for (const key in PLATFORM_URLS) {
			const pid = d.profile[key]
			if (pid) {
				const label = PLATFORM_URLS[key][0]
				const tmpl = PLATFORM_URLS[key][1]
				const url = tmpl.format(pid)
				if (url && !seen.has(url)) {
					links.push({ label: label, url: url, name: pid })
					seen.add(url)
				}
			}
		}
		
		const flags = d.flags || {};

		// Links
		let linksHtml = "";
		if (links.length) {
			linksHtml = '<div class="detail-links">';
			for (const lk of links) {
				linksHtml += '<a class="detail-link-tag" href="' + esc(lk.url) +
					'" target="_blank" rel="noopener"><span class="detail-link-label">' +
					esc(lk.label) + '</span> ' + esc(lk.name || lk.label) + "</a>";
			}
			linksHtml += "</div>";
		}

		// Flags
		let flagsHtml = "";
		const flagEntries = Object.entries(flags);
		if (flagEntries.length) {
			flagsHtml = '<div class="detail-flags">';
			for (const [k, v] of flagEntries) {
				const cls = v ? "detail-flag detail-flag-true" : "detail-flag detail-flag-false";
				const val = typeof v === "boolean" ? "" : ": " + v;
				flagsHtml += '<span class="' + cls + '">' + esc(k) + esc(String(val)) + "</span>";
			}
			flagsHtml += "</div>";
		}

		// Acceptable status
		let acceptableHtml = "";
		if (d.acceptable) {
			acceptableHtml = '<span class="detail-flag detail-acceptable-true">accepting requests</span>';
		} else {
			acceptableHtml = '<span class="detail-flag detail-acceptable-false">not accepting</span>';
		}

		return (
			'<div class="detail-head">' +
			'<div class="detail-identity">' +
			(d.avatar_url
				? '<img class="detail-avatar" src="' + esc(d.avatar_url) +
				'" onerror="this.style.display=\'none\'">'
				: "") +
			"<div>" +
			'<div class="detail-display-name">' + esc(d.name || d.screen_name) + "</div>" +
			'<a class="detail-sn" href="https://skeb.jp/@' + esc(d.screen_name) +
			'" target="_blank" rel="noopener">@' + esc(d.screen_name) + "</a>" +
			(desc ? '<div class="detail-desc">' + esc(desc) + "</div>" : "") +
			linksHtml +
			flagsHtml +
			'<div class="detail-flags" style="margin-top:4px">' + acceptableHtml + "</div>" +
			"</div>" +
			"</div>" +
			'<div class="detail-right"><div class="detail-meta">' +
			"<span>First seen " + fmtDate(d.first_seen) + "</span>" +
			"<span>Updated " + fmtDate(d.last_updated) + "</span>" +
			"</div></div>" +
			"</div>"
		);
	},

	renderPrices(d) {
		const ph = d.price_history || {};
		const genres = Object.keys(ph);
		if (!genres.length) return '<p class="msg-sm">No price data</p>';
		let html = "";
		for (const genre of genres) {
			const entries = ph[genre] || [];
			if (!entries.length) continue;
			const range = (d.price_range || {})[genre];
			html += '<div class="ph-genre"><div class="ph-genre-head">';
			html += '<span class="genre-tag">' + esc(genre) + "</span>";
			if (range && range.min !== range.max)
				html += '<span class="ph-range">' + fmtRange(range) + "</span>";
			html += '</div><ul class="ph-list">';
			for (let i = entries.length - 1; i >= 0; i--) {
				const e = entries[i];
				let cls = "";
				if (i > 0) {
					const prev = entries[i - 1].amount || 0;
					const curr = e.amount || 0;
					if (curr > prev) cls = " ph-up";
					else if (curr < prev) cls = " ph-down";
				}
				html += '<li><span class="ph-val' + cls + '">' + fmtYen(e.amount) +
					'</span><span class="ph-date">' + fmtDate(e.recorded_at) + "</span></li>";
			}
			html += "</ul></div>";
		}
		return html;
	},

	renderWorks(d) {
		const works = d.profile.received_works || [];
		if (!works.length) return '<p class="msg-sm">No works data</p>';
		const MAX = 48;
		const show = works.slice(0, MAX);
		let html = '<div class="works-grid">';
		for (const w of show) {
			const path = w.path || "";
			const genre = w.genre || "";
			const nsfw = w.nsfw;
			const date = w.created_at || ""; // Never seen before...
			const body = w.body || "";

			// Get src & srcset
			var src = ""
			var srcset = ""
			for (const key of ["thumbnail_image_urls", "private_thumbnail_image_urls"]) {
				const urls = w[key];
				if (!urls) continue;
				if (urls['src']) { src = urls['src']; }
				if (urls['srcset']) { srcset = urls['srcset']; }
				if (src && srcset) { break; }
			}

			html += '<a class="work-card" href="https://skeb.jp' + esc(path) +
				'" target="_blank" rel="noopener"' +
				(body ? ' title="' + esc(truncate(body, 300)) + '"' : "") + ">";
			if (src) {
				html += '<img class="work-thumb-img" loading="lazy" alt="" src="' + esc(src) + '"';
				if (srcset) html += ' srcset="' + esc(srcset) + '"';
				html += ">";
			} else {
				html += '<div class="work-thumb-empty"><span>' + esc(path.split("/").pop() || "?") + "</span></div>";
			}
			html += '<div class="work-info"><span>';
			if (genre) html += '<span class="work-genre">' + esc(genre) + "</span>";
			if (nsfw) html += '<span class="work-nsfw">NSFW</span>';
			html += '</span><span class="work-date">' + fmtDate(date) + "</span></div>";
			if (body) html += '<div class="work-body">' + esc(truncate(body, 100)) + "</div>";
			html += "</a>";
		}
		html += "</div>";
		if (works.length > MAX)
			html += '<p class="msg-sm" style="margin-top:8px">Showing ' + MAX + " of " + works.length + "</p>";
		return html;
	},

	async fetch(url) {
		var data = await fetch(url);
		if (!data.ok) {
			data = await fetch("https://raw.githubusercontent.com/Elfiawesome/skeb-archiver/refs/heads/main/docs/" + url);
		}
		return data;
	}
};

document.addEventListener("DOMContentLoaded", () => App.init());
