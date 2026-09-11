package jp.jun.iptv;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.List;

public class ChannelActivity extends Activity {
    private final List<Channel> channels = new ArrayList<>();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private PlaylistLoader loader;
    private EpgLoader epg;
    private ChannelAdapter adapter;
    private ListView list;
    private LinearLayout channelPanel, infoPanel, switchOsd;
    private FrameLayout playerHost;
    private PlayerView playerView;
    private PlayerEngine engine;
    private TextView status, nowTitle, nowProgram, nextProgram, switchName, switchState;
    private ImageView switchLogo;
    private String mode;
    private String displayMode;
    private int current = -1;
    private int youtubeRetryAttempted = -1;
    private final Runnable hideOsd = () -> switchOsd.setVisibility(View.GONE);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_channel);
        mode = getIntent().getStringExtra("mode");
        if (mode == null) mode = PlaylistCatalog.MODE_TV;
        displayMode = getIntent().getBooleanExtra("forceFullscreen", false)
            ? AppPrefs.DISPLAY_FULLSCREEN : AppPrefs.displayMode(this);

        list = findViewById(R.id.channelList);
        channelPanel = findViewById(R.id.channelPanel);
        infoPanel = findViewById(R.id.infoPanel);
        switchOsd = findViewById(R.id.switchOsd);
        switchLogo = findViewById(R.id.switchLogo);
        switchName = findViewById(R.id.switchName);
        switchState = findViewById(R.id.switchState);
        playerHost = findViewById(R.id.playerHost);
        playerView = findViewById(R.id.player);
        status = findViewById(R.id.status);
        nowTitle = findViewById(R.id.nowTitle);
        nowProgram = findViewById(R.id.nowProgram);
        nextProgram = findViewById(R.id.nextProgram);
        ((TextView) findViewById(R.id.modeTitle)).setText(PlaylistCatalog.title(mode));

        adapter = new ChannelAdapter(this, channels);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> {
            play(position, true);
            if (AppPrefs.DISPLAY_APP.equals(displayMode)) hideChannels();
        });
        list.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> p, View v, int pos, long id) { updateInfo(pos); }
            @Override public void onNothingSelected(android.widget.AdapterView<?> p) {}
        });
        list.setOnKeyListener((v, keyCode, event) -> {
            if (event.getAction() != KeyEvent.ACTION_DOWN || channels.isEmpty()) return false;
            int selected = list.getSelectedItemPosition();
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP && selected <= 0) {
                list.setSelection(channels.size() - 1);
                return true;
            }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN && selected >= channels.size() - 1) {
                list.setSelection(0);
                return true;
            }
            return false;
        });

        engine = new PlayerEngine(this, playerView, msg -> onPlaybackError(msg));

        applyDisplayMode();
        loader = new PlaylistLoader();
        epg = new EpgLoader();
        status.setText("M3U読み込み中…");
        loader.load(this, mode, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> loaded) {
                channels.clear();
                channels.addAll(loaded);
                adapter.notifyDataSetChanged();
                status.setText(channels.size() + " ch");
                if (!channels.isEmpty()) {
                    int start = Math.max(0, Math.min(channels.size() - 1, getIntent().getIntExtra("index", 0)));
                    list.setSelection(start);
                    play(start, true);
                    if (AppPrefs.DISPLAY_GUIDE.equals(displayMode)) list.requestFocus();
                    else playerHost.requestFocus();
                    epg.load(ChannelActivity.this, mode, channels, () -> {
                        adapter.notifyDataSetChanged();
                        updateInfo(current);
                    });
                }
            }
            @Override public void onError(String message) {
                status.setText("読込失敗");
                Toast.makeText(ChannelActivity.this, message, Toast.LENGTH_LONG).show();
            }
        });
    }

    private void applyDisplayMode() {
        infoPanel.setVisibility(View.GONE);
        channelPanel.setVisibility(AppPrefs.DISPLAY_GUIDE.equals(displayMode) ? View.VISIBLE : View.GONE);
    }

    private void showChannels() {
        if (AppPrefs.DISPLAY_FULLSCREEN.equals(displayMode)) return;
        channelPanel.setVisibility(View.VISIBLE);
        list.setSelection(Math.max(0, current));
        list.requestFocus();
    }

    private void hideChannels() {
        if (AppPrefs.DISPLAY_GUIDE.equals(displayMode)) return;
        channelPanel.setVisibility(View.GONE);
        playerHost.requestFocus();
    }

    private void play(int position, boolean resetRetry) {
        if (position < 0 || position >= channels.size()) return;
        current = position;
        if (resetRetry) youtubeRetryAttempted = -1;
        list.setItemChecked(position, true);
        Channel c = channels.get(position);
        showSwitchOsd(c, "接続中…", 4200);
        engine.play(c);
        updateInfo(position);
    }

    private void onPlaybackError(String message) {
        Channel c = current >= 0 && current < channels.size() ? channels.get(current) : null;
        if (c == null) return;
        if (PlaylistCatalog.MODE_YOUTUBE.equals(mode) && youtubeRetryAttempted != current) {
            youtubeRetryAttempted = current;
            showSwitchOsd(c, "YouTube LIVE URLを更新中…", 7000);
            refreshYoutubeChannel(c);
            return;
        }
        showSwitchOsd(c, "再生できません  (" + message + ")", 6500);
    }

    private void refreshYoutubeChannel(Channel old) {
        PlaylistLoader refresh = new PlaylistLoader();
        refresh.load(this, mode, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> fresh) {
                int match = findMatching(fresh, old);
                if (match >= 0 && current >= 0 && current < channels.size()) {
                    Channel updated = fresh.get(match);
                    channels.set(current, updated);
                    adapter.notifyDataSetChanged();
                    showSwitchOsd(updated, "再接続中…", 5000);
                    play(current, false);
                } else {
                    showSwitchOsd(old, "最新のYouTube LIVE URLを取得できません", 6500);
                }
                refresh.shutdown();
            }
            @Override public void onError(String message) {
                showSwitchOsd(old, "YouTube更新失敗", 6500);
                refresh.shutdown();
            }
        });
    }

    private int findMatching(List<Channel> list, Channel target) {
        for (int i = 0; i < list.size(); i++) {
            Channel c = list.get(i);
            if (!target.tvgId.isEmpty() && target.tvgId.equals(c.tvgId)) return i;
            if (target.name.equals(c.name) && target.source.equals(c.source)) return i;
        }
        return -1;
    }

    private void showSwitchOsd(Channel c, String state, long durationMs) {
        if (c == null) return;
        ui.removeCallbacks(hideOsd);
        switchName.setText((current >= 0 ? (current + 1) + "  " : "") + c.name);
        switchState.setText(state);
        LogoLoader.load(switchLogo, c.logo);
        switchOsd.setVisibility(View.VISIBLE);
        if (durationMs > 0) ui.postDelayed(hideOsd, durationMs);
    }

    private void updateInfo(int position) {
        if (position < 0 || position >= channels.size()) return;
        Channel c = channels.get(position);
        nowTitle.setText(c.name);
        nowProgram.setText(c.nowProgram.isEmpty() ? (c.group.isEmpty() ? "番組情報なし" : c.group) : c.nowProgram);
        nextProgram.setText(c.nextProgram.isEmpty() ? "" : "次: " + c.nextProgram);
    }

    private void switchBy(int delta) {
        if (channels.isEmpty()) return;
        int n = current < 0 ? 0 : (current + delta + channels.size()) % channels.size();
        play(n, true);
        list.setSelection(n);
    }

    private void changeVolume(int delta) {
        int v = Math.max(0, Math.min(100, AppPrefs.volume(this) + delta));
        AppPrefs.setVolume(this, v);
        engine.refreshVolume();
        Toast.makeText(this, "音量 " + v, Toast.LENGTH_SHORT).show();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_VOLUME_UP) { changeVolume(5); return true; }
        if (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) { changeVolume(-5); return true; }
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (infoPanel.getVisibility() == View.VISIBLE) { infoPanel.setVisibility(View.GONE); return true; }
            if (channelPanel.getVisibility() == View.VISIBLE && !AppPrefs.DISPLAY_GUIDE.equals(displayMode)) { hideChannels(); return true; }
            finish();
            return true;
        }

        if (list.hasFocus()) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { hideChannels(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
                int p = list.getSelectedItemPosition();
                if (p >= 0) play(p, true);
                if (AppPrefs.DISPLAY_APP.equals(displayMode)) hideChannels();
                return true;
            }
        } else {
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP) { switchBy(-1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) { switchBy(1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { showChannels(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                infoPanel.setVisibility(infoPanel.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE);
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        ui.removeCallbacksAndMessages(null);
        if (engine != null) engine.release();
        if (loader != null) loader.shutdown();
        if (epg != null) epg.shutdown();
    }
}
