cmake_minimum_required(VERSION 3.24)
# macOS: universal binary (Apple Silicon + Intel). Must be set before project().
if(APPLE)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "" FORCE)
endif()

project(VoiceCast VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

include(FetchContent)

# JUCE (download once, cached in the build folder)
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.9
    GIT_SHALLOW ON
)

# Signalsmith Stretch: pitch + formant shifting (MIT)
FetchContent_Declare(
    signalsmith-stretch
    GIT_REPOSITORY https://github.com/Signalsmith-Audio/signalsmith-stretch.git
    GIT_TAG main
    GIT_SHALLOW ON
)

FetchContent_MakeAvailable(JUCE signalsmith-stretch)

juce_add_plugin(VoiceCast
    COMPANY_NAME "InstantVoice"
    PRODUCT_NAME "Instant Voicemod"
    BUNDLE_ID "com.instantvoice.plugin"
    PLUGIN_MANUFACTURER_CODE Vcst
    PLUGIN_CODE Vcs1
    # Windows Wave Link loads VST3. macOS Wave Link loads Audio Units only (AU is skipped on Windows).
    FORMATS VST3 AU Standalone
    AU_MAIN_TYPE kAudioUnitType_Effect
    MICROPHONE_PERMISSION_ENABLED TRUE
    MICROPHONE_PERMISSION_TEXT "Instant Voicemod processes your microphone in real time."
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    VST3_CATEGORIES Fx
)

target_sources(VoiceCast PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/VoiceChain.cpp
    Source/OscBridge.cpp
    Source/SoundPlayer.cpp
)

target_compile_definitions(VoiceCast PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_DISPLAY_SPLASH_SCREEN=0
)

target_link_libraries(VoiceCast
    PRIVATE
        juce::juce_audio_utils
        juce::juce_audio_formats
        juce::juce_dsp
        juce::juce_osc
        signalsmith-stretch
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)

# Background audio engine for the virtual-cable route (no Wave Link needed).
juce_add_gui_app(InstantVoiceEngine
    PRODUCT_NAME "InstantVoiceEngine"
    COMPANY_NAME "InstantVoice"
    BUNDLE_ID "com.instantvoice.engine"
    MICROPHONE_PERMISSION_ENABLED TRUE
    MICROPHONE_PERMISSION_TEXT "Instant Voicemod processes your microphone in real time."
    PLIST_TO_MERGE "<plist><dict><key>LSUIElement</key><true/></dict></plist>"
)
target_sources(InstantVoiceEngine PRIVATE
    Source/EngineMain.cpp
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/VoiceChain.cpp
    Source/OscBridge.cpp
    Source/SoundPlayer.cpp
)
target_compile_definitions(InstantVoiceEngine PRIVATE
    JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_APPLICATION_NAME_STRING="InstantVoiceEngine" JUCE_APPLICATION_VERSION_STRING="0.2.0")
target_link_libraries(InstantVoiceEngine PRIVATE
    juce::juce_audio_utils juce::juce_audio_formats juce::juce_dsp juce::juce_osc signalsmith-stretch
    PUBLIC juce::juce_recommended_config_flags)

# Optional offline test: cmake -DVOICECAST_TESTS=ON
option(VOICECAST_TESTS "Build the offline DSP test" OFF)
if(VOICECAST_TESTS)
    juce_add_console_app(VoiceCastTest PRODUCT_NAME "VoiceCastTest")
    target_sources(VoiceCastTest PRIVATE tests/OfflineTest.cpp Source/PluginProcessor.cpp
                   Source/PluginEditor.cpp Source/VoiceChain.cpp Source/OscBridge.cpp Source/SoundPlayer.cpp)
    target_compile_definitions(VoiceCastTest PRIVATE JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
    target_link_libraries(VoiceCastTest PRIVATE juce::juce_audio_utils juce::juce_audio_formats juce::juce_dsp juce::juce_osc
                          signalsmith-stretch PUBLIC juce::juce_recommended_config_flags)
endif()
