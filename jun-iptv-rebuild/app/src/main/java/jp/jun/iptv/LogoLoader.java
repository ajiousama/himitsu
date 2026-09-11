package jp.jun.iptv;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.widget.ImageView;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LogoLoader {
    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Map<String, Bitmap> CACHE = Collections.synchronizedMap(
        new LinkedHashMap<String, Bitmap>(80, .75f, true) {
            @Override protected boolean removeEldestEntry(Map.Entry<String, Bitmap> e) { return size() > 80; }
        });

    private LogoLoader() {}

    public static void load(ImageView view, String url) {
        view.setImageDrawable(null);
        if (url == null || url.isBlank()) return;
        Bitmap cached = CACHE.get(url);
        if (cached != null) {
            view.setImageBitmap(cached);
            return;
        }
        view.setTag(url);
        POOL.submit(() -> {
            Bitmap b = null;
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(7000);
                c.setReadTimeout(10000);
                c.setInstanceFollowRedirects(true);
                c.setRequestProperty("User-Agent", Net.UA);
                try (InputStream in = c.getInputStream()) { b = BitmapFactory.decodeStream(in); }
                c.disconnect();
            } catch (Exception ignored) {}
            if (b != null) {
                CACHE.put(url, b);
                Bitmap result = b;
                view.post(() -> {
                    Object tag = view.getTag();
                    if (url.equals(tag)) view.setImageBitmap(result);
                });
            }
        });
    }
}
