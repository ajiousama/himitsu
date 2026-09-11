package jp.jun.iptv;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public final class SourceManager {
    private static final String KEY = "custom_sources";

    public static class Entry {
        public final String name, mode, m3u, epg;
        Entry(String name, String mode, String m3u, String epg) {
            this.name = name; this.mode = mode; this.m3u = m3u; this.epg = epg;
        }
    }

    private SourceManager() {}

    public static List<Entry> all(Context c) {
        List<Entry> out = new ArrayList<>();
        String raw = c.getSharedPreferences(AppPrefs.PREFS, Context.MODE_PRIVATE).getString(KEY, "[]");
        try {
            JSONArray a = new JSONArray(raw);
            for (int i = 0; i < a.length(); i++) {
                JSONObject o = a.getJSONObject(i);
                out.add(new Entry(
                    o.optString("name", "追加M3U"),
                    o.optString("mode", PlaylistCatalog.MODE_TV),
                    o.optString("m3u", ""),
                    o.optString("epg", "")
                ));
            }
        } catch (Exception ignored) {}
        return out;
    }

    public static List<PlaylistSource> sources(Context c, String mode) {
        List<PlaylistSource> out = new ArrayList<>();
        for (Entry e : all(c)) {
            if (mode.equals(e.mode) && !e.m3u.isEmpty()) {
                out.add(new PlaylistSource(e.name, e.m3u, e.epg, PlaylistSource.Filter.ALL));
            }
        }
        return out;
    }

    public static void add(Context c, String name, String mode, String m3u, String epg) {
        List<Entry> list = all(c);
        list.add(new Entry(name, mode, m3u, epg));
        save(c, list);
    }

    public static void remove(Context c, int index) {
        List<Entry> list = all(c);
        if (index >= 0 && index < list.size()) {
            list.remove(index);
            save(c, list);
        }
    }

    private static void save(Context c, List<Entry> list) {
        JSONArray a = new JSONArray();
        try {
            for (Entry e : list) {
                JSONObject o = new JSONObject();
                o.put("name", e.name);
                o.put("mode", e.mode);
                o.put("m3u", e.m3u);
                o.put("epg", e.epg);
                a.put(o);
            }
        } catch (Exception ignored) {}
        c.getSharedPreferences(AppPrefs.PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, a.toString()).apply();
    }
}
