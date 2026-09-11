# Jun IPTV Rebuild — M3U IPTV behavior reference

This branch is a clean rebuild. The original M3U IPTV APK/XAPK is used only as a behavioral reference. Do not copy proprietary source code, icons, images, or bundled assets.

## Goal

Recreate the Android TV experience so that the baseline feels like M3U IPTV, then add Jun-only features without changing the baseline interaction model.

## Core remote behavior

Mandatory controls must work on all three target remotes and therefore use only D-pad, OK, Back, Home, Volume +/- and Mute.

### Player screen
- Up / Down: previous / next channel, always wrap from first to last and last to first.
- Left: open channel list.
- Left again while channel list is open: open groups / advanced navigation.
- Right: open channel settings / stream options.
- OK: show channel information.
- Second OK while channel information is visible: open playback controls / programme browser.
- Back: close the top-most overlay; only leave the player when no overlay remains.
- Volume +/- and Mute: audio.

Dedicated Menu, Info, P+/-, transport keys, voice keys and app shortcut keys may be supported as optional shortcuts but may never be required.

## M3U IPTV baseline features to reproduce

### Navigation / viewing
- Full-screen playback as the normal player state.
- Channel list overlay with logo, channel name and EPG now/next where available.
- Groups list and an advanced navigation layer containing settings/search/guide entry points.
- Search.
- Favorites.
- Last channel / previous channel behavior.
- Immediate channel-change OSD: logo + channel name + connecting state; never ambiguous black screen.
- Configurable compact/minimal switch OSD.
- Optional channel-list side (left/right), but Jun default remains left.
- Channel list and direct channel switching wrap around.

### EPG
- XMLTV source support.
- Multiple EPG sources.
- Current/next programme display.
- Programme overview / guide.
- Time shift setting for EPG.
- Refresh interval.
- Retention for past/future programme data.
- Programme descriptions optional.
- Catch-up/archive hooks when a provider supports them.

### Playlist management
- URL M3U/M3U8 source.
- Local/storage M3U source later where Android TV file access is reliable.
- Multiple playlists/providers.
- Per-provider name, enabled state and EPG association.
- Refresh playlist at startup option.
- Preserve tvg-id, tvg-name, tvg-logo, group-title and url-tvg.
- User-Agent/header support for providers that need it.

### Playback settings
- HLS and ordinary HTTP/HTTPS streams.
- Cleartext HTTP option for legacy feeds.
- Buffer-size presets.
- Audio tracks.
- Subtitle tracks and subtitle toggle.
- Video format: original / fill-stretch / zoom.
- Resolution/variant selection where available.
- Retry/reconnect with visible status.
- Background playback optional.
- Remember last channel.

### Organization / protection
- Groups.
- Favorites.
- Channel rename/move/delete in local presentation metadata.
- Channel/group protection with PIN.
- Settings protection with PIN.
- Backup/restore of providers, favorites, groups and settings later.

## Jun-only additions

These are added only after the M3U IPTV-style baseline is stable.

1. 4 / 6 / 8 pane multiview. Only focused pane has audio.
2. Separate YouTube live-camera provider. Resolve/reacquire a playable current stream at playback time instead of showing an embedded YouTube page.
3. KICK provider/adapter. Resolve the redirect/API endpoint before giving the final stream to the player; offline is not an error state for non-24h channels.
4. TVer launcher. Launch the installed official TVer app only; never fall back to a browser. Android package visibility must be declared.
5. Jun secret mode: hidden entry sequence + PIN + editable M3U/EPG URL. No source URL hard-coded.
6. App volume and OSD.
7. Optional recording/timeshift after the baseline player is stable.

## Display modes

The player engine is shared by TV, radio, public sports, live camera and YouTube-derived live feeds.

- Full screen: video fills the display.
- Guide mode: persistent channel/programme panel and the video is physically resized into the remaining area, not merely covered by an overlay.
- App mode: full-screen playback; Left opens the channel list as an overlay.
- Multiview: 4/6/8 panes selected in settings.

## First rebuild milestone

Do not implement all Jun additions at once. The first APK must prove the baseline:

- one normal M3U provider loads reliably;
- logos render;
- Up/Down channel switching wraps;
- channel-change OSD appears before playback starts;
- Left channel list, Left again groups/options, Right settings, OK info, Back close-layer behavior;
- guide mode resizes the video correctly;
- XMLTV now/next works;
- stream errors are explicit and retryable;
- no YouTube, KICK, TVer, multiview or secret-mode code in the first baseline build.

Only after that APK behaves correctly on TS-401 do Jun-only adapters get added one at a time.
