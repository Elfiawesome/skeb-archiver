"use strict";

/* ── helpers ─────────────────────────────────────────────── */
function esc(s) {
	if (!s) return "";
	return s.replace(/&/g,"&amp;").replace(/</g,"&lt;")
			.replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function fmtDate(iso) { return iso ? iso.substring(0, 10) : "\u2014"; }
function fmtYen(n)     { return n != null ? "\u00a5" + n.toLocaleString() : "\u2014"; }

/* ── app state ───────────────────────────────────────────── */
const App = {
	users:    [],
	sorted:   [],
	sortKey:  "last_updated",
	sortAsc:  false,
	search:   "",
	genre:    "art",
	expanded: new Set(),

	/* ── bootstrap ───────────────────────────────────────── */
	async init() {
		try {
			const r = await fetch("data.json");
			if (!r.ok) throw new Error("HTTP " + r.status);
			const data = await r.json();
			this.users = data.users || [];
			this.renderMeta(data);
			this.bind();
			this.update();
		} catch (e) {
			document.getElementById("tbody").innerHTML =
				'<tr><td colspan="5" class="empty">Failed to load data: '
				+ esc(e.message) + "</td></tr>";
		}
	},

	renderMeta(data) {
		document.getElementById("meta").textContent =
			this.users.length + " users \u00b7 " + fmtDate(data.generated_at);

		const total = this.users.reduce((s, u) => s + (u.works_count || 0), 0);
		document.getElementById("stats-bar").innerHTML =
			"<span>Users: <strong>" + this.users.length + "</strong></span>" +
			"<span>Total works: <strong>" + total + "</strong></span>" +
			"<span>Generated: <strong>" + fmtDate(data.generated_at) + "</strong></span>";
	},

	/* ── events ──────────────────────────────────────────── */
	bind() {
		document.getElementById("search").addEventListener("input", (e) => {
			this.search = e.target.value.toLowerCase();
			this.update();
		});
		document.getElementById("genre-filter").addEventListener("change", (e) => {
			this.genre = e.target.value;
			this.update();
		});
		document.querySelectorAll("th[data-sort]").forEach((th) => {
			th.addEventListener("click", () => {
				const k = th.dataset.sort;
				if (this.sortKey === k) this.sortAsc = !this.sortAsc;
				else { this.sortKey = k; this.sortAsc = k === "screen_name"; }
				this.update();
			});
		});
	},

	/* ── price access ────────────────────────────────────── */
	price(u, genre) {
		const ph = u.price_history || {};
		if (genre !== "all") {
			const e = ph[genre];
			return (e && e.length) ? e[e.length - 1].amount : null;
		}
		for (const g of ["art","voice","novel","comic"]) {
			const e = ph[g];
			if (e && e.length) return e[e.length - 1].amount;
		}
		return null;
	},

	/* ── filter + sort ───────────────────────────────────── */
	filter() {
		let list = this.users;

		if (this.search)
			list = list.filter((u) =>
				u.screen_name.toLowerCase().includes(this.search));

		if (this.genre !== "all")
			list = list.filter((u) => {
				const e = (u.price_history || {})[this.genre];
				return e && e.length;
			});

		const key = this.sortKey;
		const dir = this.sortAsc ? 1 : -1;
		const self = this;

		list = list.slice().sort(function (a, b) {
			var va, vb;
			switch (key) {
				case "screen_name":
					va = a.screen_name.toLowerCase();
					vb = b.screen_name.toLowerCase();
					return va < vb ? -dir : va > vb ? dir : 0;
				case "price":
					va = self.price(a, self.genre) || 0;
					vb = self.price(b, self.genre) || 0;
					return (va - vb) * dir;
				case "works_count":
					return ((a.works_count||0) - (b.works_count||0)) * dir;
				case "first_seen":
					va = a.first_seen || "";
					vb = b.first_seen || "";
					return va < vb ? -dir : va > vb ? dir : 0;
				case "last_updated":
					va = a.last_updated || "";
					vb = b.last_updated || "";
					return va < vb ? -dir : va > vb ? dir : 0;
				default: return 0;
			}
		});

		this.sorted = list;
	},

	/* ── render ──────────────────────────────────────────── */
	update() {
		this.filter();
		this.arrows();
		this.renderTable();
	},

	arrows() {
		document.querySelectorAll("th[data-sort]").forEach((th) => {
			var el = th.querySelector(".arrow");
			if (!el) { el = document.createElement("span"); el.className="arrow"; th.appendChild(el); }
			el.textContent = th.dataset.sort === this.sortKey
				? (this.sortAsc ? "\u25b2" : "\u25bc") : "";
		});
	},

	renderTable() {
		var tbody = document.getElementById("tbody");
		if (!this.sorted.length) {
			tbody.innerHTML = '<tr><td colspan="5" class="empty">No users match the current filter</td></tr>';
			return;
		}

		var html = [];
		for (var i = 0; i < this.sorted.length; i++) {
			var u = this.sorted[i];
			var p = this.price(u, this.genre);
			var open = this.expanded.has(u.screen_name);

			html.push(
				'<tr class="row-user' + (open ? " active" : "") +
				'" data-name="' + esc(u.screen_name) + '">' +
				'<td><a class="user-link" href="https://skeb.jp/@' +
					esc(u.screen_name) + '" target="_blank" rel="noopener">@' +
					esc(u.screen_name) + "</a></td>" +
				'<td class="cell-price">' + fmtYen(p) + "</td>" +
				'<td class="cell-count">' + (u.works_count || 0) + "</td>" +
				'<td class="cell-date">' + fmtDate(u.first_seen) + "</td>" +
				'<td class="cell-date">' + fmtDate(u.last_updated) + "</td>" +
				"</tr>"
			);

			if (open) html.push(this.detailRow(u));
		}

		tbody.innerHTML = html.join("");

		/* click binding */
		var self = this;
		tbody.querySelectorAll(".row-user").forEach(function (tr) {
			tr.addEventListener("click", function (ev) {
				if (ev.target.tagName === "A") return;
				var n = tr.dataset.name;
				if (self.expanded.has(n)) self.expanded.delete(n);
				else self.expanded.add(n);
				self.renderTable();
			});
		});
	},

	detailRow(u) {
		var ph = u.price_history || {};
		var genres = Object.keys(ph);

		/* price history */
		var priceHtml = "";
		if (genres.length) {
			for (var gi = 0; gi < genres.length; gi++) {
				var g = genres[gi];
				var entries = ph[g] || [];
				priceHtml += '<span class="genre-label">' + esc(g) + "</span>";
				priceHtml += '<ul class="ph-list">';
				for (var ei = entries.length - 1; ei >= 0; ei--) {
					var e = entries[ei];
					var cls = "";
					if (ei > 0) {
						var prev = entries[ei - 1].amount || 0;
						if ((e.amount || 0) > prev) cls = " ph-up";
						else if ((e.amount || 0) < prev) cls = " ph-down";
					}
					priceHtml +=
						'<li><span class="ph-val' + cls + '">' +
						fmtYen(e.amount) + '</span><span class="ph-date">' +
						fmtDate(e.recorded_at) + "</span></li>";
				}
				priceHtml += "</ul>";
			}
		} else {
			priceHtml = '<p class="empty">No price data</p>';
		}

		/* works */
		var works = u.works || [];
		var wkHtml = "";
		if (works.length) {
			var show = works.slice(0, 60);
			wkHtml = '<ul class="wk-list">';
			for (var wi = 0; wi < show.length; wi++) {
				var w = show[wi];
				wkHtml +=
					"<li>" +
					'<a href="https://skeb.jp' + esc(w.path) +
					'" target="_blank" rel="noopener">' + esc(w.path) + "</a>" +
					'<span class="wk-date">' + fmtDate(w.scraped_at) + "</span></li>";
			}
			if (works.length > 60)
				wkHtml += '<li class="empty">\u2026 and ' + (works.length - 60) + " more</li>";
			wkHtml += "</ul>";
		} else {
			wkHtml = '<p class="empty">No works recorded</p>';
		}

		return (
			'<tr class="row-detail open"><td colspan="5"><div class="detail-grid">' +
			'<div class="detail-section"><h3>Price History</h3>' + priceHtml + "</div>" +
			'<div class="detail-section"><h3>Works (' + works.length + ")</h3>" + wkHtml + "</div>" +
			"</div></td></tr>"
		);
	}
};

document.addEventListener("DOMContentLoaded", function () { App.init(); });