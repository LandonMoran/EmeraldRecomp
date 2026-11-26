// EmeraldAccessibility — Android speech + TalkBack layer for EmeraldRecomp.
//
// Two jobs, one class:
//
//   1. Speech. With TalkBack off, the game speaks through its own
//      TextToSpeech instance. With TalkBack on (touch exploration enabled),
//      the same messages become accessibility announcements, so TalkBack's
//      voice, rate and verbosity apply and nothing is spoken twice.
//
//   2. A virtual accessibility node tree layered over the game view: status,
//      the choices on screen, the last game message, and the buttons. TalkBack
//      can focus any of them; activating an item or a button becomes a
//      synthesized game input in native code.
//
// The native side (src/accessibility/emerald_a11y_android.cpp) resolves this
// class through the activity's ClassLoader and calls the static methods below.
// Action codes are shared with src/accessibility/emerald_a11y.h.

package com.mstan.emeraldrecomp.accessibility;

import android.app.Activity;
import android.content.Context;
import android.graphics.Rect;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityNodeProvider;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class EmeraldAccessibility {
    private static final String TAG = "EmeraldA11y";

    // Keep in step with emerald::accessibility::Action.
    private static final int ACTION_UP = 1;
    private static final int ACTION_DOWN = 2;
    private static final int ACTION_LEFT = 3;
    private static final int ACTION_RIGHT = 4;
    private static final int ACTION_CONFIRM = 5;
    private static final int ACTION_CANCEL = 6;
    private static final int ACTION_START = 7;
    private static final int ACTION_READ_STATUS = 8;
    private static final int ACTION_REPEAT = 9;
    private static final int ACTION_STOP = 10;
    private static final int ACTION_SELECT_ITEM = 11;

    private static final int NODE_STATUS = 1;
    private static final int NODE_ITEMS = 2;
    private static final int NODE_MESSAGE = 3;
    private static final int NODE_CONTROLS = 4;
    private static final int NODE_ITEM_BASE = 100;
    private static final int NODE_CONTROL_BASE = 200;

    private static final String[] CONTROL_LABELS = {
        "Up", "Down", "Left", "Right", "A, confirm", "B, cancel", "Start menu",
        "Read status", "Repeat last message", "Stop speech"
    };
    private static final int[] CONTROL_ACTIONS = {
        ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT, ACTION_CONFIRM,
        ACTION_CANCEL, ACTION_START, ACTION_READ_STATUS, ACTION_REPEAT, ACTION_STOP
    };

    private static native void nativeAction(int action, int arg);

    private static Activity activity;
    private static View host;
    private static Provider provider;
    private static AccessibilityManager manager;
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

    private static volatile String statusText = "";
    private static volatile String messageText = "";
    private static volatile String[] items = new String[0];
    private static volatile int selected = -1;

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
                install();
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

    // status/items come from native as UTF-8; items are '\n'-separated.
    public static void setScene(String status, String itemsJoined, int selectedIndex,
                                String message) {
        final String newStatus = status == null ? "" : status;
        final String newMessage = message == null ? "" : message;
        final String[] newItems =
            (itemsJoined == null || itemsJoined.length() == 0)
                ? new String[0]
                : itemsJoined.split("\n", -1);
        statusText = newStatus;
        messageText = newMessage;
        items = newItems;
        selected = selectedIndex;
        final Activity a = activity;
        if (a == null) return;
        a.runOnUiThread(new Runnable() {
            public void run() {
                if (host == null || provider == null) {
                    // The view tree was not ready when the layer attached.
                    // Retry shortly (never once per frame).
                    scheduleInstall(a);
                    return;
                }
                AccessibilityEvent event =
                    AccessibilityEvent.obtain(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
                event.setClassName(host.getClass().getName());
                event.setPackageName(packageName());
                event.setSource(host, NODE_STATUS);
                event.setContentChangeTypes(
                    AccessibilityEvent.CONTENT_CHANGE_TYPE_CONTENT_DESCRIPTION);
                send(event);
            }
        });
    }

    public static boolean talkbackActive() {
        AccessibilityManager am = manager;
        if (am == null) {
            Activity a = activity;
            if (a != null) {
                am = (AccessibilityManager) a.getSystemService(Context.ACCESSIBILITY_SERVICE);
                manager = am;
            }
        }
        try {
            return am != null && am.isTouchExplorationEnabled();
        } catch (RuntimeException e) {
            return false;
        }
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

    // ── Installation ────────────────────────────────────────────────────

    private static void install() {
        if (host != null) return;
        Activity a = activity;
        if (a == null) return;
        View content = a.findViewById(android.R.id.content);
        if (content == null) {
            scheduleInstall(a);
            return;
        }
        View target = content;
        if (content instanceof ViewGroup && ((ViewGroup) content).getChildCount() > 0) {
            View child = ((ViewGroup) content).getChildAt(0);
            if (child != null) target = child;
        }
        host = target;
        provider = new Provider();
        host.setAccessibilityDelegate(new Delegate());
        host.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        host.setFocusable(true);
        manager = (AccessibilityManager) a.getSystemService(Context.ACCESSIBILITY_SERVICE);
        ensureTts();
        Log.i(TAG, "accessibility layer attached to " + host.getClass().getName());
    }

    // Retry the node-tree install after a short delay (the activity's content
    // view appears asynchronously). Speech does not wait for this.
    private static void scheduleInstall(final Activity a) {
        if (installPending || host != null || a == null) return;
        installPending = true;
        try {
            a.getWindow().getDecorView().postDelayed(new Runnable() {
                public void run() {
                    installPending = false;
                    install();
                }
            }, 250);
        } catch (RuntimeException e) {
            installPending = false;
            Log.w(TAG, "could not schedule the accessibility view install", e);
        }
    }

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

    private static String packageName() {
        View v = host;
        return v == null ? "com.mstan.emeraldrecomp" : v.getContext().getPackageName();
    }

    // ── Speech ──────────────────────────────────────────────────────────

    private static void speakOnUi(String text, boolean flush) {
        // TalkBack owns the voice only when it is actually driving the screen:
        // touch exploration on and a view to announce through. Every other
        // case -- TalkBack off (the handheld setup), no screen reader at all, or
        // a view tree that is not up yet -- speaks through this game's own
        // TextToSpeech engine, so no line is ever lost to a missing
        // announcement channel.
        if (talkbackActive() && host != null) {
            announce(text);
            return;
        }
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
        // TalkBack users hear new lines through TalkBack; the backlog still has
        // to reach them the same way rather than through a second voice.
        if (talkbackActive() && host != null) {
            announce(joined.toString());
            return;
        }
        if (!ttsReady || tts == null) return;
        ttsSpeak(joined.toString(), TextToSpeech.QUEUE_FLUSH);
    }

    private static void announce(String text) {
        View v = host;
        if (v == null) return;
        AccessibilityEvent event =
            AccessibilityEvent.obtain(AccessibilityEvent.TYPE_ANNOUNCEMENT);
        event.getText().add(text);
        event.setClassName(v.getClass().getName());
        event.setPackageName(packageName());
        event.setSource(v);
        send(event);
    }

    private static void send(AccessibilityEvent event) {
        View v = host;
        if (v == null) {
            event.recycle();
            return;
        }
        try {
            ViewParent parent = v.getParent();
            if (parent != null) {
                parent.requestSendAccessibilityEvent(v, event);
            } else {
                v.sendAccessibilityEventUnchecked(event);
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "accessibility event failed", e);
            event.recycle();
        }
    }

    // ── View delegate ───────────────────────────────────────────────────

    private static final class Delegate extends View.AccessibilityDelegate {
        @Override
        public AccessibilityNodeProvider getAccessibilityNodeProvider(View v) {
            return provider;
        }

        @Override
        public void onInitializeAccessibilityNodeInfo(View v, AccessibilityNodeInfo info) {
            super.onInitializeAccessibilityNodeInfo(v, info);
            info.setClassName("android.view.ViewGroup");
            info.setContentDescription(statusText);
        }

        @Override
        public boolean performAccessibilityAction(View v, int action, Bundle args) {
            if (action == AccessibilityNodeInfo.ACTION_CLICK) {
                nativeAction(ACTION_READ_STATUS, 0);
                return true;
            }
            return super.performAccessibilityAction(v, action, args);
        }
    }

    // ── Virtual node tree ───────────────────────────────────────────────

    private static final class Provider extends AccessibilityNodeProvider {
        @Override
        public AccessibilityNodeInfo createAccessibilityNodeInfo(int virtualViewId) {
            View v = host;
            if (v == null) return null;
            if (virtualViewId == View.NO_ID) return hostNode(v);
            AccessibilityNodeInfo info =
                AccessibilityNodeInfo.obtain(v, virtualViewId);
            info.setPackageName(packageName());
            info.setSource(v, virtualViewId);
            info.setParent(v);
            info.setVisibleToUser(true);
            info.setEnabled(true);
            info.setFocusable(true);

            if (virtualViewId == NODE_STATUS) {
                info.setClassName("android.widget.TextView");
                info.setText(statusText);
                info.addAction(AccessibilityNodeInfo.ACTION_CLICK);
                info.setBoundsInScreen(bounds(0, 1));
            } else if (virtualViewId == NODE_ITEMS) {
                info.setClassName("android.widget.ListView");
                info.setContentDescription("Choices");
                String[] snapshot = items;
                for (int i = 0; i < snapshot.length; ++i) {
                    info.addChild(v, NODE_ITEM_BASE + i);
                }
                info.setBoundsInScreen(bounds(1, Math.max(2, snapshot.length + 2)));
            } else if (virtualViewId >= NODE_ITEM_BASE && virtualViewId < NODE_CONTROL_BASE) {
                int index = virtualViewId - NODE_ITEM_BASE;
                String[] snapshot = items;
                if (index >= snapshot.length) return null;
                info.setClassName("android.widget.Button");
                info.setText(snapshot[index] + (index == selected ? ", selected" : ""));
                info.setSelected(index == selected);
                info.addAction(AccessibilityNodeInfo.ACTION_CLICK);
                info.setBoundsInScreen(bounds(index + 2, Math.max(2, snapshot.length + 2)));
            } else if (virtualViewId == NODE_MESSAGE) {
                info.setClassName("android.widget.TextView");
                info.setText(messageText.length() == 0 ? "No message yet" : messageText);
                info.addAction(AccessibilityNodeInfo.ACTION_CLICK);
                info.setBoundsInScreen(bounds(2, 4));
            } else if (virtualViewId == NODE_CONTROLS) {
                info.setClassName("android.widget.GridView");
                info.setContentDescription("Game controls");
                for (int i = 0; i < CONTROL_LABELS.length; ++i) {
                    info.addChild(v, NODE_CONTROL_BASE + i);
                }
                info.setBoundsInScreen(bounds(3, 4));
            } else if (virtualViewId >= NODE_CONTROL_BASE) {
                int index = virtualViewId - NODE_CONTROL_BASE;
                if (index >= CONTROL_LABELS.length) return null;
                info.setClassName("android.widget.Button");
                info.setText(CONTROL_LABELS[index]);
                info.addAction(AccessibilityNodeInfo.ACTION_CLICK);
                info.setBoundsInScreen(bounds(3, 4));
            } else {
                return null;
            }
            return info;
        }

        private AccessibilityNodeInfo hostNode(View v) {
            AccessibilityNodeInfo info = AccessibilityNodeInfo.obtain(v);
            info.setPackageName(packageName());
            info.setClassName("android.view.ViewGroup");
            info.setSource(v);
            info.setContentDescription(statusText);
            info.addChild(v, NODE_STATUS);
            info.addChild(v, NODE_ITEMS);
            info.addChild(v, NODE_MESSAGE);
            info.addChild(v, NODE_CONTROLS);
            info.setBoundsInScreen(bounds(0, 1));
            return info;
        }

        @Override
        public boolean performAction(int virtualViewId, int action, Bundle args) {
            if (action == AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS) {
                sendFocus(virtualViewId, true);
                return true;
            }
            if (action == AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS) {
                sendFocus(virtualViewId, false);
                return true;
            }
            if (action == AccessibilityNodeInfo.ACTION_CLICK) {
                if (virtualViewId >= NODE_CONTROL_BASE) {
                    int index = virtualViewId - NODE_CONTROL_BASE;
                    if (index >= 0 && index < CONTROL_ACTIONS.length) {
                        nativeAction(CONTROL_ACTIONS[index], 0);
                        return true;
                    }
                    return false;
                }
                if (virtualViewId >= NODE_ITEM_BASE) {
                    nativeAction(ACTION_SELECT_ITEM, virtualViewId - NODE_ITEM_BASE);
                    return true;
                }
                if (virtualViewId == NODE_STATUS) {
                    nativeAction(ACTION_READ_STATUS, 0);
                    return true;
                }
                if (virtualViewId == NODE_MESSAGE) {
                    nativeAction(ACTION_REPEAT, 0);
                    return true;
                }
            }
            return false;
        }

        private void sendFocus(int virtualViewId, boolean focused) {
            View v = host;
            if (v == null) return;
            AccessibilityEvent event = AccessibilityEvent.obtain(
                focused ? AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED
                        : AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
            event.setClassName("android.view.View");
            event.setPackageName(packageName());
            event.setSource(v, virtualViewId);
            event.setContentDescription(nodeText(virtualViewId));
            send(event);
        }

        private String nodeText(int virtualViewId) {
            if (virtualViewId == NODE_STATUS) return statusText;
            if (virtualViewId == NODE_MESSAGE) return messageText;
            if (virtualViewId == NODE_ITEMS) return "Choices";
            if (virtualViewId == NODE_CONTROLS) return "Game controls";
            if (virtualViewId >= NODE_CONTROL_BASE) {
                int index = virtualViewId - NODE_CONTROL_BASE;
                return index >= 0 && index < CONTROL_LABELS.length ? CONTROL_LABELS[index] : "";
            }
            if (virtualViewId >= NODE_ITEM_BASE) {
                int index = virtualViewId - NODE_ITEM_BASE;
                String[] snapshot = items;
                return index >= 0 && index < snapshot.length ? snapshot[index] : "";
            }
            return "";
        }
    }

    // Rough on-screen rectangles so touch exploration can reach the nodes. The
    // game image is one view, so rows are sliced out of its bounds.
    private static Rect bounds(int index, int rows) {
        Rect rect = new Rect();
        View v = host;
        if (v == null) return rect;
        int[] location = new int[2];
        v.getLocationOnScreen(location);
        int width = Math.max(1, v.getWidth());
        int height = Math.max(1, v.getHeight());
        int count = Math.max(1, rows);
        int rowHeight = Math.max(1, height / count);
        int top = location[1] + Math.min(index, count - 1) * rowHeight;
        rect.set(location[0], top, location[0] + width, Math.min(location[1] + height,
                                                                  top + rowHeight));
        return rect;
    }
}
