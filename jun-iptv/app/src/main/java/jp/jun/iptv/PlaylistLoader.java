package jp.jun.iptv;

import android.content.Context;
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
        loadInternal(PlaylistCatalog.sources(mode), callback);
    }

    public void load(Context context, String mode, Callback callback) {
        loadInternal(PlaylistCatalog.sources(context, mode), callback);
    }

    private void loadInternal(List<PlaylistSource> sources, Callback callback) {
        executor.execute(() -> {
            try {
                Map<String, Channel> merged = new LinkedHashMap<>();
                for (PlaylistSource src : sources) {
                    try {
                        String txt = Net.getText(src.m3uUrl);
                        for (Channel c : M3uParser.parse(txt, src)) {
                            String key = (!c.tvgId.isEmpty() ? c.tvgId : c.name) + "|" + c.url;
                            merged.putIfAbsent(key, c);
                        }
                    } catch (Exception ignored) {
                        // One broken provider must not hide all the other providers.
                    }
                }
                List<Channel> result = new ArrayList<>(merged.values());
                if (result.isEmpty()) throw new IllegalStateException("再生できるチャンネルを取得できませんでした");
                main.post(() -> callback.onLoaded(result));
            } catch (Exception e) {
                main.post(() -> callback.onError(e.getMessage() == null ? e.toString() : e.getMessage()));
            }
        });
    }

    public void shutdown() { executor.shutdownNow(); }
}
