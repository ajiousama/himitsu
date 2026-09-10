package jp.jun.iptv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.Toast;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        Button tv = findViewById(R.id.tvMode);
        Button radio = findViewById(R.id.radioMode);
        Button gamble = findViewById(R.id.gambleMode);
        Button settings = findViewById(R.id.settingsMode);

        tv.setOnClickListener(v -> openChannels(PlaylistCatalog.MODE_TV));
        radio.setOnClickListener(v -> openChannels(PlaylistCatalog.MODE_RADIO));
        gamble.setOnClickListener(v -> startActivity(new Intent(this, MultiViewActivity.class)));
        settings.setOnClickListener(v -> startActivity(new Intent(this, SettingsActivity.class)));

        tv.setOnLongClickListener(v -> {
            Toast.makeText(this, "高校野球モード", Toast.LENGTH_SHORT).show();
            openChannels(PlaylistCatalog.MODE_HIGH_SCHOOL);
            return true;
        });

        tv.requestFocus();
    }

    private void openChannels(String mode) {
        Intent i = new Intent(this, ChannelActivity.class);
        i.putExtra("mode", mode);
        startActivity(i);
    }
}
