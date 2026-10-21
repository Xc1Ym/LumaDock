// Original installer artwork, drawn with macOS system fonts and AppKit.
// The multi-resolution TIFF stays sharp in Finder on Retina displays.
import AppKit

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let layout = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("scripts/dmg_layout.json"))) as! [String: Any]
let width = layout["width"] as! Int, height = layout["height"] as! Int
let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let version = CommandLine.arguments[2]
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let canvas = NSSize(width: width, height: height)
func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: r, green: g, blue: b, alpha: a)
}
let ink = color(0.09, 0.18, 0.23), muted = color(0.34, 0.43, 0.48), teal = color(0.01, 0.49, 0.54)

func render(scale: Int) -> NSBitmapImageRep {
    let cg = CGContext(data: nil, width: width * scale, height: height * scale, bitsPerComponent: 8,
                       bytesPerRow: width * scale * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                       bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    cg.translateBy(x: 0, y: CGFloat(height * scale)); cg.scaleBy(x: CGFloat(scale), y: -CGFloat(scale))
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: cg, flipped: true)
    defer { NSGraphicsContext.restoreGraphicsState() }
    func round(_ rect: NSRect, _ radius: CGFloat, fill: NSColor, stroke: NSColor? = nil) {
        let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
        fill.setFill(); path.fill()
        if let stroke { stroke.setStroke(); path.lineWidth = 1; path.stroke() }
    }
    func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat,
              _ weight: NSFont.Weight = .regular, _ foreground: NSColor = ink) {
        (value as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [
            .font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: foreground
        ])
    }
    func glow(_ x: CGFloat, _ y: CGFloat, _ radius: CGFloat, _ tint: NSColor) {
        let end = tint.withAlphaComponent(0)
        let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB),
                                  colors: [tint.cgColor, end.cgColor] as CFArray, locations: [0, 1])!
        cg.drawRadialGradient(gradient, startCenter: CGPoint(x:x,y:y), startRadius:0,
                              endCenter:CGPoint(x:x,y:y), endRadius:radius, options:[])
    }
    color(0.96, 0.98, 0.99).setFill(); NSRect(origin:.zero,size:canvas).fill()
    glow(20, 180, 390, color(0.57, 0.9, 0.88, 0.47))
    glow(790, 120, 430, color(0.64, 0.75, 0.98, 0.32))
    glow(670, 590, 390, color(0.77, 0.71, 0.98, 0.22))
    glow(250, 490, 330, color(1, 1, 1, 0.95))

    let logo = NSImage(contentsOf: root.appendingPathComponent("Assets/LumaDock.png"))!
    logo.draw(in:NSRect(x:54,y:30,width:48,height:48),from:.zero,operation:.sourceOver,fraction:1,respectFlipped:true,hints:nil)
    text("LumaDock", 114, 35, 31, .bold)
    text("璃游", 288, 47, 16, .medium, muted)
    round(NSRect(x:626,y:42,width:118,height:26),13,fill:color(1,1,1,0.62),stroke:color(1,1,1,0.9))
    text("MADE FOR MAC",640,49,10,.semibold,teal)
    text("Drag LumaDock to Applications.",60,110,21,.semibold)
    text("将璃游拖入 Applications 文件夹，即可安装。",60,143,13,.regular,muted)

    for (x, step) in [(96.0,"01  DRAG"),(480.0,"02  DROP")] {
        let rect=NSRect(x:x,y:182,width:224,height:192)
        cg.saveGState();cg.setShadow(offset:CGSize(width:0,height:8),blur:28,color:color(0.13,0.3,0.4,0.08).cgColor)
        round(rect,26,fill:color(1,1,1,0.58));cg.restoreGState()
        round(rect.insetBy(dx:0.5,dy:0.5),26,fill:color(1,1,1,0.1),stroke:color(1,1,1,0.95))
        text(step,CGFloat(x)+20,200,10,.semibold,muted)
    }
    let line=NSBezierPath();line.move(to:NSPoint(x:348,y:270));line.line(to:NSPoint(x:452,y:270))
    color(0.19,0.6,0.64,0.26).setStroke();line.lineWidth=1.5;line.stroke()
    round(NSRect(x:377,y:247,width:46,height:46),23,fill:color(1,1,1,0.9),stroke:color(0.81,0.91,0.93))
    let arrow=NSBezierPath();arrow.move(to:NSPoint(x:390,y:270));arrow.line(to:NSPoint(x:410,y:270))
    arrow.move(to:NSPoint(x:402,y:262));arrow.line(to:NSPoint(x:410,y:270));arrow.line(to:NSPoint(x:402,y:278))
    arrow.lineWidth=2;arrow.lineCapStyle = .round;arrow.lineJoinStyle = .round;teal.setStroke();arrow.stroke()

    let rule=NSBezierPath();rule.move(to:NSPoint(x:60,y:404));rule.line(to:NSPoint(x:510,y:404))
    color(0.75,0.83,0.86,0.55).setStroke();rule.lineWidth=1;rule.stroke()
    text("Open LumaDock from Applications.",60,427,15,.semibold)
    text("复制完成后，从“应用程序”打开璃游。",60,454,12,.regular,muted)
    text("Apple Silicon   ·   macOS 26+   ·   v"+version,60,505,11,.medium,muted)
    text("English / 简体中文",60,525,10,.regular,muted)
    text("GUIDES & LICENSES",611,391,9,.semibold,muted)

    let rep=NSBitmapImageRep(cgImage:cg.makeImage()!);rep.size=canvas
    return rep
}
let image=NSImage(size:canvas)
let regular=render(scale:1), retina=render(scale:2)
image.addRepresentation(regular);image.addRepresentation(retina)
try image.tiffRepresentation!.write(to:output.appendingPathComponent("installer-background.tiff"))
try retina.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent("installer-background@2x.png"))
print("Created original \(width)×\(height) point installer artwork (1× / 2×)")
