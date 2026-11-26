package com.mstan.emeraldrecomp.accessibility;

import android.app.Activity;
import android.content.res.AssetFileDescriptor;
import android.content.res.AssetManager;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.SoundPool;
import android.media.ToneGenerator;
import android.util.Log;

import java.util.HashMap;

/**
 * Plays the accessibility audio cues for the Emerald spoken interface.
 *
 * <p>The native layer decides <em>which</em> event happened and calls
 * {@code play(asset)} through the JNI bridge; this class only turns an asset
 * name into a sound. Every asset is CC0; sources, authors, licenses and hashes
 * are documented in {@code docs/a11y-sfx.md}. Sounds play through the
 * accessibility audio usage, never through the game's own audio path, and
 * Emerald's music, sound effects and menus are untouched.
 *
 * <p>When an asset is missing (or the platform refuses the stream) a short
 * synthesized tone stands in, so a packaging mistake degrades the cue instead
 * of silencing it.
 */
public final class A11yCues {
    private static final String TAG = "EmeraldA11yCues";
    private static final String DIR = "a11y/sfx/";

    private static final HashMap<String, Integer> sIds = new HashMap<>();
    private static AssetManager sAssets;
    private static SoundPool sPool;
    private static ToneGenerator sTones;
    private static boolean sEnabled = true;

    private A11yCues() {}

    /** Called from the native bridge once the activity exists. */
    static boolean attach(Activity activity) {
        try {
            sAssets = activity.getAssets();
            final AudioAttributes attrs = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            sPool = new SoundPool.Builder()
                    .setMaxStreams(2)
                    .setAudioAttributes(attrs)
                    .build();
            sTones = new ToneGenerator(AudioManager.STREAM_ACCESSIBILITY, 60);
            return true;
        } catch (Throwable t) {
            Log.w(TAG, "cue audio unavailable", t);
            return false;
        }
    }

    /** Play one cue asset ("door", "stairs_up", "ok", ...). */
    static void play(String asset) {
        if (!sEnabled || asset == null || asset.isEmpty()) return;
        int id = load(asset);
        if (id != 0 && sPool != null) {
            sPool.play(id, 1.0f, 1.0f, 1, 0, 1.0f);
            return;
        }
        fallback(asset);
    }

    static void setEnabled(boolean on) {
        sEnabled = on;
    }

    static boolean isEnabled() {
        return sEnabled;
    }

    static void shutdown() {
        if (sPool != null) {
            sPool.release();
            sPool = null;
        }
        if (sTones != null) {
            sTones.release();
            sTones = null;
        }
        sIds.clear();
        sAssets = null;
    }

    private static int load(String asset) {
        Integer cached = sIds.get(asset);
        if (cached != null) return cached;
        int id = 0;
        if (sAssets != null && sPool != null) {
            try (AssetFileDescriptor fd = sAssets.openFd(DIR + asset + ".ogg")) {
                id = sPool.load(fd, 1);
            } catch (Throwable t) {
                // Missing asset: recorded once, then the tone fallback covers it.
                Log.i(TAG, "no asset for cue '" + asset + "', using synthesized tone");
            }
        }
        sIds.put(asset, id);
        return id;
    }

    /** Synthesized stand-in, chosen per event class so the cues stay distinct. */
    private static void fallback(String asset) {
        if (sTones == null) return;
        int tone;
        switch (asset) {
            case "fail":
                tone = ToneGenerator.TONE_PROP_NACK;
                break;
            case "ok":
            case "target":
                tone = ToneGenerator.TONE_PROP_ACK;
                break;
            case "item":
                tone = ToneGenerator.TONE_PROP_BEEP2;
                break;
            case "door":
            case "map":
                tone = ToneGenerator.TONE_PROP_PROMPT;
                break;
            case "stairs_up":
                tone = ToneGenerator.TONE_DTMF_9;
                break;
            case "stairs_down":
                tone = ToneGenerator.TONE_DTMF_6;
                break;
            case "npc":
                tone = ToneGenerator.TONE_PROP_BEEP;
                break;
            case "object":
            default:
                tone = ToneGenerator.TONE_PROP_BEEP;
                break;
        }
        try {
            sTones.startTone(tone, 90);
        } catch (Throwable t) {
            Log.w(TAG, "tone fallback failed", t);
        }
    }
}
