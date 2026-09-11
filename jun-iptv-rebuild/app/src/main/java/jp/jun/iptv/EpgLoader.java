package jp.jun.iptv;

import android.os.Handler;
import android.util.Xml;

import org.xmlpull.v1.XmlPullParser;

import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class EpgLoader {
    public interface Callback { void done(); }
    private final ExecutorService pool = Executors.newSingleThreadExecutor();

    public void load(String url, List<Channel> channels, Handler ui, Callback cb) {
        pool.submit(() -> {
            try {
                Map<String, Channel> byId = new HashMap<>();
                Map<Channel, Long> nextStart = new HashMap<>();
                for (Channel c : channels) {
                    if (!c.tvgId.isEmpty()) byId.put(c.tvgId, c);
                    if (!c.tvgName.isEmpty()) byId.putIfAbsent(c.tvgName, c);
                }
                long now = System.currentTimeMillis();
                try (InputStream in = Net.stream(url)) {
                    XmlPullParser x = Xml.newPullParser();
                    x.setInput(in, "UTF-8");
                    int e;
                    String channelId = null, startS = null, stopS = null, title = null;
                    boolean inProgram = false;
                    while ((e = x.next()) != XmlPullParser.END_DOCUMENT) {
                        if (e == XmlPullParser.START_TAG) {
                            String n = x.getName();
                            if ("programme".equals(n)) {
                                channelId = x.getAttributeValue(null, "channel");
                                if (!byId.containsKey(channelId)) {
                                    skip(x);
                                    continue;
                                }
                                startS = x.getAttributeValue(null, "start");
                                stopS = x.getAttributeValue(null, "stop");
                                title = "";
                                inProgram = true;
                            } else if (inProgram && "title".equals(n)) {
                                title = x.nextText();
                            }
                        } else if (e == XmlPullParser.END_TAG && "programme".equals(x.getName()) && inProgram) {
                            Channel c = byId.get(channelId);
                            if (c != null) {
                                long start = parseTime(startS), stop = parseTime(stopS);
                                if (start <= now && now < stop) {
                                    c.nowTitle = title == null ? "" : title;
                                    c.nowStart = start;
                                    c.nowStop = stop;
                                } else if (start > now) {
                                    Long old = nextStart.get(c);
                                    if (old == null || start < old) {
                                        nextStart.put(c, start);
                                        c.nextTitle = title == null ? "" : title;
                                    }
                                }
                            }
                            inProgram = false;
                        }
                    }
                }
            } catch (Exception ignored) {
            } finally {
                ui.post(cb::done);
            }
        });
    }

    private static void skip(XmlPullParser x) throws Exception {
        int depth = 1;
        while (depth != 0) {
            int e = x.next();
            if (e == XmlPullParser.START_TAG) depth++;
            else if (e == XmlPullParser.END_TAG) depth--;
        }
    }

    private static long parseTime(String s) {
        if (s == null || s.length() < 14) return 0L;
        try {
            String base = s.substring(0, 14);
            SimpleDateFormat f = new SimpleDateFormat("yyyyMMddHHmmss", Locale.US);
            f.setTimeZone(TimeZone.getTimeZone("UTC"));
            long t = f.parse(base).getTime();
            if (s.length() >= 20) {
                char sign = s.charAt(15);
                int hh = Integer.parseInt(s.substring(16, 18));
                int mm = Integer.parseInt(s.substring(18, 20));
                long off = (hh * 60L + mm) * 60000L;
                t -= sign == '+' ? off : -off;
            }
            return t;
        } catch (Exception e) {
            return 0L;
        }
    }

    public void shutdown() { pool.shutdownNow(); }
}
