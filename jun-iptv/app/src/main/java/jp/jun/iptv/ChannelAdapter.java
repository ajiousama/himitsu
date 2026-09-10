package jp.jun.iptv;

import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
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
            row.setOrientation(LinearLayout.VERTICAL);
            row.setPadding(dp(14), dp(10), dp(12), dp(10));
            row.setGravity(Gravity.CENTER_VERTICAL);
            TextView name = new TextView(context);
            name.setTextColor(Color.WHITE);
            name.setTextSize(18);
            name.setSingleLine(true);
            TextView program = new TextView(context);
            program.setTextColor(Color.rgb(180, 186, 198));
            program.setTextSize(13);
            program.setSingleLine(true);
            row.addView(name, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            row.addView(program, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            h = new Holder(name, program);
            row.setTag(h);
            convertView = row;
        } else h = (Holder) convertView.getTag();

        Channel c = getItem(position);
        String prefix = c.group.isEmpty() ? "" : "[" + c.group + "] ";
        h.name.setText(prefix + c.name);
        h.program.setText(c.nowProgram.isEmpty() ? c.source : c.nowProgram);
        return convertView;
    }

    private int dp(int v) { return (int) (v * context.getResources().getDisplayMetrics().density + 0.5f); }
    private static class Holder {
        final TextView name, program;
        Holder(TextView name, TextView program) { this.name = name; this.program = program; }
    }
}
