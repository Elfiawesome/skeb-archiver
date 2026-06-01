/* ================================================================
   Skeb Tracker — editor.js
   Album editor with thumbnails, bulk edit, shortcuts, dup detection
   ================================================================ */

(function() {
	var state = {
		meta: { name: 'untitled', label: 'Untitled', type: 'reports', timestamp: Date.now() / 1000 },
		entries: [],
		mainData: [],
		mainLoaded: false,
		selectedIdx: -1,
		dragIdx: -1,
		checked: {}
	};

	function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

	function findInMain(sn) {
		for (var i = 0; i < state.mainData.length; i++) {
			if (state.mainData[i].screen_name === sn) return state.mainData[i];
		}
		return null;
	}

	function isInAlbum(sn) { for (var i=0;i<state.entries.length;i++) { if (state.entries[i].screen_name===sn) return true; } return false; }

	function enrichEntry(entry) {
		var full = findInMain(entry.screen_name);
		if (full) {
			if (!entry.avatar_url && full.avatar_url) entry.avatar_url = full.avatar_url;
			if (!entry.current_prices && full.current_prices) entry.current_prices = full.current_prices;
			if ((!entry.latest_thumbnails || !entry.latest_thumbnails.length) && full.latest_thumbnails && full.latest_thumbnails.length) entry.latest_thumbnails = full.latest_thumbnails.slice();
			if (entry.total_works == null && full.total_works != null) entry.total_works = full.total_works;
			if (entry.file == null && full.file) entry.file = full.file;
			if (entry.acceptable == null && full.acceptable != null) entry.acceptable = full.acceptable;
		}
	}

	function countBreakdown() {
		var notes=0,tags=0;
		for (var i=0;i<state.entries.length;i++) {
			if (state.entries[i].notes) notes++;
			if (state.entries[i].tags && state.entries[i].tags.length) tags++;
		}
		return {notes:notes,tags:tags};
	}

	// --- binary ---
	function parseHeader(buf) { var v=new DataView(buf),ms=v.getUint32(0,false); var mb=new Uint8Array(buf.slice(4,4+ms)); var m=JSON.parse(new TextDecoder('utf-8').decode(mb)); var ds=new DataView(buf.slice(4+ms,8+ms)).getUint32(0,false); return {meta:m,headerSize:8+ms,dataSize:ds}; }
	async function decompress(c) { var s=new Response(c).body.pipeThrough(new DecompressionStream('gzip')); var b=await new Response(s).arrayBuffer(); return JSON.parse(new TextDecoder('utf-8').decode(b)); }
	async function buildAlbum(meta,entries) { meta.timestamp=Date.now()/1000; var mb=new TextEncoder().encode(JSON.stringify(meta)); var dj=JSON.stringify(entries); var cs=new Response(dj).body.pipeThrough(new CompressionStream('gzip')); var cb=await new Response(cs).arrayBuffer(); var total=4+mb.length+4+cb.byteLength; var r=new Uint8Array(total),dv=new DataView(r.buffer),off=0; dv.setUint32(off,mb.length,false);off+=4; r.set(mb,off);off+=mb.length; dv.setUint32(off,cb.byteLength,false);off+=4; r.set(new Uint8Array(cb),off); return r; }
	function downloadBlob(data,fn) { var blob=new Blob([data],{type:'application/octet-stream'}); var url=URL.createObjectURL(blob); var a=document.createElement('a'); a.href=url;a.download=fn; document.body.appendChild(a);a.click();document.body.removeChild(a); URL.revokeObjectURL(url); }

	// --- main data ---
	async function loadMainData() {
		var btn=document.getElementById('btnLoadData'); btn.textContent='Loading...';btn.disabled=true;
		try { var album=await App._getAlbum('albums/main_index'); state.mainData=album.data||[]; state.mainLoaded=true; btn.textContent='Data Loaded';btn.classList.add('loaded'); document.getElementById('editorSearch').placeholder='Search '+state.mainData.length+' artists...'; for(var i=0;i<state.entries.length;i++) enrichEntry(state.entries[i]); renderAll(); }
		catch(e) { console.error(e); btn.textContent='Load Failed';btn.disabled=false; }
	}

	// --- search ---
	var searchTimer=null;
	function doSearch(q) { clearTimeout(searchTimer); searchTimer=setTimeout(function(){renderSearch(q);},200); }
	function renderSearch(query) {
		var c=document.getElementById('searchResults');
		if(!state.mainLoaded){c.innerHTML='<div class="empty-message">Click "Load Data" to enable search.</div>';return;}
		if(!query){c.innerHTML='<div class="empty-message">Search '+state.mainData.length+' artists.</div>';return;}
		var q=query.toLowerCase(),results=[];
		for(var i=0;i<state.mainData.length&&results.length<20;i++){var u=state.mainData[i]; if(u.screen_name&&u.screen_name.toLowerCase().includes(q)) results.push(u);}
		if(!results.length){c.innerHTML='<div class="empty-message">No matches.</div>';return;}
		c.innerHTML=results.map(function(u){var added=isInAlbum(u.screen_name); var av=u.avatar_url||''; var pr=u.current_prices||{}; var chips=Object.entries(pr).map(function(p){return p[0]+': \u00A5'+p[1].toLocaleString();}).join(', ');
			return'<div class="rc-card'+(added?' added':'')+'" data-sn="'+u.screen_name+'">'+(av?'<img src="'+av+'" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">':'<div style="width:32px;height:32px;background:var(--surface3);flex-shrink:0"></div>')+'<div class="rc-info"><div class="rc-name">@'+u.screen_name+'</div><div class="rc-meta">'+(chips||'No prices')+' | '+(u.total_works||0)+' works</div></div>'+(added?'<span style="color:var(--text-secondary);font-size:0.7rem">Added</span>':'<span class="rc-add">+ Add</span>')+'</div>';
		}).join('');
		c.querySelectorAll('.rc-card').forEach(function(card){card.addEventListener('click',function(){var sn=card.dataset.sn; if(isInAlbum(sn))return; addEntry(sn);});});
	}

	function addEntry(sn) {
		if(isInAlbum(sn)){flashDuplicate(sn);return;}
		var entry={screen_name:sn,notes:'',tags:[],latest_thumbnails:[]};
		var full=findInMain(sn);
		if(full){ entry.avatar_url=full.avatar_url||''; entry.current_prices=full.current_prices||{}; entry.latest_thumbnails=(full.latest_thumbnails||[]).slice(); entry.total_works=full.total_works||0; entry.file=full.file||''; entry.acceptable=full.acceptable; }
		state.entries.push(entry); state.selectedIdx=state.entries.length-1; renderAll();
	}

	function flashDuplicate(sn) {
		var c=document.getElementById('searchResults');
		var card=c.querySelector('[data-sn="'+sn+'"]'); if(!card)return;
		card.style.background='var(--red)'; setTimeout(function(){card.style.background='';},600);
	}

	function removeEntry(idx) {
		delete state.checked[idx];
		state.entries.splice(idx,1);
		var newChecked={};
		Object.keys(state.checked).forEach(function(k){var n=parseInt(k); if(n>idx) newChecked[n-1]=true; else if(n<idx) newChecked[n]=true;});
		state.checked=newChecked;
		if(state.selectedIdx>=state.entries.length) state.selectedIdx=state.entries.length-1;
		renderAll();
	}

	// --- entries ---
	function renderEntries() {
		var c=document.getElementById('albumEntries');
		var bd=countBreakdown();

		var titleEl=document.getElementById('entryCount');
		if(!titleEl)return;
		var title=titleEl.parentNode;
		// replace all entry-count children in the title
		title.querySelectorAll('.entry-count').forEach(function(el){el.remove();});
		var countHtml='<span class="entry-count" id="entryCount">'+state.entries.length+'</span>';
		if(bd.notes) countHtml+='<span class="entry-count entry-count-notes">'+bd.notes+' notes</span>';
		if(bd.tags) countHtml+='<span class="entry-count entry-count-tags">'+bd.tags+' tags</span>';
		title.insertAdjacentHTML('beforeend',countHtml);

		if(!state.entries.length){c.innerHTML='<div class="empty-message">No entries. Search and "+ Add", or drop a .album file.</div>';return;}

		var anyChecked=Object.keys(state.checked).length>0;
		c.innerHTML=state.entries.map(function(e,i){
			var av=e.avatar_url||'',sel=(i===state.selectedIdx)?' selected':'',checked=state.checked[i]?' checked':'';
			var prices=e.current_prices||{};
			var priceChips=Object.entries(prices).map(function(p){return'<span>'+p[0]+': \u00A5'+p[1].toLocaleString()+'</span>';}).join('');
			var tags=e.tags||[];
			var tagChips=tags.length?'<div class="ae-tags">'+tags.map(function(t){return'<span>'+t+'</span>';}).join('')+'</div>':'';
			var thumbs=e.latest_thumbnails||[];
			var thumbHtml=thumbs.length?'<div class="ae-thumbs">'+thumbs.slice(0,3).map(function(s){return'<img src="'+s+'" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">';}).join('')+'</div>':'';
			var notesDot=e.notes?'<span class="ae-notes-indicator" title="'+esc(e.notes.substring(0,80))+'">\u25CF</span>':'';
			return'<div class="ae-card'+sel+checked+'" data-idx="'+i+'" draggable="true">'
				+'<input type="checkbox" class="ae-check" data-idx="'+i+'" '+(state.checked[i]?'checked':'')+' title="Select for bulk actions">'
				+'<span class="drag-handle">\u2630</span>'
				+(av?'<img class="ae-avatar" src="'+av+'" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">':'<div style="width:36px;height:36px;background:var(--surface3);flex-shrink:0;border:1px solid var(--border)"></div>')
				+'<div class="ae-body">'
					+'<div class="ae-name-row"><span class="ae-name">@'+e.screen_name+'</span>'+notesDot+'</div>'
					+(priceChips?'<div class="ae-prices">'+priceChips+'</div>':'')+tagChips
				+'</div>'
				+thumbHtml
				+'<button class="ae-remove" data-idx="'+i+'" title="Remove">\u2715</button>'
			+'</div>';
		}).join('');

		if(anyChecked){
			c.insertAdjacentHTML('afterbegin','<div class="ae-bulk-bar"><span>'+Object.keys(state.checked).length+' selected</span> <button id="bulkTag">Tag</button> <button id="bulkNote">Note</button> <button id="bulkRemove">Remove</button> <button id="bulkClear">Clear</button></div>');
			document.getElementById('bulkTag').addEventListener('click',function(){bulkEdit('tag');});
			document.getElementById('bulkNote').addEventListener('click',function(){bulkEdit('note');});
			document.getElementById('bulkRemove').addEventListener('click',function(){
				var idxs=Object.keys(state.checked).map(Number).sort(function(a,b){return b-a;});
				idxs.forEach(function(idx){state.entries.splice(idx,1);});
				state.checked={}; state.selectedIdx=-1; renderAll();
			});
			document.getElementById('bulkClear').addEventListener('click',function(){state.checked={};renderEntries();});
		}

		c.querySelectorAll('.ae-card').forEach(function(el){
			el.addEventListener('click',function(e){
				if(e.target.closest('.ae-remove,.ae-check'))return;
				state.selectedIdx=parseInt(el.dataset.idx); renderAll();
			});
		});
		c.querySelectorAll('.ae-check').forEach(function(cb){
			cb.addEventListener('click',function(e){e.stopPropagation(); var i=parseInt(cb.dataset.idx); if(state.checked[i]) delete state.checked[i]; else state.checked[i]=true; renderEntries();});
		});
		c.querySelectorAll('.ae-remove').forEach(function(btn){
			btn.addEventListener('click',function(e){e.stopPropagation(); removeEntry(parseInt(btn.dataset.idx));});
		});
		// drag
		c.querySelectorAll('.ae-card').forEach(function(row){
			row.addEventListener('dragstart',function(e){state.dragIdx=parseInt(row.dataset.idx);row.classList.add('entry-dragging');e.dataTransfer.effectAllowed='move';});
			row.addEventListener('dragend',function(){row.classList.remove('entry-dragging');});
			row.addEventListener('dragover',function(e){e.preventDefault();e.dataTransfer.dropEffect='move';});
			row.addEventListener('drop',function(e){e.preventDefault();var from=state.dragIdx,to=parseInt(row.dataset.idx); if(from>=0&&from!==to){var item=state.entries.splice(from,1)[0];state.entries.splice(to,0,item); if(state.selectedIdx===from)state.selectedIdx=to;else if(state.selectedIdx>=to&&state.selectedIdx<from)state.selectedIdx++;else if(state.selectedIdx<=to&&state.selectedIdx>from)state.selectedIdx--; var nc={};Object.keys(state.checked).forEach(function(k){var n=parseInt(k);if(n===from) nc[to]=true;else if(n>=to&&n<from) nc[n+1]=true;else if(n<=to&&n>from) nc[n-1]=true;else nc[n]=true;});state.checked=nc;renderAll();}state.dragIdx=-1;});
		});
	}

	function bulkEdit(mode){
		var val=prompt(mode==='tag'?'Enter tag:':'Enter note:');
		if(!val&&val!=='')return;
		Object.keys(state.checked).forEach(function(k){var i=parseInt(k); if(mode==='tag'){var t=state.entries[i].tags||[]; if(t.indexOf(val)===-1)t.push(val); state.entries[i].tags=t;}else{state.entries[i].notes=val;} });
		state.checked={}; renderAll();
	}

	// --- detail ---
	function renderDetail() {
		var c=document.getElementById('detailPanel');
		if(state.selectedIdx<0||state.selectedIdx>=state.entries.length){c.className='detail-panel';c.innerHTML='';return;}
		var e=state.entries[state.selectedIdx];
		var av=e.avatar_url||'',prices=e.current_prices||{};
		var priceChips=Object.entries(prices).map(function(p){return'<span>'+p[0]+': \u00A5'+p[1].toLocaleString()+'</span>';}).join('');
		var thumbs=e.latest_thumbnails||[];
		var tags=(e.tags||[]).join(', ');
		var full=findInMain(e.screen_name);

		c.className='detail-panel open';
		c.innerHTML='<div class="dp-header">'+(av?'<img src="'+av+'" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');">':'')+'<div><div class="dp-name">@'+e.screen_name+'</div><a class="dp-link" href="https://skeb.jp/@'+e.screen_name+'" target="_blank">Open on Skeb \u2197</a></div></div>'
			+(priceChips?'<div class="dp-prices">'+priceChips+'</div>':'')
			+'<div class="dp-row"><label>Notes</label><textarea data-field="notes" rows="2">'+esc(e.notes||'')+'</textarea></div>'
			+'<div class="dp-row"><label>Tags</label><input type="text" data-field="tags" value="'+esc(tags)+'" placeholder="comma-separated"></div>'
			+'<div class="dp-row"><label>Thumbs</label><div style="flex:1">'
				+'<div class="dp-thumbs">'+(thumbs.length?thumbs.map(function(s,ti){return'<div class="dp-thumb-wrap"><img src="'+s+'" loading="lazy" onerror="this.classList.add(\'img-broken\');this.removeAttribute(\'src\');"><button class="dp-thumb-remove" data-ti="'+ti+'">\u2715</button></div>';}).join(''):'<span style="color:var(--text-secondary);font-size:0.75rem">No thumbnails</span>')+'</div>'
				+'<div style="display:flex;gap:0.3rem;margin-top:0.4rem;">'
					+'<input type="text" id="thumbUrlInput" placeholder="Paste image URL..." style="flex:1;font-size:0.75rem;padding:0.25rem 0.4rem;background:var(--surface3);border:1px solid var(--border);color:var(--text);outline:none;">'
					+'<button id="btnAddThumb" style="font-size:0.7rem;padding:0.25rem 0.5rem;background:var(--surface3);color:var(--text);border:1px solid var(--border);cursor:pointer;white-space:nowrap;">Add</button>'
					+(full&&full.latest_thumbnails&&full.latest_thumbnails.length?'<button id="btnImportThumbs" style="font-size:0.7rem;padding:0.25rem 0.5rem;background:var(--accent);color:#fff;border:1px solid var(--accent);cursor:pointer;white-space:nowrap;">Import from Main</button>':'')
				+'</div>'
			+'</div></div>';

		c.querySelectorAll('[data-field]').forEach(function(el){el.addEventListener('change',function(){if(el.dataset.field==='notes')state.entries[state.selectedIdx].notes=el.value;if(el.dataset.field==='tags')state.entries[state.selectedIdx].tags=el.value.split(',').map(function(t){return t.trim();}).filter(Boolean);renderEntries();});});

		c.querySelectorAll('.dp-thumb-remove').forEach(function(btn){btn.addEventListener('click',function(){var ti=parseInt(btn.dataset.ti);state.entries[state.selectedIdx].latest_thumbnails.splice(ti,1);renderDetail();renderEntries();});});

		var addBtn=document.getElementById('btnAddThumb');
		if(addBtn) addBtn.addEventListener('click',function(){
			var u=document.getElementById('thumbUrlInput').value.trim();
			var input=document.getElementById('thumbUrlInput');
			if(!u)return;
			addBtn.textContent='Checking...';addBtn.disabled=true;
			var img=new Image();
			img.onload=function(){
				state.entries[state.selectedIdx].latest_thumbnails.push(u);
				input.value='';input.style.borderColor='';
				addBtn.textContent='Add';addBtn.disabled=false;
				renderDetail();renderEntries();
			};
			img.onerror=function(){
				input.style.borderColor='var(--red)';
				addBtn.textContent='Invalid';addBtn.disabled=false;
				setTimeout(function(){input.style.borderColor='';addBtn.textContent='Add';},1500);
			};
			img.src=u;
		});

		var impBtn=document.getElementById('btnImportThumbs');
		if(impBtn) impBtn.addEventListener('click',function(){var full=findInMain(state.entries[state.selectedIdx].screen_name);if(full&&full.latest_thumbnails){state.entries[state.selectedIdx].latest_thumbnails=full.latest_thumbnails.slice();renderDetail();renderEntries();}});
	}

	function renderAll(){renderEntries();renderDetail(); var sq=document.getElementById('editorSearch'); if(sq)renderSearch(sq.value.trim());}

	// --- upload ---
	var uploadZone=document.getElementById('uploadZone'),fileInput=document.getElementById('fileInput');
	uploadZone.addEventListener('click',function(){fileInput.click();});
	fileInput.addEventListener('change',function(e){handleFile(e.target.files[0]);});
	uploadZone.addEventListener('dragover',function(e){e.preventDefault();uploadZone.classList.add('dragover');});
	uploadZone.addEventListener('dragleave',function(){uploadZone.classList.remove('dragover');});
	uploadZone.addEventListener('drop',function(e){e.preventDefault();uploadZone.classList.remove('dragover'); if(e.dataTransfer.files[0])handleFile(e.dataTransfer.files[0]);});

	async function handleFile(file){
		if(!file)return; uploadZone.textContent='Loading '+file.name+'...';
		try{var buf=await file.arrayBuffer(),h=parseHeader(buf); state.meta=h.meta; var entries=await decompress(buf.slice(h.headerSize)); state.entries=Array.isArray(entries)?entries:[]; for(var i=0;i<state.entries.length;i++){state.entries[i].notes=state.entries[i].notes||'';state.entries[i].tags=state.entries[i].tags||[];state.entries[i].latest_thumbnails=state.entries[i].latest_thumbnails||[];}
			if(!state.mainLoaded){try{var album=await App._getAlbum('albums/main_index');state.mainData=album.data||[];state.mainLoaded=true;var btn=document.getElementById('btnLoadData');btn.textContent='Data Loaded';btn.classList.add('loaded');document.getElementById('editorSearch').placeholder='Search '+state.mainData.length+' artists...';}catch(e){console.warn('Could not auto-load main data:',e);}}
			for(var k=0;k<state.entries.length;k++) enrichEntry(state.entries[k]);
			state.selectedIdx=-1;state.checked={}; uploadZone.innerHTML='<p><strong>'+file.name+'</strong> loaded ('+state.entries.length+' entries)</p>';uploadZone.classList.add('has-file'); document.getElementById('metaLabel').value=state.meta.label||'Untitled';document.getElementById('metaType').value=state.meta.type||'reports';renderAll();}
		catch(e){uploadZone.classList.remove('has-file');uploadZone.innerHTML='<p style="color:var(--red)">Failed: '+e.message+'</p><p>Drop .album file here</p>';}
	}

	// --- events ---
	document.getElementById('btnLoadData').addEventListener('click',function(){if(!state.mainLoaded)loadMainData();});
	document.getElementById('editorSearch').addEventListener('input',function(){doSearch(this.value.trim());});
	document.getElementById('btnDownload').addEventListener('click',async function(){
		state.meta.label=document.getElementById('metaLabel').value||'Untitled'; state.meta.name=state.meta.label.toLowerCase().replace(/\s+/g,'_'); state.meta.type=document.getElementById('metaType').value;
		var clean=state.entries.map(function(e){var out={screen_name:e.screen_name}; if(e.notes)out.notes=e.notes; if(e.tags&&e.tags.length)out.tags=e.tags; if(e.latest_thumbnails&&e.latest_thumbnails.length)out.latest_thumbnails=e.latest_thumbnails; return out;});
		var data=await buildAlbum(state.meta,clean); downloadBlob(data,(state.meta.name||'album')+'.album');
	});
	document.getElementById('metaLabel').addEventListener('input',function(){state.meta.label=this.value;});
	document.getElementById('metaType').addEventListener('change',function(){state.meta.type=this.value;});

	// --- keyboard ---
	document.addEventListener('keydown',function(e){
		if(e.target.closest('input,textarea,select,[contenteditable]'))return;
		if(e.key==='Delete'||e.key==='Backspace'){if(state.selectedIdx>=0){removeEntry(state.selectedIdx);e.preventDefault();}}
		if(e.key==='Escape'){state.selectedIdx=-1;state.checked={};renderAll();}
		if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();document.getElementById('btnDownload').click();}
	});

	renderAll();
})();
