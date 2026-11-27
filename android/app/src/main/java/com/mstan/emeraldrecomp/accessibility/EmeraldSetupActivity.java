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
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.gbarecomp.GbaSetupActivity;
import org.gbarecomp.NativeSaveStore;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
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

    // Spoken-interface settings, edited here on the launcher rather than through
    // a pad chord the player has to remember. They are the same three options
    // the game's own Mods menu edits, written to the same mod state file.
    private LinearLayout settingsCard;
    private Button gameTextButton;
    private Button detailButton;
    private Button rateButton;

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
        installSettingsCard();
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
    protected void onResume() {
        super.onResume();
        // The game writes the same options from its own Mods menu, so read them
        // back whenever this screen returns: the launcher shows what the game
        // will actually use.
        if (voice == null) return;
        installSettingsCard();
        hookControls(root);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // The engine rebuilds its whole screen for the new orientation; the
        // settings card is ours, so it has to be put back into the new tree.
        if (voice == null || root == null) return;
        settingsCard = null;
        gameTextButton = null;
        detailButton = null;
        rateButton = null;
        installSettingsCard();
        hookControls(root);
        installLiveRegions(root);
        previous = snapshot().lines;
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

    // ── Spoken-interface settings ────────────────────────────────────────

    // Three options, set here before the game starts. They are the options the
    // game's own Mods menu shows, stored where the game reads them
    // (mods/state.toml), so the launcher and the menu are one setting.

    private void installSettingsCard() {
        ViewGroup host = scrollRoot();
        if (host == null) return;
        if (settingsCard != null && settingsCard.getParent() == host) {
            refreshSettingsLabels();
            return;
        }
        settingsCard = buildSettingsCard();
        host.addView(settingsCard, params(0, dip(8), 0, dip(6)));
        refreshSettingsLabels();
    }

    private LinearLayout buildSettingsCard() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dip(20), dip(12), dip(20), dip(12));
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(20, 25, 48));
        background.setCornerRadius(dip(18));
        background.setStroke(dip(1), Color.rgb(48, 58, 92));
        card.setBackground(background);

        TextView title = new TextView(this);
        title.setText("Spoken interface");
        title.setTextSize(17);
        title.setTextColor(Color.WHITE);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(title);

        TextView description = new TextView(this);
        description.setText("Set these before you play. They save as you tap. " +
            "To change them later, quit the game and you will land back here.");
        description.setTextSize(13);
        description.setTextColor(Color.rgb(164, 175, 207));
        description.setLineSpacing(0, 1.12f);
        card.addView(description, params(0, dip(4), 0, 0));

        gameTextButton = settingsButton();
        gameTextButton.setOnClickListener(view -> changeGameText());
        card.addView(gameTextButton, params(0, dip(6), 0, 0));

        detailButton = settingsButton();
        detailButton.setOnClickListener(view -> changeDetail());
        card.addView(detailButton, params(0, dip(6), 0, 0));

        rateButton = settingsButton();
        rateButton.setOnClickListener(view -> changeRate());
        card.addView(rateButton, params(0, dip(6), 0, 0));
        return card;
    }

    private Button settingsButton() {
        Button button = new Button(this);
        button.setTextColor(Color.WHITE);
        button.setTextSize(14);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(dip(52));
        button.setPadding(dip(16), 0, dip(16), 0);
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(30, 38, 68));
        background.setCornerRadius(dip(14));
        background.setStroke(dip(1), Color.rgb(78, 216, 255));
        button.setBackground(background);
        return button;
    }

    private void refreshSettingsLabels() {
        if (gameTextButton == null) return;
        SpokenUiSettings.Values values = SpokenUiSettings.read(stateText());
        gameTextButton.setText(gameTextLabel(values.gameText));
        detailButton.setText(detailLabel(values.verbosity));
        rateButton.setText(rateLabel(values.rate));
    }

    private void changeGameText() {
        SpokenUiSettings.Values values = SpokenUiSettings.read(stateText());
        values.gameText = "off".equals(values.gameText) ? "on" : "off";
        commitSettings(values, gameTextLabel(values.gameText));
    }

    private void changeDetail() {
        SpokenUiSettings.Values values = SpokenUiSettings.read(stateText());
        values.verbosity = "menus".equals(values.verbosity) ? "everything" : "menus";
        commitSettings(values, detailLabel(values.verbosity));
    }

    private void changeRate() {
        SpokenUiSettings.Values values = SpokenUiSettings.read(stateText());
        if ("slow".equals(values.rate)) values.rate = "normal";
        else if ("fast".equals(values.rate)) values.rate = "slow";
        else values.rate = "fast";
        commitSettings(values, rateLabel(values.rate));
    }

    private void commitSettings(SpokenUiSettings.Values values, String spoken) {
        if (NativeSaveStore.gameRunning()) {
            speakSettings("Quit the game first. These settings are changed here, " +
                "on the launcher, while the game is not running.");
            return;
        }
        boolean saved = saveSettings(values);
        refreshSettingsLabels();
        speakSettings(saved ? spoken : spoken + ", not saved.");
    }

    private void speakSettings(String text) {
        if (voice == null || voice.talkbackActive()) return;
        voice.speak(text, true);
    }

    private static String gameTextLabel(String value) {
        return "Read game text: " + ("off".equals(value) ? "off" : "on");
    }

    private static String detailLabel(String value) {
        return "Detail: " + ("menus".equals(value) ? "menus and battles only" : "everything");
    }

    private static String rateLabel(String value) {
        return "Speech rate: " + (value == null || value.isEmpty() ? "normal" : value);
    }

    /** The engine's scrolling content column, which our card joins. */
    private ViewGroup scrollRoot() {
        ScrollView scroll = findScroll(root);
        if (scroll == null) return null;
        View child = scroll.getChildAt(0);
        return child instanceof ViewGroup ? (ViewGroup) child : null;
    }

    private static ScrollView findScroll(View view) {
        if (view == null) return null;
        if (view instanceof ScrollView) return (ScrollView) view;
        if (!(view instanceof ViewGroup)) return null;
        ViewGroup group = (ViewGroup) view;
        for (int i = 0; i < group.getChildCount(); ++i) {
            ScrollView found = findScroll(group.getChildAt(i));
            if (found != null) return found;
        }
        return null;
    }

    private File stateFile() {
        return new File(getFilesDir(), "mods/state.toml");
    }

    /** The current mod state, or the copy that ships in the payload before it exists. */
    private String stateText() {
        File file = stateFile();
        if (file.isFile()) {
            try {
                return readAll(file);
            } catch (IOException unreadable) {
                // Fall through to the packaged defaults: labels stay usable and
                // a save rewrites the file.
            }
        }
        try (InputStream input = getAssets().open("payload/mods/state.toml")) {
            return readAll(input);
        } catch (IOException missing) {
            return "";
        }
    }

    private boolean saveSettings(SpokenUiSettings.Values values) {
        String updated = SpokenUiSettings.apply(stateText(), values);
        File file = stateFile();
        File directory = file.getParentFile();
        if (directory != null && !directory.isDirectory() && !directory.mkdirs()) return false;
        try {
            File temporary = File.createTempFile("state-", ".toml", directory);
            try (FileOutputStream output = new FileOutputStream(temporary)) {
                output.write(updated.getBytes(StandardCharsets.UTF_8));
                output.getFD().sync();
            }
            // rename(2) replaces the file atomically on Android's filesystems;
            // if the provider refuses, rewrite in place rather than leave the
            // player with no state file at all.
            if (temporary.renameTo(file)) return true;
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(updated.getBytes(StandardCharsets.UTF_8));
                output.getFD().sync();
            } finally {
                temporary.delete();
            }
            return true;
        } catch (IOException error) {
            return false;
        }
    }

    private static String readAll(File file) throws IOException {
        try (FileInputStream input = new FileInputStream(file)) {
            return readAll(input);
        }
    }

    private static String readAll(InputStream input) throws IOException {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) >= 0) {
            if (read > 0) out.write(buffer, 0, read);
        }
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private LinearLayout.LayoutParams params(int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT);
        layout.setMargins(left, top, right, bottom);
        return layout;
    }

    private int dip(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
