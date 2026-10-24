// Milestone view/estimation adapted from jhaizhou-ops/S2Arm at 601b5454.
// See docs/Third-party-licenses.md for source attribution.
import SwiftUI

struct Milestone: Codable, Identifiable, Equatable {
    var id:String
    var label:String
    var purpose:String
    var expected:Double
    var source:String?
    var samples:Int?
    var valid:Bool {!id.isEmpty && expected.isFinite && expected>0 && expected<315360000}
    var estimateSource:String {
        if source == "history",let samples,samples>0 {return L("本机历史 · \(samples) 次记录")}
        return L("初始参考估时，实际耗时可能变化")
    }
}

/// S2Arm's per-step speed projection and calibration from completed steps.
/// Elapsed-time fill is an estimate; the displayed percentage always uses counters.
struct MilestoneEstimate {
    let plan:[Milestone]
    let current:String?
    let started:[String:Double]
    let fraction:Double?
    let now:Double
    var cached:Set<String>=[]
    var index:Int? {plan.firstIndex{$0.id==current}}
    private func elapsed(since value:Double)->Double {
        guard now.isFinite,value.isFinite else {return 0}
        return min(315360000,max(0,now-value))
    }
    var stepElapsed:Double {current.flatMap{started[$0]}.map{elapsed(since:$0)} ?? 0}
    var totalElapsed:Double {started.values.filter(\.isFinite).min().map{elapsed(since:$0)} ?? 0}
    var calibration:Double {
        guard let i=index,i>0 else {return 1}
        var actual=0.0,expected=0.0
        for k in 0..<i {
            if cached.contains(plan[k].id) {continue}
            guard let start=started[plan[k].id],let end=started[plan[k+1].id],start.isFinite,end.isFinite,plan[k].valid else {continue}
            actual+=max(0,end-start);expected+=plan[k].expected
        }
        return expected>1 ? min(3,max(0.5,actual/expected)):1
    }
    var measuredFraction:Double? {
        guard let fraction,fraction.isFinite else {return nil}
        return min(1,max(0,fraction))
    }
    var currentRemaining:Double {
        guard let i=index else {return 0}
        if let f=measuredFraction {
            if f>=1 {return 0}
            if f>=0.05,stepElapsed>=1 {return min(315360000,stepElapsed*(1-f)/f)}
        }
        let expected=plan[i].expected*calibration
        return max(expected-stepElapsed,expected*0.1)
    }
    var remaining:Double? {
        guard let i=index else {return nil}
        return min(315360000,currentRemaining+plan.dropFirst(i+1).reduce(0){$0+$1.expected}*calibration)
    }
    func fill(_ k:Int)->Double {
        guard let i=index else {return 0}
        if k<i {return 1};if k>i {return 0}
        return measuredFraction ?? min(0.95,stepElapsed/max(1,plan[i].expected*calibration))
    }
    /// Reserve minimum widths before sharing the rest, keeping narrow bars in bounds.
    static func gap(count:Int,available:Double)->Double {min(2,max(0,available)/Double(max(1,count*2)))}
    static func widths(_ plan:[Milestone],available:Double)->[Double] {
        guard !plan.isEmpty,available.isFinite else {return []}
        let gap=gap(count:plan.count,available:available)
        let usable=max(0,available-gap*Double(plan.count-1))
        let minimum=min(6,usable/Double(plan.count))
        let weights=plan.map{$0.valid ? max(1,$0.expected):1}
        let extra=max(0,usable-minimum*Double(plan.count)),total=weights.reduce(0,+)
        return weights.map{minimum+extra*$0/total}
    }
}

func milestoneDuration(_ seconds:Double)->String {
    let formatter=DateComponentsFormatter()
    formatter.unitsStyle = .short
    formatter.allowedUnits=seconds>=3600 ? [.hour,.minute]:seconds>=60 ? [.minute,.second]:[.second]
    var calendar=Calendar.current
    calendar.locale=Locale(identifier:Localization.language.hasPrefix("en") ? "en_US":"zh_CN")
    formatter.calendar=calendar
    let safe=seconds.isFinite ? min(315360000,max(0,seconds.rounded())):0
    return formatter.string(from:safe) ?? "\(Int(safe))"
}

