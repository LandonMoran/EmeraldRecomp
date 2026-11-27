// EmeraldAccessibility.java — the game's own voice on Android.
//
// The spoken interface is the game's own text to speech, not a screen-reader
// tree. An accessibility node tree published over the game screen is read by
// TalkBack, and TalkBack then owns the controls: with nodes in the tree, the
// pad, the keyboard and touches move accessibility focus instead of reaching
// Pokémon, so the game becomes unplayable with a controller. That is the wrong
// trade for a game whose whole interface is already spoken, so:
//
//   * the game screen is marked not important for accessibility, and
//   * every line goes through this activity's own TextToSpeech engine.
//
// The launcher (EmeraldSetupActivity) is the opposite case and is untouched: it
// is stock Android widgets, so its tree is the platform's own and TalkBack
// reads and drives it normally before the game starts. SetupVoice decides on
// that screen whether the game should narrate; nothing here reaches it.
//
// Native → Java: speak / stopSpeech / setRate. There is no Java → native path
// any more: the in-game commands come from the pad's own key state and from the
// TCP debug port, both of which the native layer already owns.

package com.mstan.emeraldrecomp.accessibility;

import android.app.Activity;
import android.speech.tts.TextToSpeech;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class EmeraldAccessibility {
    private static final String TAG = "EmeraldA11y";

    private static Activity activity;
    private static TextToSpeech tts;
    private static boolean ttsReady;
    private static int ttsAttempts;
    private static boolean installPending;
    private static float rate = 1.0f;

    // While the engine is starting, keep the newest lines rather than the first
    // four: a cold TextToSpeech start must not swallow the greeting and the
    // first menu after it.
    private static final int MAX_PENDING_LINES = 12;
    private static final int MAX_PENDING_CHARS = 2000;

    private static final List<String> pendingSpeech = new ArrayList<String>();

    private EmeraldAccessibility() {}

    // ── Native entry points ─────────────────────────────────────────────

    public static boolean attach(Activity a) {
        if (a == null) return false;
        activity = a;
        a.runOnUiThread(new Runnable() {
            public void run() {
                // The voice comes first: the engine must not depend on the SDL
                // view being in the tree yet, or an early attach leaves the
                // whole run silent.
                ensureTts();
                hideGameScreenFromAccessibility();
            }
        });
        return true;
    }

    public static void speak(String text, int priority) {
        if (text == null || text.length() == 0) return;
        final Activity a = activity;
        final String message = text;
        final boolean flush = priority != 0;
        if (a == null) return;
        a.runOnUiThread(new Runnable() {
            public void run() {
                speakOnUi(message, flush);
            }
        });
    }

    public static void stopSpeech() {
        final Activity a = activity;
        if (a == null) return;
        a.runOnUiThread(new Runnable() {
            public void run() {
                pendingSpeech.clear();
                if (tts != null) {
                    try {
                        tts.stop();
                    } catch (RuntimeException ignored) {
                    }
                }
            }
        });
    }

    public static void setRate(float value) {
        rate = value;
        final Activity a = activity;
        if (a == null) return;
        a.runOnUiThread(new Runnable() {
            public void run() {
                if (tts != null) {
                    try {
                        tts.setSpeechRate(rate);
                    } catch (RuntimeException ignored) {
                    }
                }
            }
        });
    }

    public static void shutdown() {
        final Activity a = activity;
        if (a == null) return;
        a.runOnUiThread(new Runnable() {
            public void run() {
                if (tts != null) {
                    try {
                        tts.stop();
                        tts.shutdown();
                    } catch (RuntimeException ignored) {
                    }
                    tts = null;
                }
                ttsReady = false;
                pendingSpeech.clear();
            }
        });
    }

    // ── The game screen is not an accessibility surface ─────────────────

    // Hiding the game view keeps TalkBack's navigation (d-pad, keyboard,
    // touch exploration) away from the emulator: the controls belong to the
    // game, and the game speaks for itself. The launcher is a different
    // activity with its own stock views, so it is unaffected.
    private static void hideGameScreenFromAccessibility() {
        Activity a = activity;
        if (a == null) return;
        View content = a.findViewById(android.R.id.content);
        if (content == null) {
            scheduleHide(a);
            return;
        }
        View target = content;
        if (content instanceof ViewGroup && ((ViewGroup) content).getChildCount() > 0) {
            View child = ((ViewGroup) content).getChildAt(0);
            if (child != null) target = child;
        }
        target.setImportantForAccessibility(
            View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        target.setFocusable(false);
        Log.i(TAG, "game screen hidden from accessibility services");
    }

    // The activity's content view appears asynchronously; speech does not wait
    // for this and neither does play.
    private static void scheduleHide(final Activity a) {
        if (installPending || a == null) return;
        installPending = true;
        try {
            a.getWindow().getDecorView().postDelayed(new Runnable() {
                public void run() {
                    installPending = false;
                    hideGameScreenFromAccessibility();
                }
            }, 250);
        } catch (RuntimeException e) {
            installPending = false;
            Log.w(TAG, "could not schedule the game-screen hide", e);
        }
    }

    // ── Text to speech ─────────────────────────────────────────────────

    // One Android TextToSpeech engine for the whole run. Created as soon as an
    // activity exists, independent of the view tree, and retried once if the
    // platform reports the engine as unavailable, so the game cannot end up
    // with no voice at all.
    private static void ensureTts() {
        final Activity a = activity;
        if (a == null || tts != null || ttsReady) return;
        try {
            tts = new TextToSpeech(a.getApplicationContext(),
                new TextToSpeech.OnInitListener() {
                    public void onInit(int status) {
                        if (status != TextToSpeech.SUCCESS) {
                            Log.w(TAG, "TextToSpeech is unavailable");
                            final TextToSpeech failed = tts;
                            tts = null;
                            ttsReady = false;
                            try {
                                if (failed != null) failed.shutdown();
                            } catch (RuntimeException ignored) {
                            }
                            if (ttsAttempts < 1) {
                                ttsAttempts++;
                                try {
                                    a.getWindow().getDecorView().postDelayed(new Runnable() {
                                        public void run() {
                                            ensureTts();
                                        }
                                    }, 1000);
                                } catch (RuntimeException ignored) {
                                }
                            }
                            return;
                        }
                        ttsReady = true;
                        selectLanguage();
                        try {
                            tts.setSpeechRate(rate);
                        } catch (RuntimeException e) {
                            Log.w(TAG, "TextToSpeech rate failed", e);
                        }
                        flushPending();
                    }
                });
        } catch (RuntimeException e) {
            Log.w(TAG, "TextToSpeech could not start", e);
            tts = null;
        }
    }

    // US English is what the game's text is; if the device has no such voice,
    // fall back to its default language so speech is not lost.
    private static void selectLanguage() {
        if (tts == null) return;
        try {
            int result = tts.setLanguage(Locale.US);
            if (result == TextToSpeech.LANG_MISSING_DATA ||
                result == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts.setLanguage(Locale.getDefault());
                Log.w(TAG, "no US English voice; speaking the device language");
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "TextToSpeech language failed", e);
        }
    }

    private static void speakOnUi(String text, boolean flush) {
        if (!ttsReady || tts == null) {
            ensureTts();
            queuePending(text);
            return;
        }
        ttsSpeak(text, flush ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD);
    }

    // Keep the newest lines while the engine starts, bounded by count and by
    // characters so a burst of text cannot build an unbounded backlog.
    private static void queuePending(String text) {
        pendingSpeech.add(text);
        int total = 0;
        for (String line : pendingSpeech) total += line.length();
        while (pendingSpeech.size() > MAX_PENDING_LINES ||
               total > MAX_PENDING_CHARS) {
            total -= pendingSpeech.remove(0).length();
        }
    }

    private static void ttsSpeak(String text, int queueMode) {
        if (tts == null) return;
        try {
            // minSdk 28: the utterance-id form is always available.
            tts.speak(text, queueMode, null, "emerald");
        } catch (RuntimeException e) {
            Log.w(TAG, "speak failed", e);
        }
    }

    private static void flushPending() {
        StringBuilder joined = new StringBuilder();
        for (String line : pendingSpeech) {
            if (joined.length() > 0) joined.append(' ');
            joined.append(line);
        }
        pendingSpeech.clear();
        if (joined.length() == 0) return;
        if (!ttsReady || tts == null) return;
        ttsSpeak(joined.toString(), TextToSpeech.QUEUE_FLUSH);
    }
}
