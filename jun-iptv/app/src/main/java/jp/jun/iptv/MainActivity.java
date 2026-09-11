package jp.jun.iptv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.text.InputType;
import android.view.KeyEvent;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

public class MainActivity extends Activity {
    private final SecretSequence secretSequence = new SecretSequence();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        Button tv = findViewById(R.id.tvMode);
        Button radio = findViewById(R.id.radioMode);
        Button gamble = findViewById(R.id.gambleMode);
        Button youtube = findViewById(R.id.youtubeMode);
        Button settings = findViewById(R.id.settingsMode);

        tv.setOnClickListener(v -> open(PlaylistCatalog.MODE_TV));
        radio.setOnClickListener(v -> open(PlaylistCatalog.MODE_RADIO));
        gamble.setOnClickListener(v -> open(PlaylistCatalog.MODE_GAMBLE));
        youtube.setOnClickListener(v -> open(PlaylistCatalog.MODE_YOUTUBE));
        settings.setOnClickListener(v -> startActivity(new Intent(this, SettingsActivity.class)));
        tv.requestFocus();
    }

    private void open(String mode) {
        Intent i = AppPrefs.DISPLAY_MULTI.equals(AppPrefs.displayMode(this))
            ? new Intent(this, MultiViewActivity.class)
            : new Intent(this, ChannelActivity.class);
        i.putExtra("mode", mode);
        startActivity(i);
    }

    private void unlockSecretMode() {
        if (AppPrefs.secretM3u(this).isEmpty()) {
            Toast.makeText(this, "秘密モードは未設定です", Toast.LENGTH_SHORT).show();
            return;
        }
        EditText pin = new EditText(this);
        pin.setSingleLine(true);
        pin.setHint("PIN");
        pin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        new AlertDialog.Builder(this)
            .setTitle("PIN")
            .setView(pin)
            .setPositiveButton("開く", (d, w) -> {
                if (AppPrefs.secretPin(this).equals(pin.getText().toString().trim())) open(PlaylistCatalog.MODE_SECRET);
                else Toast.makeText(this, "PINが違います", Toast.LENGTH_SHORT).show();
            })
            .setNegativeButton("キャンセル", null)
            .show();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN && secretSequence.push(keyCode)) {
            unlockSecretMode();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }
}
