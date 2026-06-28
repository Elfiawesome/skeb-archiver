/* ================================================================
   Skeb Tracker — utils.js
   General-purpose helpers with no dependencies on App state
   ================================================================ */

App._resolvePath = function(obj, path) {
	var parts = path.split('.');
	var cur = obj;
	for (var i = 0; i < parts.length; i++) {
		if (cur == null || typeof cur !== 'object') return undefined;
		cur = cur[parts[i]];
	}
	return cur;
};

App._coerceValue = function(v) {
	if (v === 'true') return true;
	if (v === 'false') return false;
	if (v === 'null') return null;
	if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
	return v;
};

App._eq = function(a, b) {
	if (typeof a === 'string' && typeof b === 'string') return a.toLowerCase() === b.toLowerCase();
	return a === b;
};

App._fmtDate = function(iso) {
	if (!iso) return '\u2014';
	var d = new Date(iso * 1000);
	var now = new Date();
	var dateStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
	var diff = Math.floor((now - d) / 1000);
	var units = [
		{ label: 'year',   sec: 31536000 },
		{ label: 'month',  sec: 2592000 },
		{ label: 'day',    sec: 86400 },
		{ label: 'hour',   sec: 3600 },
		{ label: 'minute', sec: 60 },
	];
	var ago = 'just now';
	for (var i = 0; i < units.length; i++) {
		var n = Math.floor(diff / units[i].sec);
		if (n >= 1) { ago = n + ' ' + units[i].label + (n > 1 ? 's' : '') + ' ago'; break; }
	}
	return dateStr + ' (' + ago + ')';
};

App._debounce = function(fn, delay) {
	var t;
	return function() {
		var self = this, args = arguments;
		clearTimeout(t);
		t = setTimeout(function() { fn.apply(self, args); }, delay);
	};
};

