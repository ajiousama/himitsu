package jp.jun.iptv;

import android.content.Context;
import android.content.SharedPreferences;

public final class AppPrefs {
    public static final String PREFS = "jun_iptv_settings";
    public static final String DISPLAY_FULLSCREEN = "fullscreen";
    public static final String DISPLAY_GUIDE = "guide";
    public static final String DISPLAY_APP = "app";
    public static final String DISPLAY_MULTI = "multi";

    private AppPrefs() {}

    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String displayMode(Context c) {
        return p(c).getString("display_mode", DISPLAY_APP);
    }

    public static void setDisplayMode(Context c, String mode) {
        p(c).edit().putString("display_mode", mode).apply();
    }

    public static int multiCount(Context c) {
        int v = p(c).getInt("multi_count", 4);
        return (v == 6 || v == 8) ? v : 4;
    }

    public static void setMultiCount(Context c, int count) {
        p(c).edit().putInt("multi_count", count).apply();
    }

    public static int volume(Context c) {
        return Math.max(0, Math.min(100, p(c).getInt("app_volume", 100)));
    }

    public static void setVolume(Context c, int volume) {
        p(c).edit().putInt("app_volume", Math.max(0, Math.min(100, volume))).apply();
    }

    public static float volumeFloat(Context c) {
        return volume(c) / 100f;
    }
}
