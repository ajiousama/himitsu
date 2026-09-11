package jp.jun.iptv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ChannelActivity extends Activity {
    private final List<Channel> channels = new ArrayList<>();
    private PlaylistLoader loader;
    private EpgLoader epg;
    private ChannelAdapter adapter;
    private ListView list;
    private LinearLayout channelPanel, infoPanel;
    private FrameLayout playerHost;
    private PlayerView playerView;
    private WebView youtubeView;
    private PlayerEngine engine;
    private TextView status, nowTitle, nowProgram, nextProgram;
    private String mode;
    private String displayMode;
    private int current = -1;

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
        playerHost = findViewById(R.id.playerHost);
        playerView = findViewById(R.id.player);
        youtubeView = findViewById(R.id.youtubeView);
        status = findViewById(R.id.status);
        nowTitle = findViewById(R.id.nowTitle);
        nowProgram = findViewById(R.id.nowProgram);
        nextProgram = findViewById(R.id.nextProgram);
        ((TextView) findViewById(R.id.modeTitle)).setText(PlaylistCatalog.title(mode));

        setupYoutube();
        adapter = new ChannelAdapter(this, channels);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> {
            play(position);
            if (AppPrefs.DISPLAY_APP.equals(displayMode)) hideChannels();
        });
        list.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> p, View v, int pos, long id) { updateInfo(pos); }
            @Override public void onNothingSelected(android.widget.AdapterView<?> p) {}
        });

        engine = new PlayerEngine(this, playerView, msg -> {
            Channel c = current >= 0 && current < channels.size() ? channels.get(current) : null;
            if (c != null && tryYoutube(c)) return;
            Toast.makeText(this, "再生エラー: " + msg, Toast.LENGTH_SHORT).show();
        });

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
                    play(start);
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

    private void setupYoutube() {
        WebSettings s = youtubeView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        youtubeView.setWebChromeClient(new WebChromeClient());
        youtubeView.setWebViewClient(new WebViewClient());
        youtubeView.setFocusable(false);
    }

    private void applyDisplayMode() {
        infoPanel.setVisibility(View.GONE);
        if (AppPrefs.DISPLAY_GUIDE.equals(displayMode)) {
            channelPanel.setVisibility(View.VISIBLE);
        } else {
            channelPanel.setVisibility(View.GONE);
        }
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

    private void play(int position) {
        if (position < 0 || position >= channels.size()) return;
        current = position;
        list.setItemChecked(position, true);
        youtubeView.setVisibility(View.GONE);
        playerView.setVisibility(View.VISIBLE);
        Channel c = channels.get(position);
        if (PlaylistCatalog.MODE_YOUTUBE.equals(mode) && tryYoutube(c)) {
            updateInfo(position);
            return;
        }
        engine.play(c);
        updateInfo(position);
    }

    private boolean tryYoutube(Channel c) {
        String id = youtubeId(c.url);
        if (id == null) return false;
        engine.getPlayer().stop();
        playerView.setVisibility(View.GONE);
        youtubeView.setVisibility(View.VISIBLE);
        String html = "<html><body style='margin:0;background:#000;overflow:hidden'>" +
            "<iframe width='100%' height='100%' src='https://www.youtube.com/embed/" + id +
            "?autoplay=1&controls=1&playsinline=1' frameborder='0' allow='autoplay; encrypted-media; picture-in-picture' allowfullscreen></iframe>" +
            "</body></html>";
        youtubeView.loadDataWithBaseURL("https://www.youtube.com", html, "text/html", "UTF-8", null);
        playerHost.requestFocus();
        return true;
    }

    private String youtubeId(String url) {
        if (url == null) return null;
        String[] regex = {
            "[?&]v=([A-Za-z0-9_-]{11})",
            "youtu\\.be/([A-Za-z0-9_-]{11})",
            "youtube\\.com/(?:live|embed)/([A-Za-z0-9_-]{11})",
            "/id/([A-Za-z0-9_-]{11})(?:[./])"
        };
        for (String r : regex) {
            Matcher m = Pattern.compile(r).matcher(url);
            if (m.find()) return m.group(1);
        }
        return null;
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
        play(n);
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
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (infoPanel.getVisibility() == View.VISIBLE) { infoPanel.setVisibility(View.GONE); return true; }
            if (channelPanel.getVisibility() == View.VISIBLE && !AppPrefs.DISPLAY_GUIDE.equals(displayMode)) { hideChannels(); return true; }
            finish(); return true;
        }

        if (list.hasFocus()) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { hideChannels(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
                int p = list.getSelectedItemPosition();
                if (p >= 0) play(p);
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
        if (youtubeView != null) youtubeView.destroy();
        if (engine != null) engine.release();
        if (loader != null) loader.shutdown();
        if (epg != null) epg.shutdown();
    }
}
