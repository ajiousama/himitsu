package jp.jun.iptv;

import android.view.KeyEvent;

public final class SecretSequence {
    private static final int[] KEYS = {
        KeyEvent.KEYCODE_DPAD_UP,
        KeyEvent.KEYCODE_DPAD_UP,
        KeyEvent.KEYCODE_DPAD_DOWN,
        KeyEvent.KEYCODE_DPAD_DOWN,
        KeyEvent.KEYCODE_DPAD_LEFT,
        KeyEvent.KEYCODE_DPAD_RIGHT,
        KeyEvent.KEYCODE_DPAD_LEFT,
        KeyEvent.KEYCODE_DPAD_RIGHT
    };
    private int pos = 0;
    public boolean push(int keyCode) {
        if (keyCode == KEYS[pos]) {
            pos++;
            if (pos == KEYS.length) { pos = 0; return true; }
            return false;
        }
        pos = keyCode == KEYS[0] ? 1 : 0;
        return false;
    }
}
