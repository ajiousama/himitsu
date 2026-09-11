package jp.jun.iptv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.text.InputType;
import android.view.KeyEvent;
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
    private final SecretSequence secretSequence = new SecretSequence();

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
            .setTitle("多チャンネル")
            .setSingleChoiceItems(labels, selected, (d, which) -> {
                AppPrefs.setMultiCount(this, values[which]);
                d.dismiss();
                refreshLabels();
                Toast.makeText(this, values[which] + "画面に設定しました", Toast.LENGTH_SHORT).show();
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
        box.addView(name); box.addView(m3u); box.addView(epg);

        new AlertDialog.Builder(this)
            .setTitle(PlaylistCatalog.modeLabel(mode) + " にM3U/EPG追加")
            .setView(box)
            .setPositiveButton("追加", (d, w) -> {
                String u = m3u.getText().toString().trim();
                if (u.isEmpty()) { Toast.makeText(this, "M3U URLが必要です", Toast.LENGTH_SHORT).show(); return; }
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
        if (list.isEmpty()) { Toast.makeText(this, "追加M3Uはありません", Toast.LENGTH_SHORT).show(); return; }
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
        String[] packages = {"jp.co.tver.tvapp", "jp.co.tver"};
        for (String pkg : packages) {
            Intent launch = getPackageManager().getLaunchIntentForPackage(pkg);
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
                startActivity(launch);
                return;
            }
        }
        Toast.makeText(this, "TVerアプリがインストールされていません", Toast.LENGTH_LONG).show();
    }

    private void promptSecretPin() {
        EditText pin = new EditText(this);
        pin.setSingleLine(true);
        pin.setHint("PIN");
        pin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        new AlertDialog.Builder(this)
            .setTitle("秘密モード設定")
            .setView(pin)
            .setPositiveButton("開く", (d, w) -> {
                if (AppPrefs.secretPin(this).equals(pin.getText().toString().trim())) showSecretSettings();
                else Toast.makeText(this, "PINが違います", Toast.LENGTH_SHORT).show();
            })
            .setNegativeButton("キャンセル", null)
            .show();
    }

    private void showSecretSettings() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        box.setPadding(pad, pad, pad, pad);
        EditText m3u = field("秘密モード M3U URL");
        m3u.setText(AppPrefs.secretM3u(this));
        EditText epg = field("EPG(XMLTV) URL  ※空欄可");
        epg.setText(AppPrefs.secretEpg(this));
        EditText newPin = new EditText(this);
        newPin.setHint("PIN 4〜8桁");
        newPin.setSingleLine(true);
        newPin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        newPin.setText(AppPrefs.secretPin(this));
        newPin.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(62)));
        box.addView(m3u); box.addView(epg); box.addView(newPin);

        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("秘密モード")
            .setView(box)
            .setPositiveButton("保存", null)
            .setNegativeButton("キャンセル", null)
            .create();
        dialog.setOnShowListener(x -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String p = newPin.getText().toString().trim();
            if (!p.matches("\\d{4,8}")) { Toast.makeText(this, "PINは4〜8桁の数字にしてください", Toast.LENGTH_SHORT).show(); return; }
            AppPrefs.setSecret(this, m3u.getText().toString(), epg.getText().toString(), p);
            Toast.makeText(this, m3u.getText().toString().trim().isEmpty() ? "秘密モードを無効にしました" : "秘密モードを保存しました", Toast.LENGTH_SHORT).show();
            dialog.dismiss();
        }));
        dialog.show();
    }

    private void refreshLabels() {
        String display = AppPrefs.displayMode(this);
        String displayLabel = AppPrefs.DISPLAY_FULLSCREEN.equals(display) ? "全画面" : AppPrefs.DISPLAY_GUIDE.equals(display) ? "番組表" : AppPrefs.DISPLAY_MULTI.equals(display) ? "多チャンネル" : "アプリ";
        displayButton.setText("再生画面：" + displayLabel + "モード");
        multiButton.setText("多チャンネル：" + AppPrefs.multiCount(this) + "画面  （4 / 6 / 8）");
        volumeButton.setText("アプリ音量：" + AppPrefs.volume(this) + "　(決定:+10 / 長押し:-10)");
        manageSourceButton.setText("追加M3U管理：" + SourceManager.all(this).size() + "件");
        help.setText("共通リモコン操作：← チャンネル一覧 / → 番組情報 / ↑↓ 選局 / OK 決定 / 戻る 閉じる\nチャンネル送りは先頭と最後がループします。ロゴと接続状態を選局時に表示します。\nTVerはブラウザを使わず公式アプリだけを起動します。");
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN && secretSequence.push(keyCode)) {
            promptSecretPin();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
}
