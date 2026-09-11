package jp.jun.iptv;

import android.content.Context;
import android.content.SharedPreferences;

public final class Prefs {
    private static final String N = "jun_rebuild";
    public static final String DEFAULT_M3U = "https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi";
    public static final String DEFAULT_EPG = "https://raw.githubusercontent.com/ajiousama/himitsu/main/guides.xml";

    private Prefs() {}

    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences(N, Context.MODE_PRIVATE);
    }

    public static String m3u(Context c) { return p(c).getString("m3u", DEFAULT_M3U); }
    public static String epg(Context c) { return p(c).getString("epg", DEFAULT_EPG); }
    public static boolean guideMode(Context c) { return p(c).getBoolean("guide_mode", false); }
    public static int lastIndex(Context c) { return p(c).getInt("last_index", 0); }

    public static void saveSource(Context c, String m3u, String epg) {
        p(c).edit().putString("m3u", m3u).putString("epg", epg).apply();
    }
    public static void setGuideMode(Context c, boolean v) {
        p(c).edit().putBoolean("guide_mode", v).apply();
    }
    public static void setLastIndex(Context c, int i) {
        p(c).edit().putInt("last_index", i).apply();
    }
    public static boolean favorite(Context c, String id) {
        return p(c).getBoolean("fav_" + safe(id), false);
    }
    public static void toggleFavorite(Context c, String id) {
        String k = "fav_" + safe(id);
        p(c).edit().putBoolean(k, !p(c).getBoolean(k, false)).apply();
    }
    private static String safe(String s) {
        return Integer.toHexString((s == null ? "" : s).hashCode());
    }
}
