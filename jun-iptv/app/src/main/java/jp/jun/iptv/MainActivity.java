package jp.jun.iptv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;

public class MainActivity extends Activity {
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
        Intent i;
        if (AppPrefs.DISPLAY_MULTI.equals(AppPrefs.displayMode(this))) {
            i = new Intent(this, MultiViewActivity.class);
        } else {
            i = new Intent(this, ChannelActivity.class);
        }
        i.putExtra("mode", mode);
        startActivity(i);
    }
}
