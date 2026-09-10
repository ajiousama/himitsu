package jp.jun.iptv;

import android.os.Handler;
import android.os.Looper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PlaylistLoader {
    public interface Callback {
        void onLoaded(List<Channel> channels);
        void onError(String message);
    }

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    public void load(String mode, Callback callback) {
        executor.execute(() -> {
            try {
                Map<String, Channel> merged = new LinkedHashMap<>();
                for (PlaylistSource src : PlaylistCatalog.sources(mode)) {
                    String txt = Net.getText(src.m3uUrl);
                    for (Channel c : M3uParser.parse(txt, src)) {
                        String key = (!c.tvgId.isEmpty() ? c.tvgId : c.name) + "|" + c.url;
                        merged.putIfAbsent(key, c);
                    }
                }
                List<Channel> result = new ArrayList<>(merged.values());
                main.post(() -> callback.onLoaded(result));
            } catch (Exception e) {
                main.post(() -> callback.onError(e.getMessage() == null ? e.toString() : e.getMessage()));
            }
        });
    }

    public void shutdown() { executor.shutdownNow(); }
}
