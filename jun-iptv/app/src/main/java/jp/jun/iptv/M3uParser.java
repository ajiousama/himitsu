package jp.jun.iptv;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class M3uParser {
    private static final Pattern ATTR = Pattern.compile("([A-Za-z0-9_-]+)=\\\"([^\\\"]*)\\\"");

    private M3uParser() {}

    public static List<Channel> parse(String text, PlaylistSource source) throws IOException {
        List<Channel> out = new ArrayList<>();
        BufferedReader br = new BufferedReader(new StringReader(text));
        String line;
        String ext = null;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (line.startsWith("#EXTINF:")) {
                ext = line;
                continue;
            }
            if (ext != null && !line.isEmpty() && !line.startsWith("#")) {
                Channel c = from(ext, line, source.name);
                ext = null;
                if (c != null && accept(c, source.filter)) out.add(c);
            }
        }
        return out;
    }

    private static Channel from(String ext, String url, String source) {
        String name = "Channel";
        int comma = ext.lastIndexOf(',');
        if (comma >= 0 && comma + 1 < ext.length()) name = ext.substring(comma + 1).trim();
        String group = "";
        String tvgId = "";
        String logo = "";
        Matcher m = ATTR.matcher(ext);
        while (m.find()) {
            String key = m.group(1).toLowerCase(Locale.ROOT);
            String val = m.group(2);
            if ("group-title".equals(key)) group = val;
            else if ("tvg-id".equals(key)) tvgId = val;
            else if ("tvg-logo".equals(key)) logo = val;
        }
        return new Channel(name, group, tvgId, logo, url, source);
    }

    private static boolean accept(Channel c, PlaylistSource.Filter filter) {
        if (filter == PlaylistSource.Filter.ALL) return true;
        String s = (c.group + " " + c.name + " " + c.source).toLowerCase(Locale.ROOT);
        String[] excluded = {
            "ラジオ", "radio", "競輪", "keirin", "ボート", "boat", "オート", "autorace",
            "地方競馬", "jra", "green channel", "グリーンチャンネル", "公営競技",
            "youtube", "youtube / live", "かなチューブ", "ゲームセンターcx"
        };
        for (String x : excluded) if (s.contains(x)) return false;
        return true;
    }
}
