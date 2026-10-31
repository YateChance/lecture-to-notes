import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
let files = try FileManager.default.contentsOfDirectory(at: input, includingPropertiesForKeys: nil).filter {$0.pathExtension == "jpg"}.sorted {$0.lastPathComponent < $1.lastPathComponent}
FileManager.default.createFile(atPath: output.path, contents: nil)
let handle = try FileHandle(forWritingTo: output)
for (index, file) in files.enumerated() {
    autoreleasepool {
        do {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = false
            request.minimumTextHeight = 0.008
            let handler = VNImageRequestHandler(url: file, options: [:])
            try handler.perform([request])
            let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                let b = observation.boundingBox
                return ["text": candidate.string, "confidence": candidate.confidence, "bbox": [b.origin.x, b.origin.y, b.width, b.height]]
            }
            let record: [String: Any] = ["file": file.lastPathComponent, "lines": lines]
            let data = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
            handle.write(data)
            handle.write(Data("\n".utf8))
        } catch {
            fputs("OCR error \(file.lastPathComponent): \(error)\n", stderr)
        }
    }
    if (index + 1) % 25 == 0 { print("OCR \(index + 1)/\(files.count)"); fflush(stdout) }
}
try handle.close()
