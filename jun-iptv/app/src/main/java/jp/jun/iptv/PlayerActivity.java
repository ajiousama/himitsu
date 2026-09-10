package jp.jun.iptv;

import android.app.Activity;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.List;

public class PlayerActivity extends Activity {
    private final List<Channel> channels = new ArrayList<>();
    private PlaylistLoader loader;
    private EpgLoader epg;
    private PlayerEngine engine;
    private TextView title, program;
    private LinearLayout infoPanel;
    private String mode;
    private int current;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_player);
        mode = getIntent().getStringExtra("mode");
        if (mode == null) mode = PlaylistCatalog.MODE_TV;
        current = Math.max(0, getIntent().getIntExtra("index", 0));
        title = findViewById(R.id.title);
        program = findViewById(R.id.program);
        infoPanel = findViewById(R.id.infoPanel);
        PlayerView pv = findViewById(R.id.player);
        engine = new PlayerEngine(this, pv, msg -> Toast.makeText(this, "再生エラー: " + msg, Toast.LENGTH_SHORT).show());
        loader = new PlaylistLoader();
        epg = new EpgLoader();
        loader.load(mode, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> loaded) {
                channels.clear(); channels.addAll(loaded);
                if (channels.isEmpty()) return;
                if (current >= channels.size()) current = 0;
                play();
                epg.load(mode, channels, PlayerActivity.this::showInfo);
            }
            @Override public void onError(String message) { Toast.makeText(PlayerActivity.this, message, Toast.LENGTH_LONG).show(); }
        });
    }

    private void play() {
        if (channels.isEmpty()) return;
        engine.play(channels.get(current));
        showInfo();
    }

    private void showInfo() {
        if (channels.isEmpty()) return;
        Channel c = channels.get(current);
        title.setText(c.name);
        program.setText(c.nowProgram.isEmpty() ? c.group : c.nowProgram);
    }

    private void step(int d) {
        if (channels.isEmpty()) return;
        current = (current + d + channels.size()) % channels.size();
        play();
    }

    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_DPAD_UP) { step(-1); return true; }
        if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) { step(1); return true; }
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { finish(); return true; }
        if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
            infoPanel.setVisibility(infoPanel.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE); return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (engine != null) engine.release();
        if (loader != null) loader.shutdown();
        if (epg != null) epg.shutdown();
    }
}
