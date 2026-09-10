package jp.jun.iptv;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class PlaylistCatalog {
    public static final String MODE_TV = "tv";
    public static final String MODE_RADIO = "radio";
    public static final String MODE_GAMBLE = "gamble";
    public static final String MODE_HIGH_SCHOOL = "highschool";

    private static final String HIM = "https://raw.githubusercontent.com/ajiousama/himitsu/main/";
    private static final String SPORTS = "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/";

    private PlaylistCatalog() {}

    public static List<PlaylistSource> sources(String mode) {
        if (MODE_TV.equals(mode)) {
            return Arrays.asList(
                new PlaylistSource("Free Wi-Fi", HIM + "freewifi", HIM + "guides.xml", PlaylistSource.Filter.TV),
                new PlaylistSource("YouTube / LIVE", HIM + "general_youtube.m3u", HIM + "guides.xml", PlaylistSource.Filter.ALL)
            );
        }
        if (MODE_RADIO.equals(mode)) {
            return Collections.singletonList(
                new PlaylistSource("Radio", HIM + "radio.m3u", HIM + "guides.xml", PlaylistSource.Filter.ALL)
            );
        }
        if (MODE_GAMBLE.equals(mode)) {
            return Collections.singletonList(
                new PlaylistSource("Public Sports", SPORTS + "public_sports.m3u", SPORTS + "epg.xml", PlaylistSource.Filter.ALL)
            );
        }
        if (MODE_HIGH_SCHOOL.equals(mode)) {
            return Collections.singletonList(
                new PlaylistSource("高校野球", HIM + "kokouyakyu", "", PlaylistSource.Filter.ALL)
            );
        }
        return Collections.emptyList();
    }

    public static String title(String mode) {
        if (MODE_RADIO.equals(mode)) return "ラジオ";
        if (MODE_GAMBLE.equals(mode)) return "ギャンブル";
        if (MODE_HIGH_SCHOOL.equals(mode)) return "高校野球（裏）";
        return "テレビ";
    }
}
