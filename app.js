/* ================================================================
   Skeb Tracker — app.js (glue)
   State + init + event binding
   ================================================================ */

var App = {
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

	_customKeyIndex: [],
	_screenNameIndex: [],
	_acResults: [],
	_acSelected: -1,

	async init() {
		try {
			this.timeNow = new Date();
			this._readURLParams();

			await this._loadAlbumIndex();

			this._showProgress();
			var mainAlbum = await this._getAlbum('albums/main_index');
			this._hideProgress();
			this.mainData = mainAlbum.data || [];

			var extUrl = (this.currentAlbum && this.currentAlbum._externalUrl) || null;
			if (extUrl) {
				await this._tryLoadExternal(extUrl);
			} else if (this.currentAlbum && this.currentAlbum._fromFile) {
				this.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
				this.albumEntries = [];
			} else if (this.currentAlbum && (this.currentAlbum.name || '').replace(/\/$/, '') !== 'albums/main_index') {
				await this._tryLoadAlbum(this.currentAlbum.name);
			} else {
				this.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
			}

			this._mergeWithMain();
			this._collectAlbumTags();
			this._buildCustomKeyIndex();
			this._buildScreenNameIndex();

			document.querySelector('#statsBadge span').textContent =
				(this.allUsers.length ? this.allUsers.length.toLocaleString() : '?') + ' users' +
				(mainAlbum.timestamp ? ' · ' + this._fmtDate(mainAlbum.timestamp) : '');

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

	_bindEvents() {
		var self = this;

		document.getElementById('searchInput').addEventListener('input', this._debounce(function() {
			var input = document.getElementById('searchInput');
			self.searchTerm = input.value.trim();
			self.currentPage = 1;
			self._applyFilters();

			var el = input;
			var cursorPos = el.selectionStart || 0;
			var val = el.value;
			var before = val.substring(0, cursorPos);
			var lastSpace = before.lastIndexOf(' ');
			var tokenStart = lastSpace >= 0 ? lastSpace + 1 : 0;
			var token = val.substring(tokenStart, cursorPos);

			if (token.length >= 1 && !token.includes(':') && !token.match(/[=<>!]/)) {
				// resolve dot-path for nested keys
				var dotIdx = token.lastIndexOf('.');
				var partial = dotIdx >= 0 ? token.substring(dotIdx + 1) : token;
				var prefixCheck = dotIdx >= 0 ? token.substring(0, dotIdx + 1) : '';
				if (prefixCheck) {
					var keys = self._customKeyIndex || [];
					var hasNested = keys.some(function(k) { return k.startsWith(prefixCheck) && k !== prefixCheck.slice(0, -1); });
					if (!hasNested) { self._hideAutocomplete(); return; }
				}
				self._showAutocomplete(partial);
			} else {
				self._hideAutocomplete();
			}
		}, 250));

		document.getElementById('searchInput').addEventListener('keydown', function(e) {
			self._handleAutocompleteKey(e);
		});

		document.getElementById('searchInput').addEventListener('blur', function() {
			setTimeout(function() { self._hideAutocomplete(); }, 150);
		});

		document.getElementById('searchHelpBtn').addEventListener('click', function(e) {
			e.stopPropagation();
			document.getElementById('searchHelpTooltip').classList.toggle('visible');
		});
		document.addEventListener('click', function(e) {
			if (!e.target.closest('.search-wrapper')) {
				document.getElementById('searchHelpTooltip').classList.remove('visible');
			}
		});

		document.getElementById('filterAcceptable').addEventListener('click', function() {
			self.filterAcceptable = self.filterAcceptable === null ? true : (self.filterAcceptable ? false : null);
			self.currentPage = 1; self._applyFilters();
		});
		document.getElementById('filterNsfw').addEventListener('click', function() {
			self.filterNsfw = self.filterNsfw === null ? true : (self.filterNsfw ? false : null);
			self.currentPage = 1; self._applyFilters();
		});
		document.getElementById('genreFilter').addEventListener('change', function(e) {
			self.filterGenre = e.target.value;
			self.currentPage = 1; self._applyFilters();
		});

		var priceDebounced = self._debounce(function() {
			self.filterPriceMin = document.getElementById('priceMin').value ? +document.getElementById('priceMin').value : null;
			self.filterPriceMax = document.getElementById('priceMax').value ? +document.getElementById('priceMax').value : null;
			self.currentPage = 1; self._applyFilters();
		}, 500);
		document.getElementById('priceMin').addEventListener('input', priceDebounced);
		document.getElementById('priceMax').addEventListener('input', priceDebounced);

		var worksDebounced = self._debounce(function() {
			self.filterWorksMin = document.getElementById('worksMin').value ? +document.getElementById('worksMin').value : null;
			self.filterWorksMax = document.getElementById('worksMax').value ? +document.getElementById('worksMax').value : null;
			self.currentPage = 1; self._applyFilters();
		}, 500);
		document.getElementById('worksMin').addEventListener('input', worksDebounced);
		document.getElementById('worksMax').addEventListener('input', worksDebounced);

		document.getElementById('seenOlderDays').addEventListener('input', self._debounce(function() {
			self.filterSeenOlderDays = document.getElementById('seenOlderDays').value ? +document.getElementById('seenOlderDays').value : null;
			self.currentPage = 1; self._applyFilters();
		}, 500));
		document.getElementById('updatedWithinDays').addEventListener('input', self._debounce(function() {
			self.filterUpdatedWithinDays = document.getElementById('updatedWithinDays').value ? +document.getElementById('updatedWithinDays').value : null;
			self.currentPage = 1; self._applyFilters();
		}, 500));

		document.getElementById('resetFilters').addEventListener('click', function() {
			self.searchTerm = '';
			self.filterAcceptable = null;
			self.filterNsfw = null;
			self.filterGenre = '';
			self.filterPriceMin = self.filterPriceMax = null;
			self.filterWorksMin = self.filterWorksMax = null;
			self.filterSeenOlderDays = null;
			self.filterUpdatedWithinDays = null;
			self.sortChain = [];
			self.filterAlbumTags = [];
			self.currentPage = 1;
			document.getElementById('searchInput').value = '';
			self._updateFilterButtonsUI();
			self._renderSortStates();
			self._applyFilters();
		});

		document.querySelectorAll('.sort-chip').forEach(function(chip) {
			chip.addEventListener('click', function() { self._toggleSortKey(chip.dataset.key); });
		});

		document.addEventListener('click', function(e) {
			if (!e.target.closest('.user-card')) self._closeAllDetails();
		});

		document.getElementById('albumSelectBtn').addEventListener('click', function() { self._openAlbumModal(); });
		document.getElementById('albumModalBg').addEventListener('click', function() { self._closeAlbumModal(); });
		document.getElementById('albumModalClose').addEventListener('click', function() { self._closeAlbumModal(); });
		document.getElementById('albumModalSearch').addEventListener('input', self._debounce(function() {
			self._renderAlbumModalList(document.getElementById('albumModalSearch').value);
		}, 200));
		document.getElementById('albumModalExternal').addEventListener('click', function() { self._handleExternalAlbumPrompt(); });
		document.getElementById('albumModalFile').addEventListener('click', function() { self._handleFileAlbumPrompt(); });

		document.querySelectorAll('#albumModalTypeFilters .album-type-chip').forEach(function(chip) {
			chip.addEventListener('click', function() {
				self.albumModalTypeFilter = chip.dataset.type;
				self._renderAlbumModalTypeChips();
				self._renderAlbumModalList(document.getElementById('albumModalSearch').value);
			});
		});

		document.addEventListener('keydown', function(e) {
			if (e.key === 'Escape') self._closeAlbumModal();
		});

		window.addEventListener('popstate', function() {
			self._readURLParams();
			if (!self.loadingComplete) return;
			if (self.currentAlbum && self.currentAlbum._fromFile) {
				self._switchAlbum('albums/main_index');
			} else if (self.currentAlbum && self.currentAlbum._externalUrl) {
				self._loadExternalAlbum(self.currentAlbum._externalUrl);
			} else if (self.currentAlbum && (self.currentAlbum.name || '').replace(/\/$/, '') !== 'albums/main_index') {
				self._switchAlbum(self.currentAlbum.name);
			} else {
				self._switchAlbum('albums/main_index');
			}
		});
	}
};

document.addEventListener('DOMContentLoaded', function() { App.init(); });
