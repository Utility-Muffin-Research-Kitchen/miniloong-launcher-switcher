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
           body: "Your device is checking the card before saving is enabled.\nThis can take a few minutes."),
    Screen(dir: "device/mlp1/storage-recovery/repairing/0",
           title: "Repairing your SD card",
           body: "Keep your device connected to power and leave the card in.\nThis can take several minutes."),
    Screen(dir: "device/mlp1/storage-recovery/failed/0",
           title: "Your SD card is still protected",
           body: "Turn off your device and repair the card on a computer.\nSafely eject it, then insert it and turn your device on."),
    // Shutdown pauses. Hold times match POWER_HOLD_CS in umrk-leaf-session.
    Screen(dir: "device/mlp1/storage-recovery/paused-app/0",
           title: "An app didn't close",
           body: "It may not have saved everything. Leaf is waiting for it.\nTo turn off anyway, hold the power button for 2 seconds."),
    Screen(dir: "device/mlp1/storage-recovery/paused-recording/0",
           title: "Saving your recording",
           body: "Leaf is still converting a screen recording.\nTo turn off anyway, hold the power button for 2 seconds.\nThe recording may not finish converting."),
    Screen(dir: "device/mlp1/storage-recovery/paused-storage/0",
           title: "Shutdown paused",
           body: "Something is still saving to your SD card.\nLeaf will keep trying. To try again now, press the power button."),
    Screen(dir: "device/mlp1/storage-recovery/paused-storage-force/0",
           title: "Still can't finish saving",
           body: "To try again, press the power button.\nTo turn off anyway, hold it for 2 seconds.\nLeaf will check your SD card the next time you turn it on."),
    Screen(dir: "device/mlp1/storage-recovery/paused-no-force/0",
           title: "Shutdown paused",
           body: "Leaf couldn't prepare a safe way to turn off.\nTo try again, press the power button."),
    Screen(dir: "device/mlp1/storage-recovery/forcing/0",
           title: "Turning off",
           body: "Leaf will check your SD card the next time you turn it on."),
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