// --- MD5 (pure JS, matches Python hashlib.md5) ---
App._md5 = (function() {
	function md5cycle(x,k){
		var a=x[0],b=x[1],c=x[2],d=x[3];
		a=ff(a,b,c,d,k[0],7,-680876936);d=ff(d,a,b,c,k[1],12,-389564586);c=ff(c,d,a,b,k[2],17,606105819);b=ff(b,c,d,a,k[3],22,-1044525330);
		a=ff(a,b,c,d,k[4],7,-176418897);d=ff(d,a,b,c,k[5],12,1200080426);c=ff(c,d,a,b,k[6],17,-1473231341);b=ff(b,c,d,a,k[7],22,-45705983);
		a=ff(a,b,c,d,k[8],7,1770035416);d=ff(d,a,b,c,k[9],12,-1958414417);c=ff(c,d,a,b,k[10],17,-42063);b=ff(b,c,d,a,k[11],22,-1990404162);
		a=ff(a,b,c,d,k[12],7,1804603682);d=ff(d,a,b,c,k[13],12,-40341101);c=ff(c,d,a,b,k[14],17,-1502002290);b=ff(b,c,d,a,k[15],22,1236535329);
		a=gg(a,b,c,d,k[1],5,-165796510);d=gg(d,a,b,c,k[6],9,-1069501632);c=gg(c,d,a,b,k[11],14,643717713);b=gg(b,c,d,a,k[0],20,-373897302);
		a=gg(a,b,c,d,k[5],5,-701558691);d=gg(d,a,b,c,k[10],9,38016083);c=gg(c,d,a,b,k[15],14,-660478335);b=gg(b,c,d,a,k[4],20,-405537848);
		a=gg(a,b,c,d,k[9],5,568446438);d=gg(d,a,b,c,k[14],9,-1019803690);c=gg(c,d,a,b,k[3],14,-187363961);b=gg(b,c,d,a,k[8],20,1163531501);
		a=gg(a,b,c,d,k[13],5,-1444681467);d=gg(d,a,b,c,k[2],9,-51403784);c=gg(c,d,a,b,k[7],14,1735328473);b=gg(b,c,d,a,k[12],20,-1926607734);
		a=hh(a,b,c,d,k[5],4,-378558);d=hh(d,a,b,c,k[8],11,-2022574463);c=hh(c,d,a,b,k[11],16,1839030562);b=hh(b,c,d,a,k[14],23,-35309556);
		a=hh(a,b,c,d,k[1],4,-1530992060);d=hh(d,a,b,c,k[4],11,1272893353);c=hh(c,d,a,b,k[7],16,-155497632);b=hh(b,c,d,a,k[10],23,-1094730640);
		a=hh(a,b,c,d,k[13],4,681279174);d=hh(d,a,b,c,k[0],11,-358537222);c=hh(c,d,a,b,k[3],16,-722521979);b=hh(b,c,d,a,k[6],23,76029189);
		a=hh(a,b,c,d,k[9],4,-640364487);d=hh(d,a,b,c,k[12],11,-421815835);c=hh(c,d,a,b,k[15],16,530742520);b=hh(b,c,d,a,k[2],23,-995338651);
		a=ii(a,b,c,d,k[0],6,-198630844);d=ii(d,a,b,c,k[7],10,1126891415);c=ii(c,d,a,b,k[14],15,-1416354905);b=ii(b,c,d,a,k[5],21,-57434055);
		a=ii(a,b,c,d,k[12],6,1700485571);d=ii(d,a,b,c,k[3],10,-1894986606);c=ii(c,d,a,b,k[10],15,-1051523);b=ii(b,c,d,a,k[1],21,-2054922799);
		a=ii(a,b,c,d,k[8],6,1873313359);d=ii(d,a,b,c,k[15],10,-30611744);c=ii(c,d,a,b,k[6],15,-1560198380);b=ii(b,c,d,a,k[13],21,1309151649);
		a=ii(a,b,c,d,k[4],6,-145523070);d=ii(d,a,b,c,k[11],10,-1120210379);c=ii(c,d,a,b,k[2],15,718787259);b=ii(b,c,d,a,k[9],21,-343485551);
		x[0]=add32(a,x[0]);x[1]=add32(b,x[1]);x[2]=add32(c,x[2]);x[3]=add32(d,x[3]);
	}
	function cmn(q,a,b,x,s,t){return add32(bitRol(add32(add32(a,q),add32(x,t)),s),b);}
	function ff(a,b,c,d,x,s,t){return cmn((b&c)|((~b)&d),a,b,x,s,t);}
	function gg(a,b,c,d,x,s,t){return cmn((b&d)|(c&(~d)),a,b,x,s,t);}
	function hh(a,b,c,d,x,s,t){return cmn(b^c^d,a,b,x,s,t);}
	function ii(a,b,c,d,x,s,t){return cmn(c^(b|(~d)),a,b,x,s,t);}
	function bitRol(n,c){return(n<<c)|(n>>>(32-c));}
	function add32(a,b){var lsw=(a&0xFFFF)+(b&0xFFFF);var msw=(a>>>16)+(b>>>16)+(lsw>>>16);return(msw<<16)|(lsw&0xFFFF);}

	function str2binl(str){
		var bin=[];
		var mask=(1<<8)-1;
		for(var i=0;i<str.length*8;i+=8)
			bin[i>>5]|=(str.charCodeAt(i/8)&mask)<<(i%32);
		return bin;
	}

	function binl2hex(bin){
		var hexTab='0123456789abcdef',str='';
		for(var i=0;i<bin.length*4;i++){
			str+=hexTab.charAt((bin[i>>2]>>((i%4)*8+4))&0xF)+hexTab.charAt((bin[i>>2]>>((i%4)*8))&0xF);
		}
		return str;
	}

	function core(s,len){
		s[len>>5]|=0x80<<((len)%32);
		s[(((len+64)>>>9)<<4)+14]=len;
		for(var i=15;i>(((len+64)>>>9)<<4)+14;i--) s[i]=0;
		var a=1732584193,b=-271733879,c=-1732584194,d=271733878;
		for(var i=0;i<s.length;i+=16){
			var k=s.slice(i,i+16);
			while(k.length<16)k.push(0);
			var state=[a,b,c,d];
			md5cycle(state,k);
			a=state[0];b=state[1];c=state[2];d=state[3];
		}
		return [a,b,c,d];
	}

	return function(str){
		var utf8=unescape(encodeURIComponent(str));
		return binl2hex(core(str2binl(utf8),utf8.length*8));
	};
})();

App._computeFileKey = function(screenName) {
	var safe = screenName.replace(/[^\w\-.]/g, '_');
	var hash6 = App._md5(screenName).substring(0, 6);
	return safe + '-' + hash6;
};

App._showProgress = function() {
	var pc = document.getElementById('progressContainer');
	if (pc) { pc.classList.remove('hidden'); document.getElementById('progressFill').style.width = '0%'; }
};

App._updateProgress = function(pct) {
	var pf = document.getElementById('progressFill');
	if (!pf) return;
	if (pct < 0) {
		pf.classList.add('indeterminate');
		pf.style.width = '';
	} else {
		pf.classList.remove('indeterminate');
		pf.style.width = Math.min(100, Math.max(0, pct)) + '%';
	}
};

App._hideProgress = function() {
	var pc = document.getElementById('progressContainer');
	if (pc) { pc.classList.add('hidden'); document.getElementById('progressFill').style.width = '0%'; }
};
