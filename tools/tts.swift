/// Mandarin TTS helper — uses AVSpeechSynthesizer to access Siri/Premium voices.
/// Usage:
///   tts "你好"                     — speak to speakers (default voice)
///   tts "你好" --voice Yu-shu      — speak with specific voice
///   tts "你好" --rate 0.42         — speak at specific rate (0.0-1.0)
///   tts "你好" -o /tmp/out.wav     — render to WAV file (no playback)
///   tts --list                     — list available zh-CN voices

import AVFoundation
import Foundation

// MARK: - Voice lookup

func findVoice(name: String?) -> AVSpeechSynthesisVoice? {
    let zhVoices = AVSpeechSynthesisVoice.speechVoices().filter {
        $0.language.hasPrefix("zh-CN")
    }
    if let name = name {
        if let v = zhVoices.first(where: { $0.name.lowercased() == name.lowercased() }) {
            return v
        }
        if let v = zhVoices.first(where: { $0.name.lowercased().contains(name.lowercased()) }) {
            return v
        }
    }
    // Prefer premium > enhanced > standard, prefer Yu-shu
    let sorted = zhVoices.sorted { a, b in
        if a.quality.rawValue != b.quality.rawValue {
            return a.quality.rawValue > b.quality.rawValue
        }
        if a.name.contains("Yu") && !b.name.contains("Yu") { return true }
        if !a.name.contains("Yu") && b.name.contains("Yu") { return false }
        return a.name < b.name
    }
    return sorted.first
}

// MARK: - Speak to speakers

func speakLive(text: String, voice: AVSpeechSynthesisVoice, rate: Float) {
    let synth = AVSpeechSynthesizer()
    let sem = DispatchSemaphore(value: 0)

    class Delegate: NSObject, AVSpeechSynthesizerDelegate {
        let sem: DispatchSemaphore
        init(sem: DispatchSemaphore) { self.sem = sem }
        func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
            sem.signal()
        }
        func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) {
            sem.signal()
        }
    }
    let delegate = Delegate(sem: sem)
    synth.delegate = delegate

    let utterance = AVSpeechUtterance(string: text)
    utterance.voice = voice
    utterance.rate = rate
    synth.speak(utterance)
    sem.wait()
}

// MARK: - Render to WAV file

func renderToFile(text: String, voice: AVSpeechSynthesisVoice, rate: Float, path: String) {
    let synth = AVSpeechSynthesizer()
    let sem = DispatchSemaphore(value: 0)
    let url = URL(fileURLWithPath: path)

    let utterance = AVSpeechUtterance(string: text)
    utterance.voice = voice
    utterance.rate = rate

    try? FileManager.default.removeItem(at: url)

    var audioFile: AVAudioFile? = nil
    var gotData = false

    synth.write(utterance) { buffer in
        guard let pcm = buffer as? AVAudioPCMBuffer else {
            // nil/non-PCM buffer = synthesis complete
            sem.signal()
            return
        }
        if pcm.frameLength == 0 {
            // Empty buffer = synthesis complete
            sem.signal()
            return
        }
        gotData = true
        do {
            if audioFile == nil {
                audioFile = try AVAudioFile(
                    forWriting: url,
                    settings: pcm.format.settings
                )
            }
            try audioFile!.write(from: pcm)
        } catch {
            fputs("Write error: \(error.localizedDescription)\n", stderr)
            sem.signal()
        }
    }

    // Wait up to 30 seconds
    let result = sem.wait(timeout: .now() + 30)
    audioFile = nil  // Close file

    if result == .timedOut {
        fputs("Timeout rendering audio\n", stderr)
        exit(1)
    }
    if !gotData {
        fputs("No audio data generated\n", stderr)
        exit(1)
    }
}

// MARK: - Main

let args = CommandLine.arguments

if args.contains("--list") {
    let voices = AVSpeechSynthesisVoice.speechVoices().filter {
        $0.language.hasPrefix("zh-CN")
    }.sorted { a, b in
        if a.quality.rawValue != b.quality.rawValue {
            return a.quality.rawValue > b.quality.rawValue
        }
        return a.name < b.name
    }
    for v in voices {
        let q: String
        switch v.quality.rawValue {
        case 1: q = "standard"
        case 2: q = "enhanced"
        case 3: q = "premium"
        default: q = "q=\(v.quality.rawValue)"
        }
        print("\(v.name)\t\(q)\t\(v.identifier)")
    }
    exit(0)
}

var text: String? = nil
var voiceName: String? = nil
var rate: Float = 0.42
var outputPath: String? = nil

var i = 1
while i < args.count {
    switch args[i] {
    case "--voice": i += 1; voiceName = args[i]
    case "--rate":  i += 1; rate = Float(args[i]) ?? 0.42
    case "-o":      i += 1; outputPath = args[i]
    default:        if text == nil { text = args[i] }
    }
    i += 1
}

guard let speakText = text else {
    fputs("Usage: tts \"text\" [--voice name] [--rate 0.0-1.0] [-o file.wav]\n", stderr)
    fputs("       tts --list\n", stderr)
    exit(1)
}

guard let voice = findVoice(name: voiceName) else {
    fputs("No zh-CN voice available.\n", stderr)
    exit(1)
}

if let path = outputPath {
    renderToFile(text: speakText, voice: voice, rate: rate, path: path)
} else {
    speakLive(text: speakText, voice: voice, rate: rate)
}
