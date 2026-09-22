#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')

def rw(rel, fn):
    p = ROOT / rel
    s = p.read_text(encoding='utf-8').replace('\r\n','\n')
    out = fn(s)
    if out == s:
        raise SystemExit(f'no change applied: {rel}')
    p.write_text(out, encoding='utf-8', newline='\n')
    print('patched', rel)

def one(s, old, new, label):
    if old not in s:
        raise SystemExit(f'pattern not found: {label}')
    return s.replace(old, new, 1)

# Home / TV home: first-run preset bootstrap.
for rel, player in [('assets/index.html','player/index.html'), ('assets/index-tv.html','player/index-tv.html')]:
    def patch_home(s, player=player):
        old = f'''}} else if( localStorage.getItem('bReadyForPlay') === "1" ) {{\n\twindow.location.href = "{player}";\n}} else {{'''
        new = f'''}} else if( localStorage.getItem('bReadyForPlay') === "1" ) {{\n\twindow.location.href = "{player}";\n}} else if( localStorage.getItem('iptvm3uPresetReady') !== '1' ) {{\n\twindow.location.href = "settings/index.html#iptvm3u_boot";\n}} else {{'''
        return one(s, old, new, rel)
    rw(rel, patch_home)

# Playlist worker: IPTV9X-compatible headers + virtual merged source.
def patch_worker(s):
    helpers = r'''

/* IPTV9X compatibility helpers: keep M3U IPTV native playback, but accept the
   common header/property variants seen in IPTV9X-compatible playlists. */
function iptvm3uSafeDecode( sValue ) {
    if( typeof(sValue) !== 'string' ) { return sValue || ''; }
    try { return decodeURIComponent(sValue.replace(/\+/g, '%20')); }
    catch( e ) { return sValue; }
}

function iptvm3uApplyHeaders( aChannel, sHeaders, bStoreRaw ) {
    if( !aChannel || !sHeaders ) { return; }
    sHeaders = String(sHeaders).trim();
    if( !sHeaders ) { return; }

    if( bStoreRaw !== false ) {
        if( aChannel.headers ) {
            if( aChannel.headers.indexOf(sHeaders) === -1 ) {
                aChannel.headers += '&' + sHeaders;
            }
        } else {
            aChannel.headers = sHeaders;
        }
    }

    var sParse = sHeaders;
    // Some lists URL-encode the complete header query string.
    if( sParse.indexOf('&') === -1 && /%26/i.test(sParse) ) {
        sParse = iptvm3uSafeDecode(sParse);
    }

    sParse.split('&').forEach(function(sPair) {
        if( !sPair ) { return; }
        var iEq = sPair.indexOf('=');
        if( iEq < 1 ) { return; }
        var sKey = iptvm3uSafeDecode(sPair.substring(0, iEq)).trim().toLowerCase();
        var sValue = iptvm3uSafeDecode(sPair.substring(iEq + 1)).trim();
        if( !sValue ) { return; }

        if( sKey === 'user-agent' || sKey === 'http-user-agent' || sKey === 'useragent' ) {
            aChannel.ua = sValue;
        } else if( sKey === 'referer' || sKey === 'referrer' || sKey === 'http-referer' || sKey === 'http-referrer' ) {
            aChannel.ref = sValue;
        }
    });
}

function iptvm3uAppendHeader( aChannel, sName, sValue ) {
    if( !sName || !sValue ) { return; }
    var sPair = sName + '=' + sValue;
    if( aChannel.headers ) {
        if( aChannel.headers.indexOf(sPair) === -1 ) { aChannel.headers += '&' + sPair; }
    } else {
        aChannel.headers = sPair;
    }
    iptvm3uApplyHeaders(aChannel, sPair, false);
}

function iptvm3uApplyExtHttp( aChannel, sJson ) {
    if( !aChannel || !sJson ) { return; }
    try {
        var oHeaders = JSON.parse(sJson);
        if( oHeaders && typeof(oHeaders) === 'object' ) {
            Object.keys(oHeaders).forEach(function(sKey) {
                var sValue = String(oHeaders[sKey]);
                iptvm3uAppendHeader(aChannel, sKey, sValue);
            });
        }
    } catch( e ) {
        // Leave malformed EXTHTTP lines untouched instead of failing the playlist.
    }
}
'''
    s = one(s, '\n\nfunction parsePlaylist( sContent ) {', helpers + '\nfunction parsePlaylist( sContent ) {', 'worker helpers')

    old = '''\t\t\tsLine = sLine.trim();\n\n\t\t\tif( sLine.startsWith('#EXTVLCOPT:') ) {\n\n\t\t\t\tif( sLine.indexOf('#EXTVLCOPT:http-referrer=') === 0 ) {\n\t\t\t\t\taChannel.ref = sLine.replace('#EXTVLCOPT:http-referrer=', '');\n\t\t\t\t} else if( sLine.indexOf('#EXTVLCOPT:http-referer=') === 0 ) {\n\t\t\t\t\taChannel.ref = sLine.replace('#EXTVLCOPT:http-referer=', '');\n\t\t\t\t} else if( sLine.indexOf('#EXTVLCOPT:http-user-agent=') === 0 ) {\n\t\t\t\t\taChannel.ua = sLine.replace('#EXTVLCOPT:http-user-agent=', '');\n\t\t\t\t}\n\n\t\t\t} else if( sLine.startsWith('#KODIPROP:') ) {\n\n\t\t\t\tif( sLine.indexOf('#KODIPROP:inputstream.adaptive.license_type') === 0 ) {\n\t\t\t\t\taChannel.drmT = sLine.replace('#KODIPROP:inputstream.adaptive.license_type=', '');\n\t\t\t\t} else if( sLine.indexOf('#KODIPROP:inputstream.adaptive.license_key=') === 0 ) {\n\t\t\t\t\taChannel.drmK = sLine.replace('#KODIPROP:inputstream.adaptive.license_key=', '');\n\t\t\t\t} else if( sLine.indexOf('#KODIPROP:inputstream.adaptive.stream_headers=referer=') === 0 ) {\n\t\t\t\t\taChannel.ref = sLine.replace('#KODIPROP:inputstream.adaptive.stream_headers=referer=', '');\n\t\t\t\t} else if( sLine.indexOf('#KODIPROP:inputstream.adaptive.stream_headers=user-agent=') === 0 ) {\n\t\t\t\t\taChannel.ua = sLine.replace('#KODIPROP:inputstream.adaptive.stream_headers=user-agent=', '');\n\t\t\t\t} else if( sLine.indexOf('#KODIPROP:inputstream.adaptive.stream_headers=') === 0 ) {\n\t\t\t\t    aChannel.headers = sLine.replace('#KODIPROP:inputstream.adaptive.stream_headers=', '');\n\t\t\t\t}\n\n\t\t\t} else if( sLine.startsWith('#EXTGRP:') ) {'''
    new = '''\t\t\tsLine = sLine.trim();\n\n\t\t\tif( sLine.toUpperCase().startsWith('#EXTVLCOPT:') ) {\n\n\t\t\t\tvar sVlcOpt = sLine.substring(sLine.indexOf(':') + 1), iVlcEq = sVlcOpt.indexOf('=');\n\t\t\t\tif( iVlcEq > 0 ) {\n\t\t\t\t\tvar sVlcKey = sVlcOpt.substring(0, iVlcEq).trim().toLowerCase();\n\t\t\t\t\tvar sVlcVal = sVlcOpt.substring(iVlcEq + 1).trim();\n\t\t\t\t\tif( sVlcKey === 'http-referrer' || sVlcKey === 'http-referer' ) {\n\t\t\t\t\t\taChannel.ref = iptvm3uSafeDecode(sVlcVal);\n\t\t\t\t\t} else if( sVlcKey === 'http-user-agent' ) {\n\t\t\t\t\t\taChannel.ua = iptvm3uSafeDecode(sVlcVal);\n\t\t\t\t\t} else if( sVlcKey === 'http-origin' ) {\n\t\t\t\t\t\tiptvm3uAppendHeader(aChannel, 'Origin', sVlcVal);\n\t\t\t\t\t} else if( sVlcKey === 'http-cookie' ) {\n\t\t\t\t\t\tiptvm3uAppendHeader(aChannel, 'Cookie', sVlcVal);\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t} else if( sLine.toUpperCase().startsWith('#KODIPROP:') ) {\n\n\t\t\t\tvar sKodiProp = sLine.substring(sLine.indexOf(':') + 1), iKodiEq = sKodiProp.indexOf('=');\n\t\t\t\tif( iKodiEq > 0 ) {\n\t\t\t\t\tvar sKodiKey = sKodiProp.substring(0, iKodiEq).trim().toLowerCase();\n\t\t\t\t\tvar sKodiVal = sKodiProp.substring(iKodiEq + 1).trim();\n\t\t\t\t\tif( sKodiKey === 'inputstream.adaptive.license_type' ) {\n\t\t\t\t\t\taChannel.drmT = sKodiVal;\n\t\t\t\t\t} else if( sKodiKey === 'inputstream.adaptive.license_key' ) {\n\t\t\t\t\t\taChannel.drmK = sKodiVal;\n\t\t\t\t\t} else if( sKodiKey === 'inputstream.adaptive.stream_headers' || sKodiKey === 'inputstream.adaptive.manifest_headers' ) {\n\t\t\t\t\t\tiptvm3uApplyHeaders(aChannel, sKodiVal, true);\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t} else if( sLine.toUpperCase().startsWith('#EXTHTTP:') ) {\n\n\t\t\t\tiptvm3uApplyExtHttp(aChannel, sLine.substring(sLine.indexOf(':') + 1));\n\n\t\t\t} else if( sLine.startsWith('#EXTGRP:') ) {'''
    s = one(s, old, new, 'worker header parser')

    old = '''\t\t\t\tif( !aChannel.headers && sLine.indexOf('|') > 10 ) {\n\t\t\t\t\tvar aUrlHeader = sLine.split('|');\n\t\t\t\t\tif( aUrlHeader.length == 2 ) {\n\t\t\t\t\t\tsLine = aUrlHeader[0];\n\t\t\t\t\t\taChannel.headers = aUrlHeader[1];\n\t\t\t\t\t}\n\t\t\t\t}'''
    new = '''\t\t\t\tvar iPipePos = sLine.indexOf('|');\n\t\t\t\tif( iPipePos > 10 ) {\n\t\t\t\t\tvar sPipeHeaders = sLine.substring(iPipePos + 1);\n\t\t\t\t\tsLine = sLine.substring(0, iPipePos);\n\t\t\t\t\tiptvm3uApplyHeaders(aChannel, sPipeHeaders, true);\n\t\t\t\t}'''
    s = one(s, old, new, 'worker pipe headers')

    grab = r'''

function grabIptvM3uDefault( oPlaylist ) {
\tvar aSources = [
\t\t'https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi',
\t\t'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u',
\t\t'https://raw.githubusercontent.com/ajiousama/himitsu/main/radio.m3u',
\t\t'https://raw.githubusercontent.com/ajiousama/himitsu/main/general_youtube.m3u'
\t];
\tvar aParts = [], iPos = 0;
\tpostMessage('downloading');

\tfunction next() {
\t\tif( iPos >= aSources.length ) {
\t\t\tvar sHead = '#EXTM3U url-tvg="https://raw.githubusercontent.com/ajiousama/himitsu/main/iptvm3u_epg.xml"\\n';
\t\t\tvar sMerged = sHead;
\t\t\tfor( var i = 0; i < aParts.length; i++ ) {
\t\t\t\tvar sPart = aParts[i] || '';
\t\t\t\tsPart = sPart.replace(/^\\uFEFF/, '');
\t\t\t\tsPart = sPart.replace(/^#EXTM3U[^\\r\\n]*(?:\\r?\\n)?/i, '');
\t\t\t\tsMerged += '\\n' + sPart;
\t\t\t}
\t\t\tprocessPlaylistData(sMerged);
\t\t\treturn;
\t\t}

\t\tvar sUrl = aSources[iPos++];
\t\tfireRequest(sUrl, false, function(oHttp) {
\t\t\taParts.push(oHttp.response || oHttp.responseText || '');
\t\t\tnext();
\t\t}, function(oHttp) {
\t\t\tpostMessage('ERROR: IPTVM3U source failed: ' + sUrl + ' (' + (oHttp.status || 0) + ')');
\t\t\tself.close();
\t\t});
\t}
\tnext();
}
'''
    s = one(s, '\n\nfunction grabPlaylist( oPlaylist, bProxyFallback, oOriginHttp ) {', grab + '\n\nfunction grabPlaylist( oPlaylist, bProxyFallback, oOriginHttp ) {', 'worker preset grab')
    old = '''\t\t\t\tif( aData.localPlaylist ) {\n\t\t\t\t\tprocessPlaylistData(aData.localPlaylist);\n\t\t\t\t} else {\n\t\t\t\t\tgrabPlaylist(oPlaylist, false);'''
    new = '''\t\t\t\tif( aData.localPlaylist ) {\n\t\t\t\t\tprocessPlaylistData(aData.localPlaylist);\n\t\t\t\t} else if( oPlaylist.url === 'iptvm3u://default' ) {\n\t\t\t\t\tgrabIptvM3uDefault(oPlaylist);\n\t\t\t\t} else {\n\t\t\t\t\tgrabPlaylist(oPlaylist, false);'''
    s = one(s, old, new, 'worker virtual url')
    return s
