package jp.jun.iptv;

import android.content.Context;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class PlaylistCatalog {
    public static final String MODE_TV = "tv";
    public static final String MODE_RADIO = "radio";
    public static final String MODE_GAMBLE = "gamble";
    public static final String MODE_YOUTUBE = "youtube";
    public static final String MODE_SECRET = "secret";

    private static final String HIM = "https://raw.githubusercontent.com/ajiousama/himitsu/main/";
    private static final String SPORTS = "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/";

    private PlaylistCatalog() {}

    public static List<PlaylistSource> sources(String mode) {
        if (MODE_TV.equals(mode)) return Collections.singletonList(new PlaylistSource("Free Wi-Fi", HIM + "freewifi", HIM + "guides.xml", PlaylistSource.Filter.TV));
        if (MODE_RADIO.equals(mode)) return Collections.singletonList(new PlaylistSource("Radio", HIM + "radio.m3u", HIM + "guides.xml", PlaylistSource.Filter.ALL));
        if (MODE_GAMBLE.equals(mode)) return Collections.singletonList(new PlaylistSource("Public Sports", SPORTS + "public_sports.m3u", SPORTS + "epg.xml", PlaylistSource.Filter.ALL));
        if (MODE_YOUTUBE.equals(mode)) return Collections.singletonList(new PlaylistSource("ライブカメラ (YouTube)", HIM + "general_youtube.m3u", HIM + "guides.xml", PlaylistSource.Filter.ALL));
        return Collections.emptyList();
    }

    public static List<PlaylistSource> sources(Context context, String mode) {
        List<PlaylistSource> out = new ArrayList<>();
        if (MODE_SECRET.equals(mode)) {
            String m3u = AppPrefs.secretM3u(context);
            if (!m3u.isEmpty()) out.add(new PlaylistSource("秘密モード", m3u, AppPrefs.secretEpg(context), PlaylistSource.Filter.ALL));
            return out;
        }
        out.addAll(sources(mode));
        out.addAll(SourceManager.sources(context, mode));
        return out;
    }

    public static String title(String mode) {
        if (MODE_RADIO.equals(mode)) return "ラジオ";
        if (MODE_GAMBLE.equals(mode)) return "ギャンブル";
        if (MODE_YOUTUBE.equals(mode)) return "ライブカメラ (YouTube)";
        if (MODE_SECRET.equals(mode)) return "秘密モード";
        return "テレビ";
    }

    public static String[] selectableModes() { return new String[]{MODE_TV, MODE_RADIO, MODE_GAMBLE, MODE_YOUTUBE}; }
    public static String modeLabel(String mode) { return title(mode); }
}
