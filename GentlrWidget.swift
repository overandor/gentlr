import AppKit
import Foundation

let gentlrRoot = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent().path
let gentlrPython = "\(gentlrRoot)/.venv/bin/python"
let gentlrScript = "\(gentlrRoot)/gentlr.py"

final class OrganismView: NSView {
    var pressure: CGFloat = 0.0
    var phase: CGFloat = 0.0

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.035, green: 0.065, blue: 0.055, alpha: 0.94).setFill()
        dirtyRect.fill()

        let center = CGPoint(x: bounds.midX, y: bounds.midY)
        let radius = CGFloat(42.0 + 18.0 * pressure)
        let path = NSBezierPath()
        for i in 0..<36 {
            let angle = CGFloat(i) / 36.0 * CGFloat.pi * 2.0
            let pulse = CGFloat(1.0 + 0.12 * sin(Double(phase + CGFloat(i) * 0.74)))
            let r = radius * pulse
            let point = CGPoint(x: center.x + cos(angle) * r, y: center.y + sin(angle) * r)
            if i == 0 { path.move(to: point) } else { path.line(to: point) }
        }
        path.close()

        NSColor(calibratedRed: 0.07, green: 0.24, blue: 0.18, alpha: 0.92).setFill()
        path.fill()
        (pressure < 0.72 ? NSColor(calibratedRed: 0.45, green: 0.94, blue: 0.70, alpha: 1.0) : NSColor(calibratedRed: 1.0, green: 0.82, blue: 0.42, alpha: 1.0)).setStroke()
        path.lineWidth = 2.0
        path.stroke()

        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.boldSystemFont(ofSize: 34),
            .foregroundColor: NSColor(calibratedRed: 0.88, green: 0.98, blue: 0.93, alpha: 1.0)
        ]
        NSString(string: "g").draw(at: CGPoint(x: center.x - 10, y: center.y - 21), withAttributes: attrs)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var organism: OrganismView!
    var statsLabel: NSTextField!
    var itemsLabel: NSTextField!
    var statusItem: NSStatusItem!
    var timer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        buildMenu()
        buildWindow()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    func buildMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "gentlr"
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Show Widget", action: #selector(showWidget), keyEquivalent: "s"))
        menu.addItem(NSMenuItem(title: "Train Real ML", action: #selector(train), keyEquivalent: "t"))
        menu.addItem(NSMenuItem(title: "Dry Refresh", action: #selector(refresh), keyEquivalent: "r"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    func buildWindow() {
        let rect = NSRect(x: 46, y: 420, width: 360, height: 470)
        window = NSWindow(contentRect: rect, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isMovableByWindowBackground = true

        let root = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 470))
        root.wantsLayer = true
        root.layer?.cornerRadius = 18
        root.layer?.backgroundColor = NSColor(calibratedRed: 0.035, green: 0.065, blue: 0.055, alpha: 0.94).cgColor
        window.contentView = root

        let title = label("gentlr", size: 28, weight: .bold)
        title.frame = NSRect(x: 22, y: 420, width: 210, height: 34)
        root.addSubview(title)

        let close = button("x", action: #selector(hideWidget))
        close.frame = NSRect(x: 314, y: 424, width: 28, height: 26)
        root.addSubview(close)

        organism = OrganismView(frame: NSRect(x: 90, y: 270, width: 180, height: 140))
        organism.wantsLayer = true
        organism.layer?.cornerRadius = 12
        root.addSubview(organism)

        statsLabel = label("warming up...", size: 12, weight: .regular)
        statsLabel.frame = NSRect(x: 22, y: 206, width: 316, height: 58)
        root.addSubview(statsLabel)

        itemsLabel = label("", size: 11, weight: .regular)
        itemsLabel.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        itemsLabel.frame = NSRect(x: 22, y: 76, width: 316, height: 122)
        root.addSubview(itemsLabel)

        let trainButton = button("Train", action: #selector(train))
        trainButton.frame = NSRect(x: 22, y: 24, width: 72, height: 34)
        root.addSubview(trainButton)
        let dryButton = button("Dry", action: #selector(refresh))
        dryButton.frame = NSRect(x: 104, y: 24, width: 72, height: 34)
        root.addSubview(dryButton)
        let applyButton = button("Apply 1", action: #selector(applyOne))
        applyButton.frame = NSRect(x: 186, y: 24, width: 72, height: 34)
        root.addSubview(applyButton)
        let quitButton = button("Quit", action: #selector(quit))
        quitButton.frame = NSRect(x: 268, y: 24, width: 70, height: 34)
        root.addSubview(quitButton)

        window.makeKeyAndOrderFront(nil)
    }

    func label(_ text: String, size: CGFloat, weight: NSFont.Weight) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.textColor = NSColor(calibratedRed: 0.88, green: 0.98, blue: 0.93, alpha: 1.0)
        field.font = NSFont.systemFont(ofSize: size, weight: weight)
        field.lineBreakMode = .byWordWrapping
        return field
    }

    func button(_ text: String, action: Selector) -> NSButton {
        let b = NSButton(title: text, target: self, action: action)
        b.bezelStyle = .rounded
        return b
    }

    @objc func showWidget() { window.makeKeyAndOrderFront(nil) }
    @objc func hideWidget() { window.orderOut(nil) }
    @objc func quit() { NSApp.terminate(nil) }

    @objc func train() {
        DispatchQueue.global(qos: .utility).async {
            _ = self.runGentlr(["--train", "--json", "--limit", "6"])
            DispatchQueue.main.async { self.refresh() }
        }
    }

    @objc func applyOne() {
        DispatchQueue.global(qos: .utility).async {
            _ = self.runGentlr(["--apply", "--threshold", "0.94", "--max-kill", "1", "--limit", "6"])
            DispatchQueue.main.async { self.refresh() }
        }
    }

    @objc func refresh() {
        DispatchQueue.global(qos: .utility).async {
            let output = self.runGentlr(["--json", "--limit", "6"])
            DispatchQueue.main.async { self.render(output) }
        }
    }

    func tick() {
        organism.phase += 0.22
        organism.needsDisplay = true
        refresh()
    }

    func runGentlr(_ args: [String]) -> String {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: gentlrPython)
        task.arguments = [gentlrScript] + args
        task.currentDirectoryURL = URL(fileURLWithPath: gentlrRoot)
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8) ?? ""
        } catch {
            return "\(error)"
        }
    }

    func render(_ jsonText: String) {
        guard let data = jsonText.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ok = obj["ok"] as? Bool,
              ok else {
            statsLabel.stringValue = "snapshot unavailable"
            itemsLabel.stringValue = jsonText.prefix(220).description
            return
        }
        let used = obj["used_pct"] as? Double ?? 0
        let avail = obj["available_mb"] as? Double ?? 0
        let samples = obj["samples"] as? Int ?? 0
        let candidates = obj["candidates"] as? Int ?? 0
        organism.pressure = CGFloat(used / 100.0)
        organism.needsDisplay = true
        statsLabel.stringValue = String(format: "memory %.1f%%    available %.0f MB\nsamples %d    candidates %d", used, avail, samples, candidates)
        let items = obj["items"] as? [[String: Any]] ?? []
        itemsLabel.stringValue = items.map { item in
            let score = item["score"] as? Double ?? 0
            let rss = item["rss_mb"] as? Double ?? 0
            let name = item["name"] as? String ?? "?"
            return String(format: "%.2f %7.1f MB  %@", score, rss, String(name.prefix(23)))
        }.joined(separator: "\n")
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