rw('assets/js/playlist-worker.js', patch_worker)

# Always refresh the preset source on app startup.
def patch_player(s):
    old = '''\tif( !bDownloadRunning && oCurrentPlaylist && oCurrentPlaylist.startReload && window.Worker && oCurrentPlaylist.grabtime < (iAppStartTime - 120000)\n\t\t&& (oCurrentPlaylist.type === 'url' || oCurrentPlaylist.type === 'xtream') ) {'''
    new = '''\tvar bIptvM3uPreset = !!(oCurrentPlaylist && (oCurrentPlaylist.iptvm3u || oCurrentPlaylist.url === 'iptvm3u://default'));\n\tvar bNeedsStartupRefresh = bIptvM3uPreset ? true : (oCurrentPlaylist && oCurrentPlaylist.grabtime < (iAppStartTime - 120000));\n\n\tif( !bDownloadRunning && oCurrentPlaylist && oCurrentPlaylist.startReload && window.Worker && bNeedsStartupRefresh\n\t\t&& (oCurrentPlaylist.type === 'url' || oCurrentPlaylist.type === 'xtream') ) {'''
    return one(s, old, new, 'player startup refresh')
rw('assets/player/js/playlist.js', patch_player)

# Fresh-install preset creation.
def patch_settings_playlist(s):
    marker = '\n\nfunction updateAllPlaylists() {'
    fn = r'''

function ensureIptvM3uPreset( sOnReady ) {
\tvar sDone = function() { if( typeof(sOnReady) === 'function' ) { sOnReady(); } };
\tvar sPreset = localStorage.getItem('iptvm3uPresetReady');

\tloadPlaylists(function(iCount) {
\t\t// Preserve any user-created playlist. Auto-provision only on a fresh install.
\t\tif( iCount > 0 || sPreset === '1' ) {
\t\t\tsDone(); return;
\t\t}

\t\tiCurrentEditId = 1;
\t\tif( !aLoadedPlaylists || typeof(aLoadedPlaylists) !== 'object' ) { aLoadedPlaylists = {}; }

\t\tvar oPreset = {
\t\t\tid: 1,
\t\t\tname: 'IPTVM3U',
\t\t\ttype: 'url',
\t\t\turl: 'iptvm3u://default',
\t\t\tepgUrl: 'https://raw.githubusercontent.com/ajiousama/himitsu/main/iptvm3u_epg.xml',
\t\t\tchannelCount: 0,
\t\t\tarchiveType: '-',
\t\t\tstartReload: true,
\t\t\tiptvm3u: true
\t\t};

\t\taLoadedPlaylists[1] = oPreset;
\t\toCurrentEditPlaylist = oPreset;
\t\tbIsNewPlaylist = false;
\t\tsetPlaylistNavItem(oPreset);
\t\tiPlayListCount = 1;

\t\tdownloadPlaylistManager(oPreset, false, function() {
\t\t\toPreset.saved = true;
\t\t\tlocalStorage.setItem('aPlaylists', JSON.stringify({1: oPreset}));
\t\t\tlocalStorage.setItem('iCurrentPlaylistId', '1');
\t\t\tlocalStorage.setItem('bReadyForPlay', '1');
\t\t\tlocalStorage.setItem('iptvm3uPresetReady', '1');

\t\t\tvar oEpg = {
\t\t\t\tid: 1,
\t\t\t\tpid: 1,
\t\t\t\turl: oPreset.epgUrl,
\t\t\t\ttimeshift: 0,
\t\t\t\tstatus: '',
\t\t\t\tgrabtime: 0,
\t\t\t\tiptvm3u: true
\t\t\t};
\t\t\tlocalStorage.setItem('aEpgSources', JSON.stringify({1: oEpg}));
\t\t\tsDone();
\t\t});
\t}, sDone);
}
'''
    return one(s, marker, fn + marker, 'settings playlist preset')
