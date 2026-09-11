package jp.jun.iptv;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.AdapterView;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService bg = Executors.newSingleThreadExecutor();
    private final ArrayList<Channel> all = new ArrayList<>();
    private final ArrayList<Channel> visible = new ArrayList<>();

    private FrameLayout root, playerHost;
    private LinearLayout stage, channelPanel, osd, infoPanel, optionPanel, groupPanel;
    private ListView channelList, groupList, optionList;
    private TextView status, osdName, osdState, infoName, infoNow, infoNext, groupTitle;
    private ImageView osdLogo;
    private PlayerView playerView;
    private ChannelAdapter adapter;
    private PlayerEngine engine;
    private EpgLoader epgLoader;

    private int current = -1;
    private boolean guideMode;
    private boolean retryUsed = false;
    private final Runnable hideOsd = () -> osd.setVisibility(View.GONE);

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        buildUi();
        engine = new PlayerEngine(this, playerView, new PlayerEngine.Listener() {
            @Override public void onReady() { updateOsdState("再生中", 1500); retryUsed = false; }
            @Override public void onBuffering() { updateOsdState("接続中…", 0); }
            @Override public void onError(String m) {
                if (!retryUsed) {
                    retryUsed = true;
                    updateOsdState("再接続中…", 0);
                    ui.postDelayed(() -> engine.retry(), 1200);
                } else updateOsdState("再生できません  " + m, 6500);
            }
        });
        guideMode = Prefs.guideMode(this);
        applyDisplayMode();
        loadPlaylist(true);
    }

    private void buildUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        setContentView(root);

        stage = new LinearLayout(this);
        stage.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(stage, new FrameLayout.LayoutParams(-1, -1));

        channelPanel = panel(Color.rgb(20, 24, 31));
        TextView title = text("チャンネル", 24, Color.WHITE, true);
        title.setPadding(dp(18), dp(14), dp(12), dp(4));
        channelPanel.addView(title, new LinearLayout.LayoutParams(-1, -2));
        status = text("読み込み中…", 13, Color.rgb(185, 190, 198), false);
        status.setPadding(dp(18), 0, dp(12), dp(8));
        channelPanel.addView(status, new LinearLayout.LayoutParams(-1, -2));
        channelList = new ListView(this);
        channelList.setDividerHeight(1);
        channelList.setSelector(android.R.color.darker_gray);
        adapter = new ChannelAdapter(this, visible);
        channelList.setAdapter(adapter);
        channelPanel.addView(channelList, new LinearLayout.LayoutParams(-1, 0, 1f));
        TextView hint = text("← グループ   OK 選局   → 閉じる", 12, Color.rgb(160, 165, 175), false);
        hint.setPadding(dp(12), dp(8), dp(12), dp(10));
        channelPanel.addView(hint, new LinearLayout.LayoutParams(-1, -2));
        stage.addView(channelPanel, new LinearLayout.LayoutParams(dp(430), -1));

        playerHost = new FrameLayout(this);
        playerHost.setFocusable(true);
        playerHost.setFocusableInTouchMode(true);
        playerView = new PlayerView(this);
        playerHost.addView(playerView, new FrameLayout.LayoutParams(-1, -1));
        stage.addView(playerHost, new LinearLayout.LayoutParams(0, -1, 1f));

        buildOsd();
        buildInfoPanel();
        buildGroupPanel();
        buildOptions();

        channelList.setOnItemClickListener((p, v, pos, id) -> {
            playVisible(pos);
            if (!guideMode) hideChannelPanel();
        });
        channelList.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> p, View v, int pos, long id) {
                if (pos >= 0 && pos < visible.size()) showInfoFor(visible.get(pos), false);
            }
            @Override public void onNothingSelected(AdapterView<?> p) {}
        });
        channelList.setOnKeyListener((v, keyCode, event) -> {
            if (event.getAction() != KeyEvent.ACTION_DOWN || visible.isEmpty()) return false;
            int s = channelList.getSelectedItemPosition();
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP && s <= 0) { channelList.setSelection(visible.size() - 1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN && s >= visible.size() - 1) { channelList.setSelection(0); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { showGroups(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { if (!guideMode) hideChannelPanel(); else playerHost.requestFocus(); return true; }
            return false;
        });
    }

    private void buildOsd() {
        osd = new LinearLayout(this);
        osd.setOrientation(LinearLayout.HORIZONTAL);
        osd.setGravity(Gravity.CENTER_VERTICAL);
        osd.setPadding(dp(16), dp(12), dp(20), dp(12));
        osd.setBackgroundColor(Color.argb(225, 18, 21, 28));
        osd.setVisibility(View.GONE);
        osdLogo = new ImageView(this);
        osdLogo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        osd.addView(osdLogo, new LinearLayout.LayoutParams(dp(72), dp(54)));
        LinearLayout t = new LinearLayout(this);
        t.setOrientation(LinearLayout.VERTICAL);
        t.setPadding(dp(14),0,0,0);
        osdName = text("", 23, Color.WHITE, true);
        osdState = text("接続中…", 14, Color.rgb(190,195,205), false);
        t.addView(osdName); t.addView(osdState);
        osd.addView(t);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-2, -2, Gravity.START | Gravity.BOTTOM);
        lp.leftMargin = dp(28); lp.bottomMargin = dp(30);
        root.addView(osd, lp);
    }

    private void buildInfoPanel() {
        infoPanel = panel(Color.argb(238, 13, 16, 21));
        infoPanel.setPadding(dp(28), dp(18), dp(28), dp(18));
        infoName = text("", 24, Color.WHITE, true);
        infoNow = text("", 18, Color.WHITE, false);
        infoNext = text("", 15, Color.rgb(185,190,198), false);
        infoPanel.addView(infoName); infoPanel.addView(infoNow); infoPanel.addView(infoNext);
        infoPanel.setVisibility(View.GONE);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(infoPanel, lp);
    }

    private void buildGroupPanel() {
        groupPanel = panel(Color.rgb(16, 19, 25));
        groupPanel.setVisibility(View.GONE);
        groupTitle = text("グループ", 23, Color.WHITE, true);
        groupTitle.setPadding(dp(18), dp(16), dp(12), dp(10));
        groupPanel.addView(groupTitle);
        groupList = new ListView(this);
        groupList.setDividerHeight(1);
        groupPanel.addView(groupList, new LinearLayout.LayoutParams(-1,0,1f));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(dp(330), -1, Gravity.START);
        root.addView(groupPanel, lp);
        groupList.setOnItemClickListener((p,v,pos,id) -> selectGroup((String)p.getItemAtPosition(pos)));
    }

    private void buildOptions() {
        optionPanel = panel(Color.rgb(16, 19, 25));
        optionPanel.setVisibility(View.GONE);
        TextView t = text("チャンネル設定", 23, Color.WHITE, true);
        t.setPadding(dp(18), dp(16), dp(12), dp(10));
        optionPanel.addView(t);
        optionList = new ListView(this);
        String[] opts = {"お気に入り追加/解除", "再接続", "映像サイズ切替", "番組表モード切替", "M3U / EPG 設定", "再読み込み"};
        optionList.setAdapter(new android.widget.ArrayAdapter<>(this, android.R.layout.simple_list_item_1, opts));
        optionPanel.addView(optionList, new LinearLayout.LayoutParams(-1,0,1f));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(dp(360), -1, Gravity.END);
        root.addView(optionPanel, lp);
        optionList.setOnItemClickListener((p,v,pos,id) -> runOption(pos));
    }

    private LinearLayout panel(int color) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setBackgroundColor(color);
        return l;
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView v = new TextView(this);
        v.setText(s); v.setTextSize(sp); v.setTextColor(color);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return v;
    }

    private void loadPlaylist(boolean autoplay) {
        status.setText("M3U読み込み中…");
        bg.submit(() -> {
            try {
                List<Channel> parsed = M3uParser.parse(Net.text(Prefs.m3u(this)));
                ui.post(() -> {
                    all.clear(); all.addAll(parsed);
                    rebuildGroups();
                    applyGroup("すべて");
                    status.setText(all.size() + " ch");
                    if (!all.isEmpty() && autoplay) {
                        int global = Math.max(0, Math.min(all.size()-1, Prefs.lastIndex(this)));
                        Channel target = all.get(global);
                        int vp = visible.indexOf(target);
                        if (vp < 0) vp = 0;
                        playVisible(vp);
                    }
                    loadEpg();
                });
            } catch (Exception e) {
                ui.post(() -> {
                    status.setText("M3U読込失敗");
                    Toast.makeText(this, "M3U: " + e.getMessage(), Toast.LENGTH_LONG).show();
                });
            }
        });
    }

    private void loadEpg() {
        String url = Prefs.epg(this);
        if (url == null || url.isBlank()) return;
        if (epgLoader != null) epgLoader.shutdown();
        epgLoader = new EpgLoader();
        epgLoader.load(url, all, ui, () -> {
            adapter.notifyDataSetChanged();
            status.setText(all.size() + " ch  /  EPG");
        });
    }

    private void rebuildGroups() {
        ArrayList<String> rows = new ArrayList<>();
        rows.add("すべて");
        rows.add("★ お気に入り");
        rows.add("🔎 検索");
        rows.add("⚙ 設定");
        Set<String> groups = new LinkedHashSet<>();
        for (Channel c : all) if (!c.group.isEmpty()) groups.add(c.group);
        rows.addAll(groups);
        groupList.setAdapter(new android.widget.ArrayAdapter<>(this, android.R.layout.simple_list_item_1, rows));
    }

    private void selectGroup(String row) {
        if ("🔎 検索".equals(row)) { showSearch(); return; }
        if ("⚙ 設定".equals(row)) { showSourceSettings(); return; }
        applyGroup(row);
        groupPanel.setVisibility(View.GONE);
        showChannelPanel();
    }

    private void applyGroup(String group) {
        Channel playing = current >= 0 && current < visible.size() ? visible.get(current) : null;
        visible.clear();
        if ("すべて".equals(group)) visible.addAll(all);
        else if ("★ お気に入り".equals(group)) {
            for (Channel c : all) if (Prefs.favorite(this, channelKey(c))) visible.add(c);
        } else {
            for (Channel c : all) if (group.equals(c.group)) visible.add(c);
        }
        current = playing == null ? -1 : visible.indexOf(playing);
        if (current < 0 && !visible.isEmpty()) current = 0;
        adapter.notifyDataSetChanged();
        if (current >= 0) channelList.setSelection(current);
        status.setText(visible.size() + " / " + all.size() + " ch");
    }

    private void showSearch() {
        EditText q = new EditText(this);
        q.setSingleLine(true);
        q.setHint("チャンネル名 / 番組名");
        new AlertDialog.Builder(this).setTitle("検索").setView(q)
            .setPositiveButton("検索", (d,w) -> {
                String s = q.getText().toString().trim().toLowerCase(Locale.ROOT);
                visible.clear();
                for (Channel c : all) {
                    String h = (c.name + " " + c.nowTitle + " " + c.nextTitle).toLowerCase(Locale.ROOT);
                    if (h.contains(s)) visible.add(c);
                }
                current = visible.isEmpty() ? -1 : 0;
                adapter.notifyDataSetChanged();
                groupPanel.setVisibility(View.GONE);
                showChannelPanel();
            }).setNegativeButton("閉じる", null).show();
    }

    private void showSourceSettings() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(20), dp(16), dp(20), dp(12));
        EditText m = new EditText(this); m.setSingleLine(true); m.setHint("M3U URL"); m.setText(Prefs.m3u(this));
        EditText e = new EditText(this); e.setSingleLine(true); e.setHint("EPG XMLTV URL"); e.setText(Prefs.epg(this));
        m.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        box.addView(m); box.addView(e);
        new AlertDialog.Builder(this).setTitle("M3U / EPG").setView(box)
            .setPositiveButton("保存して再読込", (d,w) -> {
                Prefs.saveSource(this, m.getText().toString().trim(), e.getText().toString().trim());
                groupPanel.setVisibility(View.GONE);
                loadPlaylist(true);
            }).setNegativeButton("閉じる", null).show();
    }

    private void playVisible(int pos) {
        if (visible.isEmpty()) return;
        pos = (pos % visible.size() + visible.size()) % visible.size();
        current = pos;
        Channel c = visible.get(pos);
        int global = all.indexOf(c);
        if (global >= 0) Prefs.setLastIndex(this, global);
        retryUsed = false;
        channelList.setItemChecked(pos, true);
        showOsd(c, "接続中…");
        engine.play(c.url);
        showInfoFor(c, false);
    }

    private void switchBy(int delta) {
        if (visible.isEmpty()) return;
        int n = current < 0 ? 0 : (current + delta + visible.size()) % visible.size();
        playVisible(n);
        channelList.setSelection(n);
    }

    private void showOsd(Channel c, String state) {
        ui.removeCallbacks(hideOsd);
        osdName.setText((current + 1) + "  " + c.name);
        osdState.setText(state);
        LogoLoader.load(osdLogo, c.logo);
        osd.setVisibility(View.VISIBLE);
    }

    private void updateOsdState(String s, long hideAfter) {
        osdState.setText(s);
        osd.setVisibility(View.VISIBLE);
        ui.removeCallbacks(hideOsd);
        if (hideAfter > 0) ui.postDelayed(hideOsd, hideAfter);
    }

    private void showInfoFor(Channel c, boolean visibleNow) {
        if (c == null) return;
        infoName.setText(c.name);
        infoNow.setText(c.nowTitle.isEmpty() ? "番組情報なし" : "現在: " + c.nowTitle);
        infoNext.setText(c.nextTitle.isEmpty() ? "" : "次: " + c.nextTitle);
        if (visibleNow) infoPanel.setVisibility(View.VISIBLE);
    }

    private void showChannelPanel() {
        channelPanel.setVisibility(View.VISIBLE);
        if (current >= 0 && current < visible.size()) channelList.setSelection(current);
        channelList.requestFocus();
    }

    private void hideChannelPanel() {
        if (guideMode) { playerHost.requestFocus(); return; }
        channelPanel.setVisibility(View.GONE);
        playerHost.requestFocus();
    }

    private void showGroups() {
        rebuildGroups();
        groupPanel.setVisibility(View.VISIBLE);
        groupList.requestFocus();
    }

    private void showOptions() {
        optionPanel.setVisibility(View.VISIBLE);
        optionList.requestFocus();
    }

    private void runOption(int pos) {
        if (pos == 0) {
            Channel c = current >= 0 && current < visible.size() ? visible.get(current) : null;
            if (c != null) {
                Prefs.toggleFavorite(this, channelKey(c));
                Toast.makeText(this, Prefs.favorite(this, channelKey(c)) ? "お気に入りに追加" : "お気に入りから解除", Toast.LENGTH_SHORT).show();
            }
        } else if (pos == 1) {
            engine.retry();
            updateOsdState("再接続中…", 0);
        } else if (pos == 2) {
            engine.toggleAspect();
            Toast.makeText(this, "映像サイズを切り替えました", Toast.LENGTH_SHORT).show();
        } else if (pos == 3) {
            guideMode = !guideMode;
            Prefs.setGuideMode(this, guideMode);
            applyDisplayMode();
        } else if (pos == 4) {
            showSourceSettings();
        } else if (pos == 5) {
            loadPlaylist(true);
        }
        optionPanel.setVisibility(View.GONE);
        playerHost.requestFocus();
    }

    private void applyDisplayMode() {
        LinearLayout.LayoutParams cp = (LinearLayout.LayoutParams) channelPanel.getLayoutParams();
        if (cp != null) {
            cp.width = guideMode ? dp(430) : 0;
            channelPanel.setLayoutParams(cp);
        }
        channelPanel.setVisibility(guideMode ? View.VISIBLE : View.GONE);
        if (guideMode) channelList.requestFocus(); else playerHost.requestFocus();
    }

    private String channelKey(Channel c) {
        return !c.tvgId.isEmpty() ? c.tvgId : c.name + "|" + c.url;
    }

    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (event.getAction() != KeyEvent.ACTION_DOWN) return super.onKeyDown(keyCode, event);

        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (optionPanel.getVisibility() == View.VISIBLE) { optionPanel.setVisibility(View.GONE); playerHost.requestFocus(); return true; }
            if (groupPanel.getVisibility() == View.VISIBLE) { groupPanel.setVisibility(View.GONE); showChannelPanel(); return true; }
            if (infoPanel.getVisibility() == View.VISIBLE) { infoPanel.setVisibility(View.GONE); playerHost.requestFocus(); return true; }
            if (channelPanel.getVisibility() == View.VISIBLE && !guideMode) { hideChannelPanel(); return true; }
            finish(); return true;
        }

        if (groupPanel.getVisibility() == View.VISIBLE || optionPanel.getVisibility() == View.VISIBLE) {
            return super.onKeyDown(keyCode, event);
        }

        if (channelList.hasFocus()) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { showGroups(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { if (!guideMode) hideChannelPanel(); else playerHost.requestFocus(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
                int p = channelList.getSelectedItemPosition();
                if (p >= 0) playVisible(p);
                if (!guideMode) hideChannelPanel();
                return true;
            }
        } else {
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP) { switchBy(-1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) { switchBy(1); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) { showChannelPanel(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) { showOptions(); return true; }
            if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
                Channel c = current >= 0 && current < visible.size() ? visible.get(current) : null;
                showInfoFor(c, true);
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        ui.removeCallbacksAndMessages(null);
        bg.shutdownNow();
        if (epgLoader != null) epgLoader.shutdown();
        if (engine != null) engine.release();
    }

    private int dp(int v) { return (int)(v * getResources().getDisplayMetrics().density + .5f); }
}
