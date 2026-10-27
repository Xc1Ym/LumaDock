import SwiftUI
import AppKit

enum WorkspacePalette {
    static let accent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(red: 0.35, green: 0.86, blue: 0.85, alpha: 1)
            : NSColor(red: 0.02, green: 0.45, blue: 0.49, alpha: 1)
    })
}

/// Shared by utility pages. The library keeps its existing layout and surfaces.
struct WorkspacePage<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            GlassEffectContainer(spacing: 16) {
                VStack(alignment: .leading, spacing: 16) { content }
                    .frame(maxWidth: 1020, alignment: .leading)
                    .frame(maxWidth: .infinity)
                    .padding(24)
            }
        }.tint(WorkspacePalette.accent)
    }
}

struct WorkspaceHeading<Actions: View>: View {
    let title: String
    let subtitle: String
    let symbol: String
    @ViewBuilder var actions: Actions
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.title2).foregroundStyle(WorkspacePalette.accent)
                .frame(width: 44, height: 44).glassSurface(14)
            VStack(alignment: .leading, spacing: 4) {
                Text(L(title)).font(.title2.bold()).lineLimit(2)
                Text(L(subtitle)).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            actions.controlSize(.small)
        }.padding(.bottom, 2)
    }
}

struct GlassPanel<Content: View>: View {
    var title: String? = nil
    var symbol: String = ""
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let title {
                Label(L(title), systemImage: symbol).font(.headline)
            }
            content
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading).glassSurface(20)
    }
}

/// Native disclosure semantics and keyboard support, with one compact summary row.
struct CompactDisclosure<Content: View>: View {
    let title: String
    var subtitle: String = ""
    var symbol: String = "info.circle"
    @State private var expanded = false
    @ViewBuilder var content: Content
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 12) { content }
                .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 12)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: symbol).foregroundStyle(WorkspacePalette.accent).frame(width: 20)
                Text(L(title)).font(.callout.weight(.semibold))
                Spacer(minLength: 8)
                if !subtitle.isEmpty {
                    Text(L(subtitle)).font(.caption).foregroundStyle(.secondary)
                        .lineLimit(1).truncationMode(.middle)
                }
            }.padding(.vertical, 2)
        }.tint(WorkspacePalette.accent)
    }
}

struct StatusPill: View {
    let title: String
    var symbol: String = "checkmark.circle.fill"
    var color: Color = WorkspacePalette.accent
    var body: some View {
        Label(L(title), systemImage: symbol).font(.caption.weight(.medium))
            .foregroundStyle(color).padding(.horizontal, 10).padding(.vertical, 6)
            .background(color.opacity(0.09), in: Capsule())
    }
}