rw('assets/settings/js/playlist.js', patch_settings_playlist)

# Hook preset provisioning into settings boot.
def patch_settings(s):
    old = '''\tinitDb(function() { // DB successfully loaded, load playlists next\n\t\tbootPlaylistReady(function() {'''
    new = '''\tinitDb(function() { // DB successfully loaded, load playlists next\n\t\tensureIptvM3uPreset(function() {\n\t\tbootPlaylistReady(function() {'''
    s = one(s, old, new, 'settings boot open')
    old = '''\t\t\tdocument.body.classList.remove('booting');\n\t\t\topenNavList(sCurrentNavId);\n\t\t\tbBootComplete = true;\n\t\t});\n\t}, function(oEv) { // DB failure'''
    new = '''\t\t\tdocument.body.classList.remove('booting');\n\t\t\tif( sCurrentNavId === 'iptvm3u_boot' ) {\n\t\t\t\twindow.location.href = '../player/index.html';\n\t\t\t\treturn;\n\t\t\t}\n\t\t\topenNavList(sCurrentNavId);\n\t\t\tbBootComplete = true;\n\t\t});\n\t\t});\n\t}, function(oEv) { // DB failure'''
    return one(s, old, new, 'settings boot close')
rw('assets/settings/js/settings.js', patch_settings)
