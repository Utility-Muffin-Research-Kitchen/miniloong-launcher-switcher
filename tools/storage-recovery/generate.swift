// Renders the rootfs SD repair screens shown by loong_transition before any
// card content is available. Run from the repo root:
//   swift tools/storage-recovery/generate.swift
import AppKit

let width = 960
let height = 720

struct Screen {
    let dir: String
    let title: String
    let body: String
}

let screens = [
    Screen(dir: "device/mlp1/storage-recovery/checking/0",
           title: "Checking your SD card",
           body: "Keep your device connected to power.\nThis can take a few minutes."),
    Screen(dir: "device/mlp1/storage-recovery/failed/0",
           title: "Your SD card couldn't be repaired.",
           body: "Turn off your device and check the card on a computer."),
]

func render(_ screen: Screen) throws {
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                     isPlanar: false, colorSpaceName: .deviceRGB,
                                     bytesPerRow: 0, bitsPerPixel: 0) else {
        throw NSError(domain: "render", code: 1)
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSColor.black.setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()

    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineSpacing = 8
    let titleAttrs: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 44, weight: .semibold),
        .foregroundColor: NSColor.white,
        .paragraphStyle: paragraph,
    ]
    let bodyAttrs: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 30, weight: .regular),
        .foregroundColor: NSColor(white: 0.82, alpha: 1.0),
        .paragraphStyle: paragraph,
    ]
    let margin = 72.0
    let box = NSRect(x: margin, y: 0, width: Double(width) - margin * 2, height: Double(height))
    let title = NSAttributedString(string: screen.title, attributes: titleAttrs)
    let body = NSAttributedString(string: screen.body, attributes: bodyAttrs)
    let titleSize = title.boundingRect(with: box.size, options: [.usesLineFragmentOrigin])
    let bodySize = body.boundingRect(with: box.size, options: [.usesLineFragmentOrigin])
    let gap = 28.0
    let total = titleSize.height + gap + bodySize.height
    let top = (Double(height) + total) / 2
    title.draw(with: NSRect(x: margin, y: top - titleSize.height, width: box.width, height: titleSize.height),
               options: [.usesLineFragmentOrigin])
    body.draw(with: NSRect(x: margin, y: top - titleSize.height - gap - bodySize.height,
                           width: box.width, height: bodySize.height),
              options: [.usesLineFragmentOrigin])
    NSGraphicsContext.restoreGraphicsState()

    try FileManager.default.createDirectory(atPath: screen.dir, withIntermediateDirectories: true)
    guard let png = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "render", code: 2)
    }
    try png.write(to: URL(fileURLWithPath: screen.dir + "/0.png"))
}

for screen in screens {
    try render(screen)
    print("wrote \(screen.dir)/0.png")
}
