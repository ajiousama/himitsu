package jp.jun.iptv;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;

public class SettingsActivity extends Activity {
    public static final String PREFS = "jun_iptv_settings";
    public static final String KEY_DISPLAY_MODE = "display_mode";
    public static final String KEY_REMEMBER_DISPLAY = "remember_display";
    public static final String KEY_LAST_DISPLAY_MODE = "last_display_mode";
    public static final String MODE_FULLSCREEN = "fullscreen";
    public static final String MODE_SPLIT = "split";

    private SharedPreferences prefs;
    private Button displayButton;
    private Button rememberButton;
    private TextView help;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        displayButton = findViewById(R.id.displayModeButton);
        rememberButton = findViewById(R.id.rememberDisplayButton);
        help = findViewById(R.id.settingsHelp);

        displayButton.setOnClickListener(v -> {
            String current = prefs.getString(KEY_DISPLAY_MODE, MODE_FULLSCREEN);
            String next = MODE_FULLSCREEN.equals(current) ? MODE_SPLIT : MODE_FULLSCREEN;
            prefs.edit().putString(KEY_DISPLAY_MODE, next).apply();
            refreshLabels();
        });

        rememberButton.setOnClickListener(v -> {
            boolean remember = prefs.getBoolean(KEY_REMEMBER_DISPLAY, true);
            prefs.edit().putBoolean(KEY_REMEMBER_DISPLAY, !remember).apply();
            refreshLabels();
        });

        refreshLabels();
        displayButton.requestFocus();
    }

    private void refreshLabels() {
        String display = prefs.getString(KEY_DISPLAY_MODE, MODE_FULLSCREEN);
        boolean remember = prefs.getBoolean(KEY_REMEMBER_DISPLAY, true);
        displayButton.setText("標準表示：" + (MODE_FULLSCREEN.equals(display) ? "全画面" : "一覧＋映像"));
        rememberButton.setText("前回の表示状態を記憶：" + (remember ? "ON" : "OFF"));
        help.setText("視聴中はMENUキーで全画面／一覧＋映像を切り替えできます。\n記憶ONなら、次回も最後に使った表示から始まります。");
    }
}
