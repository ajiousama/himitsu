package jp.jun.iptv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.List;

public class ChannelActivity extends Activity {
    private final List<Channel> channels = new ArrayList<>();
    private PlaylistLoader loader;
    private EpgLoader epg;
    private ChannelAdapter adapter;
    private ListView list;
    private PlayerView playerView;
    private PlayerEngine engine;
    private TextView status, nowTitle, nowProgram, nextProgram;
    private String mode;
    private int current = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_channel);
        mode = getIntent().getStringExtra("mode");
        if (mode == null) mode = PlaylistCatalog.MODE_TV;

        list = findViewById(R.id.channelList);
        playerView = findViewById(R.id.player);
        status = findViewById(R.id.status);
        nowTitle = findViewById(R.id.nowTitle);
        nowProgram = findViewById(R.id.nowProgram);
        nextProgram = findViewById(R.id.nextProgram);
        ((TextView) findViewById(R.id.modeTitle)).setText(PlaylistCatalog.title(mode));

        adapter = new ChannelAdapter(this, channels);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> play(position));
        list.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(android.widget.AdapterView<?> p, android.view.View v, int pos, long id) { updateInfo(pos); }
            @Override public void onNothingSelected(android.widget.AdapterView<?> p) {}
        });

        engine = new PlayerEngine(this, playerView, msg -> Toast.makeText(this, "再生エラー: " + msg, Toast.LENGTH_SHORT).show());
        loader = new PlaylistLoader();
        epg = new EpgLoader();
        status.setText("M3U読み込み中…");
        loader.load(mode, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> loaded) {
                channels.clear();
                channels.addAll(loaded);
                adapter.notifyDataSetChanged();
                status.setText(channels.size() + " ch");
                if (!channels.isEmpty()) {
                    list.setSelection(0);
                    list.requestFocus();
                    play(0);
                    epg.load(mode, channels, () -> {
                        adapter.notifyDataSetChanged();
                        updateInfo(current);
                    });
                }
            }
            @Override public void onError(String message) { status.setText("読込失敗"); Toast.makeText(ChannelActivity.this, message, Toast.LENGTH_LONG).show(); }
        });
    }

    private void play(int position) {
        if (position < 0 || position >= channels.size()) return;
        current = position;
        list.setItemChecked(position, true);
        engine.play(channels.get(position));
        updateInfo(position);
    }

    private void updateInfo(int position) {
        if (position < 0 || position >= channels.size()) return;
        Channel c = channels.get(position);
        nowTitle.setText(c.name);
        nowProgram.setText(c.nowProgram.isEmpty() ? "番組情報なし" : c.nowProgram);
        nextProgram.setText(c.nextProgram.isEmpty() ? "" : "次: " + c.nextProgram);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (playerView.hasFocus()) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP) { switchBy(-1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) { switchBy(1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { list.requestFocus(); list.setSelection(Math.max(0, current)); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) { openFullscreen(); return true; }
        } else if (list.hasFocus() && keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
            playerView.requestFocus(); return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    private void switchBy(int delta) {
        if (channels.isEmpty()) return;
        int n = current < 0 ? 0 : (current + delta + channels.size()) % channels.size();
        play(n);
        list.setSelection(n);
    }

    private void openFullscreen() {
        if (current < 0) return;
        Intent i = new Intent(this, PlayerActivity.class);
        i.putExtra("mode", mode);
        i.putExtra("index", current);
        startActivity(i);
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (engine != null) engine.release();
        if (loader != null) loader.shutdown();
        if (epg != null) epg.shutdown();
    }
}
