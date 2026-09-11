package jp.jun.iptv;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.widget.ImageView;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LogoLoader {
    private static final Map<String, Bitmap> CACHE = new ConcurrentHashMap<>();
    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(3);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private LogoLoader() {}

    public static void load(ImageView view, String url) {
        view.setTag(url == null ? "" : url);
        view.setImageDrawable(null);
        if (url == null || url.trim().isEmpty()) return;
        Bitmap cached = CACHE.get(url);
        if (cached != null) {
            view.setImageBitmap(cached);
            return;
        }
        EXECUTOR.execute(() -> {
            HttpURLConnection con = null;
            try {
                con = (HttpURLConnection) new URL(url).openConnection();
                con.setConnectTimeout(5000);
                con.setReadTimeout(7000);
                con.setInstanceFollowRedirects(true);
                con.setRequestProperty("User-Agent", "JunIPTV/0.2.1");
                Bitmap bmp = BitmapFactory.decodeStream(con.getInputStream());
                if (bmp == null) return;
                CACHE.put(url, bmp);
                MAIN.post(() -> {
                    Object tag = view.getTag();
                    if (url.equals(tag)) view.setImageBitmap(bmp);
                });
            } catch (Exception ignored) {
            } finally {
                if (con != null) con.disconnect();
            }
        });
    }
}
