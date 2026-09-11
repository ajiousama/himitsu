package jp.jun.iptv;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.List;

public final class ChannelAdapter extends BaseAdapter {
    private final Context c;
    private final List<Channel> data;
    public ChannelAdapter(Context c, List<Channel> data) { this.c = c; this.data = data; }
    @Override public int getCount() { return data.size(); }
    @Override public Channel getItem(int p) { return data.get(p); }
    @Override public long getItemId(int p) { return p; }

    @Override public View getView(int p, View v, ViewGroup parent) {
        Holder h;
        if (v == null) {
            LinearLayout row = new LinearLayout(c);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(12), dp(8), dp(12), dp(8));
            row.setMinimumHeight(dp(70));

            ImageView logo = new ImageView(c);
            logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
            row.addView(logo, new LinearLayout.LayoutParams(dp(68), dp(50)));

            LinearLayout texts = new LinearLayout(c);
            texts.setOrientation(LinearLayout.VERTICAL);
            texts.setPadding(dp(12), 0, 0, 0);
            TextView name = new TextView(c);
            name.setTextColor(Color.WHITE);
            name.setTextSize(17);
            name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            TextView now = new TextView(c);
            now.setTextColor(Color.rgb(190, 196, 205));
            now.setTextSize(13);
            texts.addView(name, new LinearLayout.LayoutParams(-1, -2));
            texts.addView(now, new LinearLayout.LayoutParams(-1, -2));
            row.addView(texts, new LinearLayout.LayoutParams(0, -2, 1f));

            h = new Holder(); h.logo = logo; h.name = name; h.now = now;
            row.setTag(h);
            v = row;
        } else h = (Holder) v.getTag();

        Channel ch = getItem(p);
        h.name.setText((p + 1) + "  " + ch.name);
        h.now.setText(ch.nowTitle.isEmpty() ? (ch.group.isEmpty() ? " " : ch.group) : ch.nowTitle);
        LogoLoader.load(h.logo, ch.logo);
        return v;
    }

    private int dp(int v) { return (int)(v * c.getResources().getDisplayMetrics().density + .5f); }
    private static final class Holder { ImageView logo; TextView name, now; }
}
