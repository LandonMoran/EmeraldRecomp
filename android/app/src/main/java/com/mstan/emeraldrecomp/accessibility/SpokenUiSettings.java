// SpokenUiSettings — the three spoken-interface options, edited on the launcher.
//
// The options live in the engine's own mod state (mods/state.toml), which the
// game reads at start-up through gba_mod_option_value(). Editing that file from
// the setup screen therefore changes the setting the game will use, with the
// same ids and values the manifest declares:
//
//   game-text  on / off              speak the text the game prints
//   verbosity  everything / menus    everything = all printed text
//   rate       slow / normal / fast  Android text-to-speech speed
//
// Nothing here touches Android: the text in, text out shape keeps the TOML edit
// reviewable and testable on a plain JVM, and the edit is conservative — only
// the spoken-ui feature's own values change, every other package, feature,
// value and comment in the file is copied through unchanged.

package com.mstan.emeraldrecomp.accessibility;

import java.util.ArrayList;
import java.util.List;

public final class SpokenUiSettings {
    public static final String PACKAGE_ID = "pokemon-emerald.accessibility.spoken-ui";
    public static final String FEATURE_ID = "spoken-ui";

    public static final String GAME_TEXT = "game-text";
    public static final String VERBOSITY = "verbosity";
    public static final String RATE = "rate";

    /** The manifest's defaults, used when the state file says nothing. */
    public static final String DEFAULT_GAME_TEXT = "on";
    public static final String DEFAULT_VERBOSITY = "everything";
    public static final String DEFAULT_RATE = "normal";

    private static final String VALUES_HEADER = "[feature.values]";
    private static final String FEATURE_HEADER = "[[feature]]";

    private SpokenUiSettings() {}

    /** The three options as the file states them. */
    public static final class Values {
        public String gameText = DEFAULT_GAME_TEXT;
        public String verbosity = DEFAULT_VERBOSITY;
        public String rate = DEFAULT_RATE;
    }

    public static Values read(String stateText) {
        Values values = new Values();
        if (stateText == null || stateText.isEmpty()) return values;
        final List<String> lines = split(stateText);
        final int feature = featureBlockStart(lines);
        if (feature < 0) return values;
        final int valuesHeader = valuesHeader(lines, feature + 1, featureEnd(lines, feature));
        if (valuesHeader < 0) return values;
        final int end = blockEnd(lines, valuesHeader);
        for (int i = valuesHeader + 1; i < end; ++i) {
            final int equals = assignment(lines.get(i));
            if (equals < 0) continue;
            final String line = lines.get(i);
            final String key = unquote(line.substring(0, equals).trim());
            final String value = unquote(line.substring(equals + 1).trim());
            if (key.equals(GAME_TEXT)) values.gameText = value;
            else if (key.equals(VERBOSITY)) values.verbosity = value;
            else if (key.equals(RATE)) values.rate = value;
        }
        return values;
    }

    /**
     * Returns {@code stateText} with the three options set. A file without the
     * spoken-ui feature gains the blocks it needs, without an {@code enabled}
     * line so the feature keeps inheriting its own default; everything else in
     * the file is preserved.
     */
    public static String apply(String stateText, Values wanted) {
        final String text = stateText == null ? "" : stateText;
        final boolean trailingNewline = text.endsWith("\n");
        final List<String> lines = split(text);

        final int feature = featureBlockStart(lines);
        if (feature < 0) {
            appendFeature(lines, wanted);
        } else {
            final int end = featureEnd(lines, feature);
            final int valuesHeader = valuesHeader(lines, feature + 1, end);
            if (valuesHeader < 0) insertValues(lines, feature, end, wanted);
            else replaceValues(lines, valuesHeader, blockEnd(lines, valuesHeader), wanted);
        }

        final StringBuilder out = new StringBuilder(text.length() + 96);
        for (int i = 0; i < lines.size(); ++i) {
            out.append(lines.get(i));
            if (i + 1 < lines.size() || trailingNewline) out.append('\n');
        }
        return out.toString();
    }

    // ── Editing ───────────────────────────────────────────────────────────

    private static void appendFeature(List<String> lines, Values wanted) {
        if (!lines.isEmpty() && !lines.get(lines.size() - 1).trim().isEmpty()) lines.add("");
        lines.add("[[package]]");
        lines.add("id = \"" + PACKAGE_ID + "\"");
        lines.add("version = \"1.0.0\"");
        lines.add("");
        lines.add(FEATURE_HEADER);
        lines.add("package_id = \"" + PACKAGE_ID + "\"");
        lines.add("id = \"" + FEATURE_ID + "\"");
        lines.add("");
        lines.add(VALUES_HEADER);
        lines.add(entry(GAME_TEXT, wanted.gameText));
        lines.add(entry(VERBOSITY, wanted.verbosity));
        lines.add(entry(RATE, wanted.rate));
    }

    /** Adds the values section at the end of the feature's own lines. */
    private static void insertValues(List<String> lines, int feature, int end, Values wanted) {
        int at = end;
        while (at > feature + 1 && lines.get(at - 1).trim().isEmpty()) --at;
        lines.add(at, "");
        lines.add(at + 1, VALUES_HEADER);
        lines.add(at + 2, entry(GAME_TEXT, wanted.gameText));
        lines.add(at + 3, entry(VERBOSITY, wanted.verbosity));
        lines.add(at + 4, entry(RATE, wanted.rate));
    }

