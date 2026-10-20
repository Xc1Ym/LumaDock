import SwiftUI
import AppKit

enum Brand {
    static let name = "璃游"
    static let latinName = "LumaDock"
    static let accent = Color(red:0.02,green:0.53,blue:0.57)
}

struct BrandMark: View {
    var size: CGFloat = 48
    var body: some View {
        Group {
            if let icon = NSImage(contentsOf:Bundle.main.resourceURL?.appendingPathComponent("LumaDock.icns") ?? URL(fileURLWithPath:"/")) {
                Image(nsImage:icon).resizable().scaledToFit()
            } else {
                Image(systemName:"play.square.stack.fill").resizable().scaledToFit().foregroundStyle(Brand.accent.gradient).padding(size*0.12)
            }
        }.frame(width:size,height:size).accessibilityHidden(true)
    }
}

/// The operating system owns the glass rendering, including increased contrast.
/// Reduce Transparency gets an opaque surface without the decorative light field.
struct LibraryBackdrop: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    var body: some View {
        ZStack {
            Color(nsColor:.windowBackgroundColor)
            if !reduceTransparency {
                RadialGradient(colors:[Brand.accent.opacity(0.11),.clear],center:.topLeading,startRadius:0,endRadius:650)
                RadialGradient(colors:[Color.indigo.opacity(0.07),.clear],center:.bottomTrailing,startRadius:0,endRadius:500)
            }
        }.ignoresSafeArea().allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct GlassSurface: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    var radius: CGFloat
    func body(content:Content)->some View {
        if reduceTransparency {
            content.background(Color(nsColor:.windowBackgroundColor),in:RoundedRectangle(cornerRadius:radius))
                .overlay(RoundedRectangle(cornerRadius:radius).strokeBorder(.primary.opacity(0.12)))
        } else {
            content.glassEffect(.regular,in:RoundedRectangle(cornerRadius:radius))
        }
    }
}

extension View {
    func glassSurface(_ radius:CGFloat=18)->some View {modifier(GlassSurface(radius:radius))}
    func contentCard(_ radius:CGFloat=18)->some View {
        background(Color(nsColor:.controlBackgroundColor).opacity(0.75),in:RoundedRectangle(cornerRadius:radius))
            .overlay(RoundedRectangle(cornerRadius:radius).strokeBorder(.primary.opacity(0.06)))
    }
}

struct LibraryStat: View {
    let title:String
    let value:Int
    let symbol:String
    var body:some View {
        HStack(spacing:8) {
            Image(systemName:symbol).foregroundStyle(Brand.accent)
            Text("\(value)").font(.callout.bold().monospacedDigit())
            Text(title).font(.caption).foregroundStyle(.secondary)
        }.padding(.horizontal,14).padding(.vertical,10).glassSurface(22)
    }
}
