// EmeraldSetupActivity — the engine's first-launch setup screen, spoken.
//
// The engine's launcher (org.gbarecomp.GbaSetupActivity) asks for a legally
// dumped ROM and BIOS, verifies them and copies them into private storage. It
// is ordinary Android UI, but nothing speaks it: with TalkBack off a blind
// player hears silence until the game starts. This subclass narrates the
// screen and its changes with Android text to speech, keeps TalkBack's live
// regions current when TalkBack is on, and speaks every control as it takes
// keyboard/gamepad focus.
//
// It is installed as the launcher activity by android/app/build.gradle, which
// derives the app manifest from the engine's and rewrites only the setup
// activity class name. Everything else — layout, verification, saved-game
// transfer, immersive mode — stays the engine's code.

package com.mstan.emeraldrecomp.accessibility;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.TextView;

import org.gbarecomp.GbaSetupActivity;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class EmeraldSetupActivity extends GbaSetupActivity {
    private SetupVoice voice;
    private View root;
    private final Set<View> hooked = new HashSet<View>();
    private List<String> previous = new ArrayList<String>();

    private final ViewTreeObserver.OnGlobalLayoutListener layoutListener =
        new ViewTreeObserver.OnGlobalLayoutListener() {
            @Override
            public void onGlobalLayout() {
                onScreenChanged();
            }
        };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        // The engine goes straight to the game when its files are already in
        // private storage (or bundled); there is nothing to narrate then.
        if (isFinishing() || isDestroyed()) return;
        View content = findViewById(android.R.id.content);
        if (!(content instanceof ViewGroup)) return;
        root = content;
        if (((ViewGroup) root).getChildCount() == 0) return;
        voice = new SetupVoice(this);
        installLiveRegions(root);
        hookControls(root);
        Snapshot snapshot = snapshot();
        previous = snapshot.lines;
        if (!voice.talkbackActive()) narrate(snapshot);
        root.getViewTreeObserver().addOnGlobalLayoutListener(layoutListener);
    }

    @Override
    protected void onDestroy() {
        if (root != null) {
            ViewTreeObserver observer = root.getViewTreeObserver();
            if (observer.isAlive()) observer.removeOnGlobalLayoutListener(layoutListener);
        }
        if (voice != null) {
            voice.shutdown();
            voice = null;
        }
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (voice == null) return;
        // The system file picker is another app and cannot be voiced from here;
        // confirm that the pick worked and that verification is running.
        if (resultCode == RESULT_OK && data != null)
            voice.speak("File received. Checking it now.", true);
    }

    // ── Screen reading ──────────────────────────────────────────────────

    private static final class Snapshot {
        final List<String> lines = new ArrayList<String>();
        final List<String> buttons = new ArrayList<String>();
        String title = "";
        float titleSize = 0;
        boolean playAvailable;
    }

    private Snapshot snapshot() {
        Snapshot snapshot = new Snapshot();
        collect(root, snapshot);
        List<String> deduped = new ArrayList<String>();
        for (String line : snapshot.lines) {
            if (deduped.isEmpty() || !deduped.get(deduped.size() - 1).equals(line))
                deduped.add(line);
        }
        snapshot.lines.clear();
        snapshot.lines.addAll(deduped);
        return snapshot;
    }

    private void collect(View view, Snapshot snapshot) {
        if (view == null || view.getVisibility() != View.VISIBLE) return;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); ++i) collect(group.getChildAt(i), snapshot);
            return;
        }
        if (!(view instanceof TextView)) return;
        String text = ((TextView) view).getText().toString().trim();
        if (text.isEmpty()) return;
        if (view instanceof Button && !(view instanceof CheckBox)) {
            snapshot.buttons.add(text);
            if (text.equalsIgnoreCase("PLAY")) snapshot.playAvailable = view.isEnabled();
        }
        // TalkBack reads a bare status line ("Verified and ready") without
        // saying which asset it refers to. The visible text is left alone; the
        // description gives the asset context, and the live region announces
        // the description when the status changes.
        if (isStatus(text)) {
            String label = assetLabel(snapshot.lines, snapshot.lines.size());
            String status = cleanStatus(text);
            String description = label.isEmpty() ? status : label + " status: " + status;
            if (!description.contentEquals(((TextView) view).getContentDescription() == null
                    ? "" : ((TextView) view).getContentDescription())) {
                view.setContentDescription(description);
            }
        }
        final float size = ((TextView) view).getTextSize();
        if (size > snapshot.titleSize) {
            snapshot.titleSize = size;
            snapshot.title = text;
        }
        snapshot.lines.add(text);
    }

    private void narrate(Snapshot snapshot) {
        StringBuilder out = new StringBuilder();
        if (!snapshot.title.isEmpty()) out.append(snapshot.title).append(". ");
        for (int i = 0; i < snapshot.lines.size(); ++i) {
            String line = snapshot.lines.get(i);
            if (!isStatus(line)) continue;
            String status = cleanStatus(line);
            String label = assetLabel(snapshot.lines, i);
            if (!label.isEmpty() && !status.toLowerCase(Locale.US).contains(label.toLowerCase(Locale.US)))
                out.append(label).append(": ");
            out.append(sentence(status)).append(' ');
        }
        out.append(snapshot.playAvailable
            ? "Play is available. "
            : "Play is disabled until the required files are chosen. ");
        if (!snapshot.buttons.isEmpty()) {
            out.append("Buttons: ");
            for (int i = 0; i < snapshot.buttons.size(); ++i) {
                if (i > 0) out.append(", ");
                out.append(snapshot.buttons.get(i).toLowerCase(Locale.US));
            }
            out.append(". ");
        }
        out.append("Use the arrow keys and Enter to choose, or turn on TalkBack and tap.");
        voice.speak(out.toString(), true);
    }

    // Narrate only what changed, so the screen does not repeat itself.
    private void onScreenChanged() {
        if (voice == null || root == null) return;
        Snapshot snapshot = snapshot();
        hookControls(root);
        installLiveRegions(root);
        if (!voice.talkbackActive()) {
            Set<String> before = new HashSet<String>(previous);
            Set<String> said = new HashSet<String>();
            for (int i = 0; i < snapshot.lines.size(); ++i) {
                String line = snapshot.lines.get(i);
                if (before.contains(line) || !said.add(line)) continue;
                String speech = describe(snapshot.lines, i);
                if (speech != null && speech.length() > 0) voice.speak(speech);
            }
        }
        previous = snapshot.lines;
    }

    private String describe(List<String> lines, int index) {
        String line = lines.get(index);
        if (!isStatus(line)) return sentence(line);
        String status = cleanStatus(line);
        String label = assetLabel(lines, index);
        if (!label.isEmpty() && !status.toLowerCase(Locale.US).contains(label.toLowerCase(Locale.US)))
            return sentence(label + ": " + status);
        return sentence(status);
    }

    // The engine's strings already end in a full stop or an ellipsis in places.
    private static String sentence(String text) {
        if (text.length() == 0) return text;
        final char last = text.charAt(text.length() - 1);
        if (last == '.' || last == '!' || last == '?' || last == '\u2026') return text;
        return text + ".";
    }

    private static boolean isStatus(String line) {
        return line.startsWith("\u25CF") || line.startsWith("\u25CB");   // ● / ○
    }

    private static String cleanStatus(String line) {
        String status = line;
        while (status.length() > 0
               && (status.charAt(0) == '\u25CF' || status.charAt(0) == '\u25CB'
                   || status.charAt(0) == ' ')) {
            status = status.substring(1);
        }
        return status.trim();
    }

    // The card headings name the asset ("1  Pokémon Emerald (USA) ROM",
    // "2  GBA BIOS", "3  Saved game"); walk back to the closest one.
    private static String assetLabel(List<String> lines, int index) {
        for (int i = index - 1; i >= 0; --i) {
            String line = lines.get(i);
            String lower = line.toLowerCase(Locale.US);
            if (lower.contains("bios")) return "BIOS";
            if (lower.contains("saved game")) return "Saved game";
            if (lower.contains("rom")) return "ROM";
        }
        return "";
    }

    // ── TalkBack and controls ───────────────────────────────────────────

    // Status text changes are only heard by TalkBack when the view is a live
    // region; the engine's TextViews are plain.
    private void installLiveRegions(View view) {
        if (view == null) return;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); ++i) installLiveRegions(group.getChildAt(i));
            return;
        }
        if (view instanceof TextView && !(view instanceof Button)) {
            try {
                view.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
            } catch (RuntimeException ignored) {
                // Accessibility is disabled or the platform is too old.
            }
        }
    }

    // Speak each control as it takes focus, so arrow keys and gamepads are
    // usable without sight (the engine's layout already handles focus order).
    private void hookControls(View view) {
        if (view == null) return;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); ++i) hookControls(group.getChildAt(i));
            return;
        }
        if (!(view instanceof Button) && !(view instanceof CheckBox)) return;
        if (!hooked.add(view)) return;
        view.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View changed, boolean hasFocus) {
                if (!hasFocus || voice == null || voice.talkbackActive()) return;
                if (!(changed instanceof TextView)) return;
                String label = ((TextView) changed).getText().toString().trim();
                if (label.length() > 0) voice.speak(label);
            }
        });
    }
}
