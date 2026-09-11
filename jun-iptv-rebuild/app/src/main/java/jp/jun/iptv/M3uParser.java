package jp.jun.iptv;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class M3uParser {
    private static final Pattern ATTR = Pattern.compile("([A-Za-z0-9_-]+)=\"([^\"]*)\"");
    private M3uParser() {}

    public static List<Channel> parse(String text) {
        ArrayList<Channel> out = new ArrayList<>();
        String[] lines = text.replace("\r", "").split("\n");
        Channel pending = null;
        for (String raw : lines) {
            String line = raw.trim();
            if (line.startsWith("#EXTINF:")) {
                pending = new Channel();
                Matcher m = ATTR.matcher(line);
                while (m.find()) {
                    String k = m.group(1);
                    String v = m.group(2);
                    if ("tvg-id".equalsIgnoreCase(k)) pending.tvgId = v;
                    else if ("tvg-name".equalsIgnoreCase(k)) pending.tvgName = v;
                    else if ("tvg-logo".equalsIgnoreCase(k)) pending.logo = v;
                    else if ("group-title".equalsIgnoreCase(k)) pending.group = v;
                }
                int comma = line.lastIndexOf(',');
                pending.name = comma >= 0 ? line.substring(comma + 1).trim() : pending.tvgName;
                if (pending.name.isEmpty()) pending.name = pending.tvgName;
            } else if (!line.isEmpty() && !line.startsWith("#") && pending != null) {
                pending.url = line;
                out.add(pending);
                pending = null;
            }
        }
        return out;
    }
}
