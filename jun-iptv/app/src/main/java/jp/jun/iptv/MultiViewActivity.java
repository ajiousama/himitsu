package jp.jun.iptv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.KeyEvent;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class MultiViewActivity extends Activity {
    private final List<Channel> channels = new ArrayList<>();
    private final PlayerEngine[] engines = new PlayerEngine[4];
    private final FrameLayout[] tiles = new FrameLayout[4];
    private final TextView[] labels = new TextView[4];
    private final int[] slotChannelIndex = {-1, -1, -1, -1};
    private PlaylistLoader loader;
    private GridLayout grid;
    private int focusedSlot = 0;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_multiview);
        grid = findViewById(R.id.grid);
        buildTiles();
        loader = new PlaylistLoader();
        loader.load(PlaylistCatalog.MODE_GAMBLE, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> loaded) {
                channels.clear(); channels.addAll(loaded);
                if (channels.isEmpty()) {
                    Toast.makeText(MultiViewActivity.this, "公営競技M3Uが空です", Toast.LENGTH_LONG).show();
                    return;
                }
                chooseInitialChannels();
                for (int i = 0; i < 4; i++) playSlot(i);
                tiles[0].requestFocus();
            }
            @Override public void onError(String message) {
                Toast.makeText(MultiViewActivity.this, "M3U読込失敗: " + message, Toast.LENGTH_LONG).show();
            }
        });
    }

    private void buildTiles() {
        for (int i = 0; i < 4; i++) {
            final int slot = i;
            FrameLayout tile = new FrameLayout(this);
            tile.setFocusable(true);
            tile.setClickable(true);
            tile.setBackgroundResource(R.drawable.tile_background);
            tile.setPadding(dp(3), dp(3), dp(3), dp(3));

            PlayerView pv = new PlayerView(this);
            pv.setUseController(false);
            tile.addView(pv, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

            TextView label = new TextView(this);
            label.setTextColor(android.graphics.Color.WHITE);
            label.setTextSize(17);
            label.setGravity(Gravity.CENTER_VERTICAL);
            label.setPadding(dp(12), dp(8), dp(12), dp(8));
            label.setBackgroundColor(0xA0000000);
            FrameLayout.LayoutParams lpLabel = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM);
            tile.addView(label, lpLabel);

            GridLayout.LayoutParams lp = new GridLayout.LayoutParams();
            lp.width = 0;
            lp.height = 0;
            lp.rowSpec = GridLayout.spec(i / 2, 1f);
            lp.columnSpec = GridLayout.spec(i % 2, 1f);
            lp.setMargins(dp(2), dp(2), dp(2), dp(2));
            grid.addView(tile, lp);

            engines[i] = new PlayerEngine(this, pv, msg -> {
                if (slot == focusedSlot) Toast.makeText(this, "再生エラー: " + msg, Toast.LENGTH_SHORT).show();
            });
            engines[i].setAudible(false);
            tiles[i] = tile;
            labels[i] = label;

            tile.setOnFocusChangeListener((v, hasFocus) -> {
                if (hasFocus) selectAudio(slot);
            });
            tile.setOnClickListener(v -> openFullscreen(slot));
            tile.setOnLongClickListener(v -> {
                openPicker(slot);
                return true;
            });
            tile.setOnKeyListener((v, keyCode, event) -> {
                if (event.getAction() != KeyEvent.ACTION_DOWN) return false;
                if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) {
                    openPicker(slot);
                    return true;
                }
                return false;
            });
        }
    }

    private void chooseInitialChannels() {
        Set<Integer> used = new HashSet<>();
        slotChannelIndex[0] = findKind("keirin", used);
        slotChannelIndex[1] = findKind("boat", used);
        slotChannelIndex[2] = findKind("keiba", used);
        slotChannelIndex[3] = findKind("auto", used);
        for (int s = 0; s < 4; s++) {
            if (slotChannelIndex[s] < 0) {
                for (int i = 0; i < channels.size(); i++) {
                    if (!used.contains(i)) { slotChannelIndex[s] = i; used.add(i); break; }
                }
            }
        }
    }

    private int findKind(String kind, Set<Integer> used) {
        for (int i = 0; i < channels.size(); i++) {
            if (used.contains(i)) continue;
            Channel c = channels.get(i);
            String s = (c.group + " " + c.name).toLowerCase(Locale.ROOT);
            boolean ok;
            switch (kind) {
                case "keirin": ok = s.contains("競輪") || s.contains("keirin"); break;
                case "boat": ok = s.contains("boat") || s.contains("ボート") || s.contains("競艇"); break;
                case "keiba": ok = s.contains("競馬") || s.contains("jra") || s.contains("gch") || s.contains("green"); break;
                default: ok = s.contains("オート") || s.contains("autorace"); break;
            }
            if (ok) { used.add(i); return i; }
        }
        return -1;
    }

    private void playSlot(int slot) {
        int idx = slotChannelIndex[slot];
        if (idx < 0 || idx >= channels.size()) {
            labels[slot].setText("未設定");
            return;
        }
        Channel c = channels.get(idx);
        labels[slot].setText(c.name);
        engines[slot].play(c);
        engines[slot].setAudible(slot == focusedSlot);
    }

    private void selectAudio(int slot) {
        focusedSlot = slot;
        for (int i = 0; i < 4; i++) engines[i].setAudible(i == slot);
    }

    private void openPicker(int slot) {
        if (channels.isEmpty()) return;
        String[] names = new String[channels.size()];
        for (int i = 0; i < channels.size(); i++) {
            Channel c = channels.get(i);
            names[i] = (c.group.isEmpty() ? "" : "[" + c.group + "] ") + c.name;
        }
        new AlertDialog.Builder(this)
            .setTitle("画面" + (slot + 1) + " のチャンネル")
            .setSingleChoiceItems(names, slotChannelIndex[slot], (d, which) -> {
                slotChannelIndex[slot] = which;
                playSlot(slot);
                d.dismiss();
                tiles[slot].requestFocus();
            })
            .setNegativeButton("閉じる", null)
            .show();
    }

    private void openFullscreen(int slot) {
        int idx = slotChannelIndex[slot];
        if (idx < 0) return;
        Intent i = new Intent(this, PlayerActivity.class);
        i.putExtra("mode", PlaylistCatalog.MODE_GAMBLE);
        i.putExtra("index", idx);
        startActivity(i);
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (loader != null) loader.shutdown();
        for (PlayerEngine e : engines) if (e != null) e.release();
    }
}
