package jp.jun.iptv;

import android.content.Context;

import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.ui.PlayerView;

public class PlayerEngine {
    public interface ErrorListener { void onError(String message); }

    private final Context context;
    private final ExoPlayer player;
    private Channel channel;
    private boolean audible = true;

    public PlayerEngine(Context context, PlayerView view, ErrorListener listener) {
        this.context = context.getApplicationContext();
        player = new ExoPlayer.Builder(context).build();
        view.setPlayer(player);
        player.addListener(new Player.Listener() {
            @Override public void onPlayerError(PlaybackException error) {
                if (listener != null) listener.onError(error.getErrorCodeName());
            }
        });
        applyVolume();
    }

    public void play(Channel c) {
        channel = c;
        player.setMediaItem(MediaItem.fromUri(c.url));
        player.prepare();
        player.play();
        applyVolume();
    }

    public void setAudible(boolean audible) {
        this.audible = audible;
        applyVolume();
    }

    public void refreshVolume() { applyVolume(); }

    private void applyVolume() {
        player.setVolume(audible ? AppPrefs.volumeFloat(context) : 0f);
    }

    public Channel getChannel() { return channel; }
    public ExoPlayer getPlayer() { return player; }
    public void release() { player.release(); }
}
