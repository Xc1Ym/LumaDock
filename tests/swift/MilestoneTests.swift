import XCTest
@testable import LumaNX

@MainActor final class MilestoneTests:XCTestCase {
    private var plan:[Milestone] {[
        Milestone(id:"verify",label:"校验游戏文件",purpose:"verify",expected:20,source:"history",samples:2),
        Milestone(id:"shaders",label:"转换并编译着色器",purpose:"compile",expected:100,source:"default",samples:0),
        Milestone(id:"install",label:"检查并安装运行版本",purpose:"install",expected:10)
    ]}
    func testMeasuredSpeedProjectsCurrentStepAndCalibratesLaterSteps() {
        let estimate=MilestoneEstimate(plan:plan,current:"shaders",started:["verify":0,"shaders":40],fraction:0.25,now:60)
        XCTAssertEqual(estimate.calibration,2)
        XCTAssertEqual(estimate.stepElapsed,20);XCTAssertEqual(estimate.totalElapsed,60)
        XCTAssertEqual(estimate.currentRemaining,60);XCTAssertEqual(estimate.remaining,80)
        XCTAssertEqual(estimate.fill(0),1);XCTAssertEqual(estimate.fill(1),0.25);XCTAssertEqual(estimate.fill(2),0)
    }
    func testUnknownTotalUsesClearlyEstimatedFillAndNeverClaimsCompletion() {
        let estimate=MilestoneEstimate(plan:plan,current:"shaders",started:["shaders":0],fraction:nil,now:300)
        XCTAssertNil(estimate.measuredFraction);XCTAssertEqual(estimate.fill(1),0.95)
        XCTAssertEqual(estimate.currentRemaining,10);XCTAssertEqual(estimate.remaining,20)
        let completed=MilestoneEstimate(plan:plan,current:"install",started:["install":0],fraction:1,now:20)
        XCTAssertEqual(completed.currentRemaining,0);XCTAssertEqual(completed.remaining,0)
    }
    func testCachedStagesDoNotMakeLaterEstimatesArtificiallyFast() {
        let estimate=MilestoneEstimate(plan:plan,current:"shaders",started:["verify":0,"shaders":1],fraction:nil,now:11,cached:["verify"])
        XCTAssertEqual(estimate.calibration,1)
        XCTAssertEqual(estimate.currentRemaining,90)
    }
    func testNarrowBarsRemainWithinAvailableWidth() {
        for width in [0.0,1,12,50,300] {
            let gap=MilestoneEstimate.gap(count:plan.count,available:width)
            let widths=MilestoneEstimate.widths(plan,available:width)
            XCTAssertEqual(widths.count,3);XCTAssertTrue(widths.allSatisfy{$0.isFinite && $0>=0})
            XCTAssertLessThanOrEqual(widths.reduce(0,+)+gap*2,width+0.00001)
        }
        XCTAssertEqual(MilestoneEstimate.widths([],available:100),[])
    }
    func testPlanAndStageProtocolKeepsWorkerTimestampsAndResetsOnlyStepCounters() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root);store.tasks=[TaskRecord(id:"build",operation:"build",state:"running",done:9,total:10)]
        let rows=try JSONSerialization.jsonObject(with:JSONEncoder().encode(plan))
        store.event(["schema":1,"taskId":"build","type":"plan","milestones":rows],visible:true)
        XCTAssertNil(store.tasks[0].done)
        store.event(["schema":1,"taskId":"build","type":"stage","milestone":"shaders","milestoneStarted":["verify":100.0,"shaders":120.0]],visible:true)
        store.event(["schema":1,"taskId":"build","type":"progress","done":25,"total":100,"milestone":"shaders"],visible:true)
        store.event(["schema":1,"taskId":"build","type":"heartbeat","milestone":"shaders"],visible:true)
        XCTAssertEqual(store.tasks[0].milestoneStarted,["verify":100,"shaders":120]);XCTAssertEqual(store.tasks[0].done,25)
        store.event(["schema":1,"taskId":"build","type":"stage","milestone":"install","milestoneCached":["verify"]],visible:true)
        XCTAssertEqual(store.tasks[0].milestone,"install");XCTAssertNil(store.tasks[0].done)
        XCTAssertEqual(store.tasks[0].milestoneCached,["verify"])
        store.persistTask(store.tasks[0])
        let saved=try JSONDecoder().decode(TaskRecord.self,from:Data(contentsOf:root.appendingPathComponent("jobs/build.json")))
        XCTAssertEqual(saved.milestones,plan);XCTAssertEqual(saved.milestoneStarted,store.tasks[0].milestoneStarted)
    }
    func testInvalidPlansAndLegacyTasksDoNotBreakRegularProgress() throws {
        var invalid=plan;invalid[0].expected = -1
        XCTAssertFalse(invalid[0].valid)
        let old=try JSONDecoder().decode(TaskRecord.self,from:Data(#"{"id":"old","operation":"build","state":"running","done":5,"total":10}"#.utf8))
        XCTAssertNil(old.milestones);XCTAssertEqual(old.progressFraction,0.5)
        let estimate=MilestoneEstimate(plan:plan,current:"unknown",started:[:],fraction:.nan,now:100)
        XCTAssertNil(estimate.remaining);XCTAssertNil(estimate.measuredFraction)
    }
}
