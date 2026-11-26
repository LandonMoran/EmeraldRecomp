// SetupVoice — speech for the first-launch setup screen.
//
// The game's spoken interface (EmeraldAccessibility) only attaches once the SDL
// game activity runs, but ROM/BIOS import happens in the setup activity before
// that. SetupVoice gives that screen the same speech path:
//
//   * TalkBack off: Android TextToSpeech, with queue/flush and repetition
//     suppression, so the screen narrates itself.
//   * TalkBack on: no second voice. The screen's views are ordinary Android
//     widgets and already speak; the setup activity sets polite live regions so
//     status changes are announced too.
//
// This is deliberately separate from EmeraldAccessibility: the setup screen has
// no game view, no virtual node tree and no native frame loop.

package com.mstan.emeraldrecomp.accessibility;

import android.app.Activity;
import android.content.Context;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.util.Log;
import android.view.View;
import android.view.ViewParent;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityManager;

import java.util.ArrayDeque;
import java.util.Locale;

final class SetupVoice {
    private static final String TAG = "EmeraldSetupVoice";

    private final Activity activity;
    private final ArrayDeque<String> pending = new ArrayDeque<String>();
    private TextToSpeech tts;
    private boolean ready;
    private String lastSpoken = "";
    private long lastSpokenAt;

    SetupVoice(Activity activity) {
        this.activity = activity;
        start();
    }

    private void start() {
        try {
            tts = new TextToSpeech(activity.getApplicationContext(),
                new TextToSpeech.OnInitListener() {
                    public void onInit(int status) {
                        if (status != TextToSpeech.SUCCESS) {
                            Log.w(TAG, "TextToSpeech is unavailable");
                            return;
                        }
                        ready = true;
                        try {
                            tts.setLanguage(Locale.US);
                        } catch (RuntimeException error) {
                            Log.w(TAG, "language selection failed", error);
                        }
                        flushPending();
                    }
                });
        } catch (RuntimeException error) {
            Log.w(TAG, "TextToSpeech could not start", error);
        }
    }

    boolean talkbackActive() {
        try {
            AccessibilityManager manager =
                (AccessibilityManager) activity.getSystemService(Context.ACCESSIBILITY_SERVICE);
            return manager != null && manager.isTouchExplorationEnabled();
        } catch (RuntimeException error) {
            return false;
        }
    }

    void speak(String text) {
        speak(text, false);
    }

    void speak(final String text, final boolean flush) {
        if (text == null || text.length() == 0) return;
        activity.runOnUiThread(new Runnable() {
            public void run() {
                speakOnUi(text, flush);
            }
        });
    }

    private void speakOnUi(String text, boolean flush) {
        if (talkbackActive()) {
            announce(text);
            return;
        }
        final long now = SystemClock.uptimeMillis();
        if (!flush && text.equals(lastSpoken) && now - lastSpokenAt < 2000) return;
        lastSpoken = text;
        lastSpokenAt = now;
        if (!ready || tts == null) {
            if (pending.size() < 4) pending.add(text);
            return;
        }
        say(text, flush ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD);
    }

    private void say(String text, int queueMode) {
        if (tts == null) return;
        try {
            tts.speak(text, queueMode, null, "emerald-setup");
        } catch (RuntimeException error) {
            Log.w(TAG, "speak failed", error);
        }
    }

    private void flushPending() {
        if (!ready || tts == null || pending.isEmpty()) return;
        StringBuilder joined = new StringBuilder();
        while (!pending.isEmpty()) {
            if (joined.length() > 0) joined.append(' ');
            joined.append(pending.removeFirst());
        }
        say(joined.toString(), TextToSpeech.QUEUE_FLUSH);
    }

    // Let TalkBack speak (it owns the voice in this mode) instead of starting a
    // second voice over it.
    private void announce(String text) {
        View host = activity.findViewById(android.R.id.content);
        if (host == null) return;
        AccessibilityEvent event =
            AccessibilityEvent.obtain(AccessibilityEvent.TYPE_ANNOUNCEMENT);
        event.getText().add(text);
        event.setClassName(host.getClass().getName());
        event.setPackageName(activity.getPackageName());
        event.setSource(host);
        try {
            ViewParent parent = host.getParent();
            if (parent != null) {
                parent.requestSendAccessibilityEvent(host, event);
            } else {
                host.sendAccessibilityEventUnchecked(event);
            }
        } catch (RuntimeException error) {
            Log.w(TAG, "announcement failed", error);
            event.recycle();
        }
    }

    void shutdown() {
        if (tts != null) {
            try {
                tts.stop();
                tts.shutdown();
            } catch (RuntimeException error) {
                Log.w(TAG, "shutdown failed", error);
            }
            tts = null;
        }
        ready = false;
        pending.clear();
    }
}
