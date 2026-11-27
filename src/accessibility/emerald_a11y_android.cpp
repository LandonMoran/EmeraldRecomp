// emerald_a11y_android.cpp — Android TextToSpeech bridge.
//
// Compiled only for Android. SDLActivity loads libmain.so, so SDL's Java
// environment (and the activity) are available without the engine shell needing
// to know this layer exists.
//
// Native → Java: speak/stopSpeech/setRate on
// com.mstan.emeraldrecomp.accessibility.EmeraldAccessibility, plus the slot
// hotkey the runtime reads for save states.
//
// There is no accessibility node tree over the game screen: with nodes in the
// tree TalkBack takes the controls (pad, keyboard, touch) and the game becomes
// unplayable with a controller. The game speaks through its own TextToSpeech
// and the screen is hidden from accessibility services; the launcher before the
// game keeps its stock widgets and is TalkBack-navigable as usual.

#include "emerald_a11y.h"

#include "emerald_cues.h"   // audio-cue sink (SoundPool on the Java side)

#if defined(__ANDROID__)

#include <SDL.h>
#include <android/log.h>
#include <jni.h>

namespace emerald::accessibility {
namespace {

constexpr const char* kTag = "EmeraldA11y";
// Dot-separated: resolved through the activity's ClassLoader (FindClass on a
// native thread does not see application classes).
constexpr const char* kClass =
    "com.mstan.emeraldrecomp.accessibility.EmeraldAccessibility";
// Audio cues live in their own class: the C++ cue table names an asset, the
// Java player turns it into sound (or a synthesized fallback).
constexpr const char* kCuesClass = "com.mstan.emeraldrecomp.accessibility.A11yCues";

JavaVM* g_vm = nullptr;
jobject g_activity = nullptr;
jclass g_class = nullptr;
jclass g_cues = nullptr;
jmethodID g_cue_play = nullptr;
jmethodID g_cue_attach = nullptr;
jmethodID g_cue_shutdown = nullptr;
jmethodID g_speak = nullptr;
jmethodID g_stop = nullptr;
jmethodID g_rate = nullptr;
jmethodID g_attach = nullptr;
jmethodID g_shutdown = nullptr;
bool g_ready = false;

bool clear(JNIEnv* e) {
    if (!e || !e->ExceptionCheck()) return false;
    e->ExceptionDescribe();
    e->ExceptionClear();
    return true;
}

JNIEnv* env() {
    if (!g_vm) return nullptr;
    JNIEnv* e = nullptr;
    const jint status = g_vm->GetEnv(reinterpret_cast<void**>(&e), JNI_VERSION_1_6);
    if (status == JNI_OK) return e;
    if (status == JNI_EDETACHED && g_vm->AttachCurrentThread(&e, nullptr) == JNI_OK)
        return e;
    return nullptr;
}

// Resolve an application class through the activity's ClassLoader (FindClass on
// a native thread cannot see application classes).
jclass load_app_class(JNIEnv* e, jobject activity, const char* name) {
    jclass activity_class = e->GetObjectClass(activity);
    jmethodID get_loader = e->GetMethodID(activity_class, "getClassLoader",
                                         "()Ljava/lang/ClassLoader;");
    jobject loader = get_loader ? e->CallObjectMethod(activity, get_loader) : nullptr;
    jclass loader_class = loader ? e->GetObjectClass(loader) : nullptr;
    jmethodID load_class =
        loader_class ? e->GetMethodID(loader_class, "loadClass",
                                      "(Ljava/lang/String;)Ljava/lang/Class;")
                     : nullptr;
    jstring jname = e->NewStringUTF(name);
    jclass cls = (load_class && jname)
                     ? static_cast<jclass>(e->CallObjectMethod(loader, load_class, jname))
                     : nullptr;
    if (jname) e->DeleteLocalRef(jname);
    if (loader_class) e->DeleteLocalRef(loader_class);
    if (loader) e->DeleteLocalRef(loader);
    if (activity_class) e->DeleteLocalRef(activity_class);
    if (!cls) clear(e);
    return cls;
}

// Native cue sink: the asset name travels as a string; speech is already routed
// through android_speak() by the cue layer, so `say` is not repeated here.
void android_cue(const char* asset, const char*, int) {
    if (!g_ready || !g_cues || !g_cue_play || !asset) return;
    JNIEnv* e = env();
    if (!e) return;
    jstring value = e->NewStringUTF(asset);
    if (value) {
        e->CallStaticVoidMethod(g_cues, g_cue_play, value);
        e->DeleteLocalRef(value);
    }
    clear(e);
}

void android_speak(const char* text, int interrupt) {
    if (!g_ready || !g_class || !text) return;
    JNIEnv* e = env();
    if (!e) return;
    jstring value = e->NewStringUTF(text);
    if (value) {
        e->CallStaticVoidMethod(g_class, g_speak, value, static_cast<jint>(interrupt));
        e->DeleteLocalRef(value);
    }
    clear(e);
}

void android_stop() {
    if (!g_ready || !g_class || !g_stop) return;
    JNIEnv* e = env();
    if (!e) return;
    e->CallStaticVoidMethod(g_class, g_stop);
    clear(e);
}

void android_rate(float rate) {
    if (!g_ready || !g_class || !g_rate) return;
    JNIEnv* e = env();
    if (!e) return;
    e->CallStaticVoidMethod(g_class, g_rate, static_cast<jfloat>(rate));
    clear(e);
}

// Save states are host events: the runtime takes them from its settings menu or
// from the edge-triggered F1..F9 / Shift+F1..F9 slot hotkeys (host_window.cpp),
// and a game cannot call its snapshot code. This delivers that same key to the
// queue the pads and touches arrive on. SDL_PushEvent is safe off the main
// thread, which is where the layer runs (the guest frame callback).
void android_slot_hotkey(int slot, int save) {
    if (slot < 1 || slot > 9) return;
    const int index = slot - 1;
    SDL_Event down;
    SDL_zero(down);
    down.type = SDL_KEYDOWN;
    down.key.timestamp = SDL_GetTicks();
    down.key.state = SDL_PRESSED;
    down.key.keysym.scancode = static_cast<SDL_Scancode>(SDL_SCANCODE_F1 + index);
    down.key.keysym.sym = static_cast<SDL_Keycode>(SDLK_F1 + index);
    down.key.keysym.mod = save ? KMOD_LSHIFT : KMOD_NONE;
    SDL_PushEvent(&down);
    // Release it too, so the host does not keep the slot key held for the next
    // pump; the hotkey itself is edge-triggered on the key-down.
    SDL_Event up = down;
    up.type = SDL_KEYUP;
    up.key.state = SDL_RELEASED;
    SDL_PushEvent(&up);
}

}  // namespace

bool install_platform_bridge() {
    if (g_ready) return true;
    JNIEnv* e = static_cast<JNIEnv*>(SDL_AndroidGetJNIEnv());
    if (!e || e->GetJavaVM(&g_vm) != JNI_OK) {
        __android_log_print(ANDROID_LOG_WARN, kTag, "no JNI environment");
        return false;
    }
    jobject activity = static_cast<jobject>(SDL_AndroidGetActivity());
    if (!activity) {
        __android_log_print(ANDROID_LOG_WARN, kTag, "no activity");
        return false;
    }

    jclass cls = load_app_class(e, activity, kClass);
    if (!cls) {
        clear(e);
        __android_log_print(ANDROID_LOG_WARN, kTag, "accessibility class not found");
        return false;
    }

    g_speak = e->GetStaticMethodID(cls, "speak", "(Ljava/lang/String;I)V");
    g_stop = e->GetStaticMethodID(cls, "stopSpeech", "()V");
    g_rate = e->GetStaticMethodID(cls, "setRate", "(F)V");
    g_attach = e->GetStaticMethodID(cls, "attach", "(Landroid/app/Activity;)Z");
    g_shutdown = e->GetStaticMethodID(cls, "shutdown", "()V");
    if (clear(e) || !g_speak || !g_stop || !g_rate || !g_attach) {
        e->DeleteLocalRef(cls);
        __android_log_print(ANDROID_LOG_WARN, kTag, "accessibility methods missing");
        return false;
    }

    g_class = static_cast<jclass>(e->NewGlobalRef(cls));
    g_activity = e->NewGlobalRef(activity);
    e->DeleteLocalRef(cls);
    const jboolean attached = e->CallStaticBooleanMethod(g_class, g_attach, g_activity);
    if (clear(e) || !attached) {
        __android_log_print(ANDROID_LOG_WARN, kTag, "attach failed");
        return false;
    }

    install_sink(&android_speak, &android_stop, &android_rate);
    install_slot_hotkey(&android_slot_hotkey);

    // Audio cues: same attachment point, separate class, never fatal.
    jclass cues = load_app_class(e, activity, kCuesClass);
    if (cues) {
        g_cue_play = e->GetStaticMethodID(cues, "play", "(Ljava/lang/String;)V");
        g_cue_attach = e->GetStaticMethodID(cues, "attach", "(Landroid/app/Activity;)Z");
        g_cue_shutdown = e->GetStaticMethodID(cues, "shutdown", "()V");
        if (clear(e) || !g_cue_play || !g_cue_attach) {
            g_cue_play = nullptr;
            g_cue_attach = nullptr;
            g_cue_shutdown = nullptr;
        } else {
            g_cues = static_cast<jclass>(e->NewGlobalRef(cues));
            e->CallStaticBooleanMethod(g_cues, g_cue_attach, g_activity);
            clear(e);
            install_cue_sink(&android_cue);
        }
        e->DeleteLocalRef(cues);
    } else {
        __android_log_print(ANDROID_LOG_WARN, kTag, "cue player not found; cues log only");
    }

    g_ready = true;
    __android_log_print(ANDROID_LOG_INFO, kTag, "spoken UI bridge attached");
    return true;
}

void shutdown_platform_bridge() {
    if (!g_ready) return;
    if (g_class && g_shutdown) {
        JNIEnv* e = env();
        if (e) {
            e->CallStaticVoidMethod(g_class, g_shutdown);
            clear(e);
        }
    }
    install_sink(nullptr, nullptr, nullptr);
    install_slot_hotkey(nullptr);
    install_cue_sink(nullptr);
    JNIEnv* e = env();
    if (e) {
        if (g_cues && g_cue_shutdown) {
            e->CallStaticVoidMethod(g_cues, g_cue_shutdown);
            clear(e);
        }
        if (g_cues) e->DeleteGlobalRef(g_cues);
        if (g_class) e->DeleteGlobalRef(g_class);
        if (g_activity) e->DeleteGlobalRef(g_activity);
    }
    g_cues = nullptr;
    g_cue_play = g_cue_attach = g_cue_shutdown = nullptr;
    g_class = nullptr;
    g_activity = nullptr;
    g_speak = g_stop = g_rate = g_attach = g_shutdown = nullptr;
    g_ready = false;
}

}  // namespace emerald::accessibility

#endif  // __ANDROID__