struct MilestoneProgressView:View {
    let task:TaskRecord
    var compact=false
    private var plan:[Milestone] {task.milestones ?? []}
    private func amount(_ value:Double)->String {
        let safe=min(Double(Int64.max-1024),max(0,value))
        return task.unit=="B" ? ByteCountFormatter.string(fromByteCount:Int64(safe),countStyle:.file):String(format:"%.0f",safe)
    }
    var body:some View {
        TimelineView(.periodic(from:.now,by:1)) {timeline in
            let estimate=MilestoneEstimate(plan:plan,current:task.milestone,started:task.milestoneStarted ?? [:],fraction:task.progressFraction,now:timeline.date.timeIntervalSince1970,cached:Set(task.milestoneCached ?? []))
            VStack(alignment:.leading,spacing:compact ? 4:8) {
                GeometryReader {geometry in
                    let widths=MilestoneEstimate.widths(plan,available:Double(geometry.size.width))
                    HStack(spacing:CGFloat(MilestoneEstimate.gap(count:plan.count,available:Double(geometry.size.width)))) {
                        ForEach(Array(plan.enumerated()),id:\.element.id) {k,m in
                            let width=widths[k]
                            ZStack(alignment:.leading) {
                                Rectangle().fill(Color.secondary.opacity(0.18))
                                Rectangle().fill(Color.teal.opacity(k==estimate.index && estimate.measuredFraction==nil ? 0.4:0.9))
                                    .frame(width:CGFloat(width*estimate.fill(k)))
                            }.frame(width:CGFloat(width))
                                .accessibilityLabel(L(m.label))
                                .help(L(m.label)+" · "+L(m.purpose)+" · "+L("预计 ")+milestoneDuration(m.expected*estimate.calibration))
                        }
                    }
                }.frame(height:compact ? 6:12).clipShape(RoundedRectangle(cornerRadius:compact ? 3:6))
                    .accessibilityLabel(L("里程碑进度，浅色填充为估计"))
                if let i=estimate.index {
                    let current=plan[i]
                    HStack(alignment:.firstTextBaseline) {
                        Text(L("第 \(i+1)/\(plan.count) 步")).foregroundStyle(.secondary)
                        Text(L(current.label)).bold().fixedSize(horizontal:false,vertical:true)
                        Spacer(minLength:8)
                    }.font(compact ? .caption:.callout)
                    HStack(alignment:.firstTextBaseline) {
                        if let fraction=task.progressFraction,let done=task.done,let total=task.total {
                            let label=["files":"个文件","shaders":"个着色器","checks":"项检查"][task.unit ?? ""] ?? ""
                            Text(amount(min(done,total))+" / "+amount(total)+(label.isEmpty ? "":" "+L(label))+" · \(Int(fraction*100))%").monospacedDigit()
                        } else {Text(L("本步总量暂不可确定"))}
                        Spacer(minLength:8)
                        if let remaining=estimate.remaining {Text(L("预计还需 ")+milestoneDuration(remaining)).monospacedDigit()}
                    }.font(.caption).foregroundStyle(.secondary)
                    if !compact {
                        Text(L(current.purpose)).font(.caption).foregroundStyle(.secondary)
                        Text(current.estimateSource).font(.caption).foregroundStyle(.secondary)
                        ViewThatFits(in:.horizontal) {
                            HStack {
                                timing(estimate)
                                Spacer()
                                if let remaining=estimate.remaining {
                                    let completion=Date(timeIntervalSince1970:timeline.date.timeIntervalSince1970+remaining).formatted(date:.omitted,time:.shortened)
                                    Text(L("预计 \(completion) 完成"))
                                }
                            }
                            timing(estimate)
                        }.font(.caption).foregroundStyle(.secondary).monospacedDigit()
                    }
                }
            }
        }
    }
    private func timing(_ estimate:MilestoneEstimate)->Text {
        Text(L("已用 ")+milestoneDuration(estimate.totalElapsed)+L("，本步 ")+milestoneDuration(estimate.stepElapsed))
    }
}
