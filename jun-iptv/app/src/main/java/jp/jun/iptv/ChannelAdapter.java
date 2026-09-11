package jp.jun.iptv;

import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.List;

public class ChannelAdapter extends BaseAdapter {
    private final Context context;
    private final List<Channel> channels;

    public ChannelAdapter(Context context, List<Channel> channels) {
        this.context = context;
        this.channels = channels;
    }

    @Override public int getCount() { return channels.size(); }
    @Override public Channel getItem(int position) { return channels.get(position); }
    @Override public long getItemId(int position) { return position; }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) {
        Holder h;
        if (convertView == null) {
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setPadding(dp(12), dp(8), dp(12), dp(8));
            row.setGravity(Gravity.CENTER_VERTICAL);

            ImageView logo = new ImageView(context);
            logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
            LinearLayout.LayoutParams logoLp = new LinearLayout.LayoutParams(dp(56), dp(46));
            logoLp.setMarginEnd(dp(12));
            row.addView(logo, logoLp);

            LinearLayout texts = new LinearLayout(context);
            texts.setOrientation(LinearLayout.VERTICAL);
            TextView name = new TextView(context);
            name.setTextColor(Color.WHITE);
            name.setTextSize(18);
            name.setSingleLine(true);
            TextView program = new TextView(context);
            program.setTextColor(Color.rgb(180, 186, 198));
            program.setTextSize(13);
            program.setSingleLine(true);
            texts.addView(name, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            texts.addView(program, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            row.addView(texts, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

            h = new Holder(logo, name, program);
            row.setTag(h);
            convertView = row;
        } else {
            h = (Holder) convertView.getTag();
        }

        Channel c = getItem(position);
        h.name.setText(c.name);
        String sub = c.nowProgram.isEmpty() ? (c.group.isEmpty() ? c.source : c.group) : c.nowProgram;
        h.program.setText(sub);
        LogoLoader.load(h.logo, c.logo);
        return convertView;
    }

    private int dp(int v) { return (int) (v * context.getResources().getDisplayMetrics().density + 0.5f); }

    private static class Holder {
        final ImageView logo;
        final TextView name, program;
        Holder(ImageView logo, TextView name, TextView program) {
            this.logo = logo;
            this.name = name;
            this.program = program;
        }
    }
}