    /** Replaces the values the section already has, adding any it lacks. */
    private static void replaceValues(List<String> lines, int valuesHeader, int end, Values wanted) {
        int insertAt = valuesHeader + 1;
        for (int i = valuesHeader + 1; i < end; ++i) {
            if (assignment(lines.get(i)) >= 0) insertAt = i + 1;
        }
        final List<String> missing = new ArrayList<String>();
        final String[] keys = { GAME_TEXT, VERBOSITY, RATE };
        final String[] values = { wanted.gameText, wanted.verbosity, wanted.rate };
        for (int k = 0; k < keys.length; ++k) {
            int found = -1;
            for (int i = valuesHeader + 1; i < end; ++i) {
                final int equals = assignment(lines.get(i));
                if (equals < 0) continue;
                if (unquote(lines.get(i).substring(0, equals).trim()).equals(keys[k])) {
                    found = i;
                    break;
                }
            }
            if (found >= 0) lines.set(found, entry(keys[k], values[k]));
            else missing.add(entry(keys[k], values[k]));
        }
        if (!missing.isEmpty()) lines.addAll(insertAt, missing);
    }

    private static String entry(String key, String value) {
        return key + " = \"" + value + "\"";
    }

    // ── Line-level TOML helpers (the subset the engine writes) ────────────

    private static List<String> split(String text) {
        // A trailing newline is put back by the writer, not stored as an empty
        // final line, so the file does not grow a blank line per save.
        String body = text;
        if (body.endsWith("\n")) body = body.substring(0, body.length() - 1);
        final List<String> lines = new ArrayList<String>();
        if (body.isEmpty()) return lines;
        for (String line : body.split("\n", -1)) lines.add(line);
        return lines;
    }

    /** The line without its comment, trimmed — what the engine's reader compares. */
    private static String strip(String line) {
        final int hash = line.indexOf('#');
        return (hash >= 0 ? line.substring(0, hash) : line).trim();
    }

    private static boolean isHeader(String line) {
        return strip(line).startsWith("[");
    }

    private static int featureBlockStart(List<String> lines) {
        for (int i = 0; i < lines.size(); ++i) {
            if (!strip(lines.get(i)).equals(FEATURE_HEADER)) continue;
            final int end = featureEnd(lines, i);
            if (assignmentFor(lines, i + 1, end, "package_id", PACKAGE_ID) &&
                assignmentFor(lines, i + 1, end, "id", FEATURE_ID)) return i;
        }
        return -1;
    }

    /** The end of a feature block, counting its own [feature.values] section. */
    private static int featureEnd(List<String> lines, int feature) {
        int i = feature + 1;
        boolean values = false;
        while (i < lines.size()) {
            if (isHeader(lines.get(i))) {
                if (!values && strip(lines.get(i)).equals(VALUES_HEADER)) {
                    values = true;
                    ++i;
                    continue;
                }
                return i;
            }
            ++i;
        }
        return lines.size();
    }

    /** The end of any section: the next header, or the end of the file. */
    private static int blockEnd(List<String> lines, int header) {
        for (int i = header + 1; i < lines.size(); ++i) {
            if (isHeader(lines.get(i))) return i;
        }
        return lines.size();
    }

    private static int valuesHeader(List<String> lines, int from, int to) {
        for (int i = from; i < to; ++i) {
            if (strip(lines.get(i)).equals(VALUES_HEADER)) return i;
        }
        return -1;
    }

    private static boolean assignmentFor(List<String> lines, int from, int to,
                                         String key, String value) {
        for (int i = from; i < to; ++i) {
            final int equals = assignment(lines.get(i));
            if (equals < 0) continue;
            final String line = lines.get(i);
            if (unquote(line.substring(0, equals).trim()).equals(key) &&
                unquote(line.substring(equals + 1).trim()).equals(value)) return true;
        }
        return false;
    }

    /** Index of the assignment's '=' or -1; headers, blanks and comments are not values. */
    private static int assignment(String line) {
        final String stripped = strip(line);
        if (stripped.isEmpty() || stripped.startsWith("[")) return -1;
        final int equals = line.indexOf('=');
        if (equals < 0) return -1;
        final int hash = line.indexOf('#');
        if (hash >= 0 && hash < equals) return -1;
        return equals;
    }

    private static String unquote(String token) {
        if (token.length() < 2) return token;
        if (token.charAt(0) != '"' || token.charAt(token.length() - 1) != '"') return token;
        final StringBuilder out = new StringBuilder(token.length() - 2);
        for (int i = 1; i < token.length() - 1; ++i) {
            final char c = token.charAt(i);
            if (c == '\\' && i + 1 < token.length() - 1) {
                final char next = token.charAt(++i);
                if (next == 'n') out.append('\n');
                else if (next == 'r') out.append('\r');
                else if (next == 't') out.append('\t');
                else out.append(next);
                continue;
            }
            out.append(c);
        }
        return out.toString();
    }
}
