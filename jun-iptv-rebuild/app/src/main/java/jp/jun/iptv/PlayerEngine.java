package jp.jun.iptv;

import android.content.Context;

import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.ui.AspectRatioFrameLayout;
import androidx.media3.ui.PlayerView;

public final class PlayerEngine {
    public interface Listener {
        void onReady();
        void onBuffering();
        void onError(String message);
    }

    private final ExoPlayer player;
    private final PlayerView view;
    private final Listener listener;

    public PlayerEngine(Context c, PlayerView view, Listener listener) {
        this.view = view;
        this.listener = listener;
        DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
            .setUserAgent(Net.UA)
            .setAllowCrossProtocolRedirects(true)
            .setConnectTimeoutMs(12000)
            .setReadTimeoutMs(25000);
        DefaultDataSource.Factory data = new DefaultDataSource.Factory(c, http);
        player = new ExoPlayer.Builder(c)
            .setMediaSourceFactory(new DefaultMediaSourceFactory(data))
            .build();
        view.setPlayer(player);
        view.setUseController(false);
        player.addListener(new Player.Listener() {
            @Override public void onPlaybackStateChanged(int state) {
                if (state == Player.STATE_BUFFERING && listener != null) listener.onBuffering();
                if (state == Player.STATE_READY && listener != null) listener.onReady();
            }
            @Override public void onPlayerError(PlaybackException error) {
                if (listener != null) listener.onError(error.getErrorCodeName());
            }
        });
    }

    public void play(String url) {
        player.setMediaItem(MediaItem.fromUri(url));
        player.prepare();
        player.play();
    }

    public void retry() {
        player.prepare();
        player.play();
    }

    public void toggleAspect() {
        int m = view.getResizeMode();
        if (m == AspectRatioFrameLayout.RESIZE_MODE_FIT) view.setResizeMode(AspectRatioFrameLayout.RESIZE_MODE_ZOOM);
        else if (m == AspectRatioFrameLayout.RESIZE_MODE_ZOOM) view.setResizeMode(AspectRatioFrameLayout.RESIZE_MODE_FILL);
        else view.setResizeMode(AspectRatioFrameLayout.RESIZE_MODE_FIT);
    }

    public void release() { player.release(); }
}
