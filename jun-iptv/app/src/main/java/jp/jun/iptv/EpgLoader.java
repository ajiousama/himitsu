package jp.jun.iptv;

import android.os.Handler;
import android.os.Looper;
import android.util.Xml;

import org.xmlpull.v1.XmlPullParser;

import java.io.InputStream;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class EpgLoader {
    public interface Callback { void onUpdated(); }
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    public void load(String mode, List<Channel> channels, Callback cb) {
        executor.execute(() -> {
            try {
                Set<String> wanted = new HashSet<>();
                for (Channel c : channels) if (!c.tvgId.isEmpty()) wanted.add(c.tvgId);
                if (wanted.isEmpty()) return;

                Set<String> urls = new HashSet<>();
                for (PlaylistSource s : PlaylistCatalog.sources(mode)) if (s.epgUrl != null && !s.epgUrl.isEmpty()) urls.add(s.epgUrl);
                Map<String, List<Programme>> map = new HashMap<>();
                for (String url : urls) parse(url, wanted, map);

                long now = System.currentTimeMillis();
                for (Channel c : channels) {
                    List<Programme> ps = map.get(c.tvgId);
                    if (ps == null) continue;
                    Programme current = null, next = null;
                    for (Programme p : ps) {
                        if (p.start <= now && now < p.stop) current = p;
                        else if (p.start > now && (next == null || p.start < next.start)) next = p;
                    }
                    c.nowProgram = current == null ? "" : current.title;
                    c.nextProgram = next == null ? "" : next.title;
                }
                main.post(cb::onUpdated);
            } catch (Exception ignored) {
                // Playback remains usable even if EPG is temporarily unavailable.
            }
        });
    }

    private void parse(String url, Set<String> wanted, Map<String, List<Programme>> out) throws Exception {
        try (InputStream in = Net.openStream(url)) {
            XmlPullParser x = Xml.newPullParser();
            x.setInput(in, "UTF-8");
            int event = x.getEventType();
            String ch = null, title = null;
            long start = 0, stop = 0;
            boolean keep = false;
            while (event != XmlPullParser.END_DOCUMENT) {
                if (event == XmlPullParser.START_TAG && "programme".equals(x.getName())) {
                    ch = x.getAttributeValue(null, "channel");
                    keep = ch != null && wanted.contains(ch);
                    title = null;
                    if (keep) {
                        start = parseTime(x.getAttributeValue(null, "start"));
                        stop = parseTime(x.getAttributeValue(null, "stop"));
                    }
                } else if (keep && event == XmlPullParser.START_TAG && "title".equals(x.getName())) {
                    title = x.nextText();
                } else if (event == XmlPullParser.END_TAG && "programme".equals(x.getName())) {
                    if (keep && title != null && start > 0 && stop > start) {
                        out.computeIfAbsent(ch, k -> new ArrayList<>()).add(new Programme(start, stop, title));
                    }
                    keep = false;
                }
                event = x.next();
            }
        }
    }

    private long parseTime(String value) {
        if (value == null || value.length() < 14) return 0;
        String v = value.trim();
        String[] fmts = {"yyyyMMddHHmmss Z", "yyyyMMddHHmmssZ", "yyyyMMddHHmmss"};
        for (String fmt : fmts) {
            try {
                SimpleDateFormat sdf = new SimpleDateFormat(fmt, Locale.US);
                if (!fmt.contains("Z")) sdf.setTimeZone(TimeZone.getTimeZone("Asia/Tokyo"));
                Date d = sdf.parse(v);
                if (d != null) return d.getTime();
            } catch (ParseException ignored) {}
        }
        return 0;
    }

    public void shutdown() { executor.shutdownNow(); }
    private static class Programme {
        final long start, stop; final String title;
        Programme(long start, long stop, String title) { this.start = start; this.stop = stop; this.title = title; }
    }
}
