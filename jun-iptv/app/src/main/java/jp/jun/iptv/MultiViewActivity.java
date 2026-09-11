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
    private PlayerEngine[] engines;
    private FrameLayout[] tiles;
    private TextView[] labels;
    private int[] slotChannelIndex;
    private PlaylistLoader loader;
    private GridLayout grid;
    private String mode;
    private int focusedSlot = 0;
    private int count;
    private int cols;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_multiview);
        mode = getIntent().getStringExtra("mode");
        if (mode == null) mode = PlaylistCatalog.MODE_GAMBLE;
        count = AppPrefs.multiCount(this);
        cols = count == 4 ? 2 : (count == 6 ? 3 : 4);
        int rows = (count + cols - 1) / cols;

        engines = new PlayerEngine[count];
        tiles = new FrameLayout[count];
        labels = new TextView[count];
        slotChannelIndex = new int[count];
        for (int i = 0; i < count; i++) slotChannelIndex[i] = -1;

        grid = findViewById(R.id.grid);
        grid.setColumnCount(cols);
        grid.setRowCount(rows);
        ((TextView) findViewById(R.id.multiTitle)).setText(PlaylistCatalog.title(mode) + "  " + count + "画面　　OK：操作");
        buildTiles(rows);

        loader = new PlaylistLoader();
        loader.load(this, mode, new PlaylistLoader.Callback() {
            @Override public void onLoaded(List<Channel> loaded) {
                channels.clear();
                channels.addAll(loaded);
                if (channels.isEmpty()) {
                    Toast.makeText(MultiViewActivity.this, "M3Uが空です", Toast.LENGTH_LONG).show();
                    return;
                }
                chooseInitialChannels();
                for (int i = 0; i < count; i++) playSlot(i);
                tiles[0].requestFocus();
            }
            @Override public void onError(String message) {
                Toast.makeText(MultiViewActivity.this, "M3U読込失敗: " + message, Toast.LENGTH_LONG).show();
            }
        });
    }

    private void buildTiles(int rows) {
        for (int i = 0; i < count; i++) {
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
            label.setTextSize(count >= 8 ? 13 : 16);
            label.setGravity(Gravity.CENTER_VERTICAL);
            label.setSingleLine(true);
            label.setPadding(dp(10), dp(6), dp(10), dp(6));
            label.setBackgroundColor(0xB0000000);
            tile.addView(label, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM));

            GridLayout.LayoutParams lp = new GridLayout.LayoutParams();
            lp.width = 0;
            lp.height = 0;
            lp.rowSpec = GridLayout.spec(i / cols, 1f);
            lp.columnSpec = GridLayout.spec(i % cols, 1f);
            lp.setMargins(dp(2), dp(2), dp(2), dp(2));
            grid.addView(tile, lp);

            engines[i] = new PlayerEngine(this, pv, msg -> {
                if (slot == focusedSlot) Toast.makeText(this, "再生エラー: " + msg, Toast.LENGTH_SHORT).show();
            });
            engines[i].setAudible(false);
            tiles[i] = tile;
            labels[i] = label;

            tile.setOnFocusChangeListener((v, hasFocus) -> { if (hasFocus) selectAudio(slot); });
            tile.setOnClickListener(v -> openSlotMenu(slot));
        }
    }

    private void chooseInitialChannels() {
        Set<Integer> used = new HashSet<>();
        if (PlaylistCatalog.MODE_GAMBLE.equals(mode) && count >= 4) {
            slotChannelIndex[0] = findKind("keirin", used);
            slotChannelIndex[1] = findKind("boat", used);
            slotChannelIndex[2] = findKind("keiba", used);
            slotChannelIndex[3] = findKind("auto", used);
        }
        for (int s = 0; s < count; s++) {
            if (slotChannelIndex[s] < 0) {
                for (int i = 0; i < channels.size(); i++) {
                    if (!used.contains(i)) {
                        slotChannelIndex[s] = i;
                        used.add(i);
                        break;
                    }
                }
            }
        }
    }

    private int findKind(String kind, Set<Integer> used) {
        for (int i = 0; i < channels.size(); i++) {
            if (used.contains(i)) continue;
            String s = (channels.get(i).group + " " + channels.get(i).name).toLowerCase(Locale.ROOT);
            boolean ok;
            switch (kind) {
                case "keirin": ok = s.contains("競輪") || s.contains("keirin"); break;
                case "boat": ok = s.contains("boat") || s.contains("ボート") || s.contains("競艇"); break;
                case "keiba": ok = s.contains("競馬") || s.contains("jra") || s.contains("gch") || s.contains("green"); break;
                default: ok = s.contains("オート") || s.contains("autorace"); break;
            }
            if (ok) {
                used.add(i);
                return i;
            }
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
        labels[slot].setText((slot + 1) + "  " + c.name);
        engines[slot].play(c);
        engines[slot].setAudible(slot == focusedSlot);
    }

    private void selectAudio(int slot) {
        focusedSlot = slot;
        for (int i = 0; i < count; i++) engines[i].setAudible(i == slot);
    }

    private void openSlotMenu(int slot) {
        if (channels.isEmpty()) return;
        String channelName = slotChannelIndex[slot] >= 0 && slotChannelIndex[slot] < channels.size()
            ? channels.get(slotChannelIndex[slot]).name : "未設定";
        new AlertDialog.Builder(this)
            .setTitle("画面" + (slot + 1) + "：" + channelName)
            .setItems(new String[]{"全画面で見る", "チャンネルを変更"}, (d, which) -> {
                if (which == 0) openFullscreen(slot);
                else openPicker(slot);
            })
            .setNegativeButton("閉じる", null)
            .show();
    }

    private void openPicker(int slot) {
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
        Intent i = new Intent(this, ChannelActivity.class);
        i.putExtra("mode", mode);
        i.putExtra("index", idx);
        i.putExtra("forceFullscreen", true);
        startActivity(i);
    }

    private void changeVolume(int delta) {
        int v = Math.max(0, Math.min(100, AppPrefs.volume(this) + delta));
        AppPrefs.setVolume(this, v);
        for (PlayerEngine e : engines) if (e != null) e.refreshVolume();
        Toast.makeText(this, "音量 " + v, Toast.LENGTH_SHORT).show();
    }

    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_VOLUME_UP) { changeVolume(5); return true; }
        if (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) { changeVolume(-5); return true; }
        return super.onKeyDown(keyCode, event);
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (loader != null) loader.shutdown();
        if (engines != null) for (PlayerEngine e : engines) if (e != null) e.release();
    }
}
