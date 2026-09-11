package jp.jun.iptv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

public class SettingsActivity extends Activity {
    private Button displayButton, multiButton, volumeButton, addSourceButton, manageSourceButton, tverButton;
    private TextView help;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        displayButton = findViewById(R.id.displayModeButton);
        multiButton = findViewById(R.id.multiViewButton);
        volumeButton = findViewById(R.id.volumeButton);
        addSourceButton = findViewById(R.id.addSourceButton);
        manageSourceButton = findViewById(R.id.manageSourceButton);
        tverButton = findViewById(R.id.tverButton);
        help = findViewById(R.id.settingsHelp);

        displayButton.setOnClickListener(v -> chooseDisplayMode());
        multiButton.setOnClickListener(v -> chooseMultiCount());
        volumeButton.setOnClickListener(v -> changeVolume(10));
        volumeButton.setOnLongClickListener(v -> { changeVolume(-10); return true; });
        addSourceButton.setOnClickListener(v -> chooseModeForSource());
        manageSourceButton.setOnClickListener(v -> manageSources());
        tverButton.setOnClickListener(v -> openTver());

        refreshLabels();
        displayButton.requestFocus();
    }

    private void chooseDisplayMode() {
        String[] labels = {"全画面モード", "番組表モード", "アプリモード", "多チャンネルモード"};
        String[] values = {AppPrefs.DISPLAY_FULLSCREEN, AppPrefs.DISPLAY_GUIDE, AppPrefs.DISPLAY_APP, AppPrefs.DISPLAY_MULTI};
        String current = AppPrefs.displayMode(this);
        int selected = 0;
        for (int i = 0; i < values.length; i++) if (values[i].equals(current)) selected = i;
        new AlertDialog.Builder(this)
            .setTitle("再生画面")
            .setSingleChoiceItems(labels, selected, (d, which) -> {
                AppPrefs.setDisplayMode(this, values[which]);
                d.dismiss();
                refreshLabels();
            })
            .setNegativeButton("閉じる", null).show();
    }

    private void chooseMultiCount() {
        String[] labels = {"4画面", "6画面", "8画面"};
        int[] values = {4, 6, 8};
        int current = AppPrefs.multiCount(this);
        int selected = current == 6 ? 1 : (current == 8 ? 2 : 0);
        new AlertDialog.Builder(this)
            .setTitle("多チャンネル画面数")
            .setSingleChoiceItems(labels, selected, (d, which) -> {
                AppPrefs.setMultiCount(this, values[which]);
                d.dismiss();
                refreshLabels();
            })
            .setNegativeButton("閉じる", null).show();
    }

    private void changeVolume(int delta) {
        int v = AppPrefs.volume(this) + delta;
        if (v > 100) v = 0;
        if (v < 0) v = 100;
        AppPrefs.setVolume(this, v);
        refreshLabels();
    }

    private void chooseModeForSource() {
        String[] modes = PlaylistCatalog.selectableModes();
        String[] labels = new String[modes.length];
        for (int i = 0; i < modes.length; i++) labels[i] = PlaylistCatalog.modeLabel(modes[i]);
        new AlertDialog.Builder(this)
            .setTitle("追加先")
            .setItems(labels, (d, which) -> showAddSourceForm(modes[which]))
            .setNegativeButton("閉じる", null).show();
    }

    private void showAddSourceForm(String mode) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        box.setPadding(pad, pad, pad, pad);

        EditText name = field("名前 例: 自宅M3U");
        EditText m3u = field("M3U URL");
        EditText epg = field("EPG(XMLTV) URL  ※空欄可");
        box.addView(name);
        box.addView(m3u);
        box.addView(epg);

        new AlertDialog.Builder(this)
            .setTitle(PlaylistCatalog.modeLabel(mode) + " にM3U/EPG追加")
            .setView(box)
            .setPositiveButton("追加", (d, w) -> {
                String u = m3u.getText().toString().trim();
                if (u.isEmpty()) {
                    Toast.makeText(this, "M3U URLが必要です", Toast.LENGTH_SHORT).show();
                    return;
                }
                String n = name.getText().toString().trim();
                if (n.isEmpty()) n = "追加M3U";
                SourceManager.add(this, n, mode, u, epg.getText().toString().trim());
                Toast.makeText(this, "追加しました", Toast.LENGTH_SHORT).show();
                refreshLabels();
            })
            .setNegativeButton("キャンセル", null).show();
    }

    private EditText field(String hint) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        e.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(62)));
        return e;
    }

    private void manageSources() {
        List<SourceManager.Entry> list = SourceManager.all(this);
        if (list.isEmpty()) {
            Toast.makeText(this, "追加M3Uはありません", Toast.LENGTH_SHORT).show();
            return;
        }
        String[] rows = new String[list.size()];
        for (int i = 0; i < list.size(); i++) {
            SourceManager.Entry e = list.get(i);
            rows[i] = "[" + PlaylistCatalog.modeLabel(e.mode) + "] " + e.name;
        }
        new AlertDialog.Builder(this)
            .setTitle("削除する追加M3Uを選択")
            .setItems(rows, (d, which) -> {
                SourceManager.remove(this, which);
                Toast.makeText(this, "削除しました", Toast.LENGTH_SHORT).show();
                refreshLabels();
            })
            .setNegativeButton("閉じる", null).show();
    }

    private void openTver() {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("https://tver.jp/mypage/favorites"));
            startActivity(i);
        } catch (Exception e) {
            try {
                Intent launch = getPackageManager().getLaunchIntentForPackage("jp.co.tver.tvapp");
                if (launch != null) startActivity(launch);
                else Toast.makeText(this, "TVerアプリが見つかりません", Toast.LENGTH_LONG).show();
            } catch (Exception ignored) {}
        }
    }

    private void refreshLabels() {
        String display = AppPrefs.displayMode(this);
        String displayLabel = AppPrefs.DISPLAY_FULLSCREEN.equals(display) ? "全画面" :
            AppPrefs.DISPLAY_GUIDE.equals(display) ? "番組表" :
            AppPrefs.DISPLAY_MULTI.equals(display) ? "多チャンネル" : "アプリ";
        displayButton.setText("再生画面：" + displayLabel + "モード");
        multiButton.setText("多チャンネル：" + AppPrefs.multiCount(this) + "画面");
        volumeButton.setText("アプリ音量：" + AppPrefs.volume(this) + "　(決定:+10 / 長押し:-10)");
        manageSourceButton.setText("追加M3U管理：" + SourceManager.all(this).size() + "件");
        help.setText("共通プレイヤー：← チャンネル一覧 / → 番組情報 / ↑↓ 選局 / MENU 設定\nM3UとEPGはセットで追加できます。YouTube系は専用再生へ自動切替します。");
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
}
